"""
Custom VibeVoice TTS Service for Pipecat

This service wraps the VibeVoice API to work with Pipecat's pipeline.
VibeVoice provides high-quality neural TTS using the OpenAI-compatible API.
"""

import asyncio
import base64
import json
import os
from typing import AsyncGenerator, Optional

import numpy as np
from loguru import logger
from openai import OpenAI
from pipecat.frames.frames import OutputAudioRawFrame, ErrorFrame, Frame
from pipecat.services.tts_service import TTSService
from pipecat.utils.text.base_text_aggregator import BaseTextAggregator


class NoAggregationTextAggregator(BaseTextAggregator):
    """Text aggregator that doesn't split on sentence boundaries.

    Used when we want to send complete responses to TTS without splitting.
    """

    def __init__(self):
        self._text = ""

    @property
    def text(self) -> str:
        return self._text

    async def aggregate(self, text: str) -> Optional[str]:
        """Accumulate all text and return it only when explicitly asked."""
        self._text += text
        # Never auto-split - return None to keep accumulating
        return None

    async def handle_interruption(self):
        """Clear buffer on interruption."""
        self._text = ""

    async def reset(self):
        """Clear the buffer."""
        self._text = ""


class VibeVoiceTTSService(TTSService):
    """VibeVoice Text-to-Speech service for Pipecat.

    Uses VibeVoice's streaming SSE API to generate natural-sounding speech
    from text in real-time.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "not-used",
        model: str,
        voice_path: str,
        ddpm_steps: int = 20,
        cfg_scale: float = 1.5,
        sample_rate: int = 24000,
        **kwargs,
    ):
        """Initialize VibeVoice TTS service.

        Args:
            base_url: The base URL for VibeVoice API
            api_key: API key (not required for local VibeVoice)
            model: The model name to use
            voice_path: Path to the voice file
            ddpm_steps: DDPM sampling steps (default: 20)
            cfg_scale: Classifier-free guidance scale (default: 1.5)
            sample_rate: Audio sample rate (default: 24000)
        """
        # Use custom aggregator that doesn't split on sentence boundaries
        # We get complete responses from Gemini, so we want to send the full text
        super().__init__(
            aggregate_sentences=False,
            text_aggregator=NoAggregationTextAggregator(),
            **kwargs
        )

        self._base_url = base_url
        self._model = model
        self._voice_path = voice_path
        self._ddpm_steps = ddpm_steps
        self._cfg_scale = cfg_scale
        self._sample_rate = sample_rate

        # Initialize OpenAI client with VibeVoice base URL
        self._client = OpenAI(base_url=base_url, api_key=api_key)

        logger.info(
            f"VibeVoice TTS initialized: {base_url}, model={model}, voice={voice_path}"
        )

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Convert text to speech using VibeVoice streaming API.

        Args:
            text: The text to convert to speech

        Yields:
            AudioRawFrame: Frames containing PCM audio data
            ErrorFrame: If an error occurs during TTS
        """
        logger.info(f"🎵 VibeVoice TTS request: {text[:100]}... (total length: {len(text)} chars)")

        try:
            # Call VibeVoice API with streaming enabled
            with self._client.audio.speech.with_streaming_response.create(
                model=self._model,
                voice="ignored_when_voice_path",  # Voice path used instead
                input=text,
                response_format="pcm",
                extra_body={
                    "voice_path": self._voice_path,
                    "stream_format": "sse",
                    "ddpm_steps": self._ddpm_steps,
                    "cfg_scale": self._cfg_scale,
                },
            ) as stream:
                # Parse SSE (Server-Sent Events) stream
                current_event = None
                data_buffer = ""
                actual_sample_rate = self._sample_rate
                chunk_count = 0

                logger.debug("Processing VibeVoice SSE stream...")

                for line in stream.iter_lines():
                    if not line:  # Empty line separates events
                        if current_event and data_buffer:
                            # Process the complete event
                            try:
                                if current_event == "start":
                                    # Extract actual sample rate from server
                                    meta = json.loads(data_buffer)
                                    actual_sample_rate = int(
                                        meta.get("sample_rate", self._sample_rate)
                                    )
                                    logger.info(
                                        f"VibeVoice stream started: {actual_sample_rate}Hz"
                                    )

                                elif current_event == "chunk":
                                    # Decode and yield audio chunk
                                    payload = json.loads(data_buffer)
                                    audio_b64 = payload.get("data")

                                    if audio_b64:
                                        audio_bytes = base64.b64decode(audio_b64)
                                        audio_np = np.frombuffer(
                                            audio_bytes, dtype=np.int16
                                        )

                                        # Create OutputAudioRawFrame for Pipecat
                                        frame = OutputAudioRawFrame(
                                            audio=audio_np.tobytes(),
                                            sample_rate=actual_sample_rate,
                                            num_channels=1,
                                        )
                                        chunk_count += 1
                                        logger.info(f"🎵 Yielding TTS chunk #{chunk_count}: {len(audio_bytes)} bytes")
                                        yield frame

                                elif current_event == "end":
                                    logger.info(f"🎵 VibeVoice stream COMPLETED - total chunks: {chunk_count}")
                                    break

                                elif current_event == "error":
                                    error_data = json.loads(data_buffer)
                                    logger.error(f"VibeVoice error: {error_data}")
                                    yield ErrorFrame(
                                        f"VibeVoice error: {error_data}"
                                    )
                                    break

                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode SSE data: {e}")
                            except Exception as e:
                                logger.error(f"Error processing SSE event: {e}")
                                yield ErrorFrame(f"VibeVoice processing error: {e}")

                        # Reset for next event
                        current_event, data_buffer = None, ""
                        continue

                    # Parse SSE format
                    if line.startswith("event:"):
                        current_event = line[len("event: ") :].strip()
                    elif line.startswith("data:"):
                        data_buffer += line[len("data: ") :].strip()

        except Exception as e:
            logger.exception(f"VibeVoice TTS error: {e}")
            yield ErrorFrame(f"VibeVoice TTS failed: {str(e)}")


# Factory function for easy initialization
def create_vibevoice_service(
    base_url: str | None = None,
    model: str | None = None,
    voice_path: str | None = None,
    **kwargs,
) -> VibeVoiceTTSService:
    """Create VibeVoice TTS service from environment variables.

    Args:
        base_url: Override VIBEVOICE_BASE_URL env var
        model: Override VIBEVOICE_MODEL env var
        voice_path: Override VIBEVOICE_PATH env var
        **kwargs: Additional arguments passed to VibeVoiceTTSService

    Returns:
        Configured VibeVoiceTTSService instance
    """
    return VibeVoiceTTSService(
        base_url=base_url or os.getenv("VIBEVOICE_BASE_URL"),
        model=model or os.getenv("VIBEVOICE_MODEL"),
        voice_path=voice_path or os.getenv("VIBEVOICE_PATH"),
        **kwargs,
    )
