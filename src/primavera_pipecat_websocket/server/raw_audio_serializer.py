"""
Raw Audio Serializer for Pipecat WebSocket Transport

This serializer handles raw audio bytes from custom clients (like our Raspberry Pi phone).
It wraps raw bytes in a minimal format that the WebSocket transport can process.
"""

import struct
from typing import Any

import json
from loguru import logger
from pipecat.frames.frames import (
    AudioRawFrame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    Frame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType


class RawAudioSerializer(FrameSerializer):
    """Simple serializer for raw audio byte streams.

    Protocol:
    - Client sends: raw audio bytes (16-bit PCM, 16kHz, mono)
    - Server sends:
        - Audio frames: raw audio bytes (16-bit PCM, 24kHz for VibeVoice)
        - Text frames: JSON messages with logs/status (prefixed with 'TEXT:')

    Messages are differentiated by prefix:
    - Audio: starts with binary audio data
    - Text/Logs: starts with 'TEXT:' followed by JSON
    """

    def __init__(self, sample_rate: int = 16000, num_channels: int = 1):
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        logger.info(f"RawAudioSerializer initialized: {sample_rate}Hz, {num_channels} channel(s)")

    @property
    def type(self) -> FrameSerializerType:
        """Return serializer type (binary for raw audio bytes)."""
        return FrameSerializerType.BINARY

    async def serialize(self, frame: Frame) -> bytes | None:
        """Serialize frames to send to client.

        Serializes OutputAudioRawFrame as audio and TranscriptionFrame/TextFrame as JSON logs.
        """
        if isinstance(frame, OutputAudioRawFrame):
            # Return raw audio bytes prefixed with 'AUDIO:'
            import time
            logger.info(f"🔊 SERIALIZER called at {time.time():.3f}: {len(frame.audio)} bytes at {frame.sample_rate}Hz")
            return b"AUDIO:" + frame.audio

        elif isinstance(frame, TranscriptionFrame):
            # Send transcription as JSON log message
            log_msg = {
                "type": "transcription",
                "text": frame.text,
                "user_id": getattr(frame, "user_id", ""),
                "timestamp": getattr(frame, "timestamp", ""),
            }
            return b"LOG:" + json.dumps(log_msg).encode("utf-8")

        elif isinstance(frame, TextFrame):
            # Send text frame as JSON log (for LLM responses and Smart Turn)
            log_msg = {
                "type": "text",
                "text": frame.text,
            }
            logger.debug(f"Serializing text frame: {frame.text[:50]}...")
            return b"LOG:" + json.dumps(log_msg).encode("utf-8")

        # Log ignored frame types for debugging
        if frame.__class__.__name__ not in ["StartFrame", "EndFrame", "CancelFrame", "SystemFrame"]:
            logger.debug(f"Ignoring frame type: {frame.__class__.__name__}")

        return None

    async def deserialize(self, data: bytes) -> Frame | None:
        """Deserialize incoming data from client.

        Assumes all incoming bytes are audio data.
        """
        if not data:
            return None

        # Wrap raw bytes in InputAudioRawFrame (for incoming audio from client)
        return InputAudioRawFrame(
            audio=data,
            sample_rate=self._sample_rate,
            num_channels=self._num_channels,
        )
