"""
Pipecat Voice Bot with Whisper STT, Smart Turn V3, and Gemini LLM

This bot implementation uses:
- Whisper for Speech-to-Text (local or API)
- Smart Turn V3 for intelligent turn-taking
- Google Gemini for LLM responses
- Cartesia for Text-to-Speech
- WebSocket transport for Raspberry Pi client communication
"""

import asyncio
import os
import sys
from typing import Optional

# Load environment variables FIRST before any other imports
from dotenv import load_dotenv
load_dotenv(override=True)

# Add parent directory to path to import shared modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from loguru import logger

# Import shared modules from parent src directory
# These need GOOGLE_API_KEY to be set, so import after load_dotenv
from config_loader import ConfigLoader
from conversation_manager import GeminiConversationManager
from gemini_cache import get_gemini_cache
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    MetricsFrame,
    StartFrame,
    StartInterruptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import SmartTurnMetricsData
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.whisper.stt import WhisperSTTService
from vibevoice_tts import create_vibevoice_service
from raw_audio_serializer import RawAudioSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

# Environment already loaded at top of file

logger.remove()
logger.add(sys.stderr, level="DEBUG")


class InterruptionHandler(FrameProcessor):
    """Handles user interruptions during bot speech.

    When a user starts speaking while the bot is talking, this processor
    triggers an interruption to stop the bot and allow the user to speak.
    """

    def __init__(self):
        super().__init__()
        self._bot_is_speaking = False
        self._user_is_speaking = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames to detect and handle interruptions."""
        await super().process_frame(frame, direction)

        # Track bot speaking state
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_is_speaking = True
            logger.info("🤖 Bot STARTED speaking")
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_is_speaking = False
            logger.info("🤖 Bot STOPPED speaking")

        # Track user speaking state
        elif isinstance(frame, UserStartedSpeakingFrame):
            self._user_is_speaking = True
            logger.info("👤 User STARTED speaking")

            # If bot is speaking when user starts, trigger interruption
            if self._bot_is_speaking:
                logger.warning("⚠️ User interruption detected - CANCELING bot speech!")
                await self.push_frame(StartInterruptionFrame())

        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._user_is_speaking = False
            logger.info("👤 User STOPPED speaking")
            # StopInterruptionFrame was removed from Pipecat
            # UserStoppedSpeakingFrame is sufficient

        await self.push_frame(frame, direction)


class GeminiProcessor(FrameProcessor):
    """Custom processor that uses GeminiConversationManager with cache.

    This processor handles the LLM interaction using the existing Primavera
    personality system and Gemini cache for context.
    """

    def __init__(self, conversation_manager: GeminiConversationManager):
        super().__init__()
        self.conversation_manager = conversation_manager

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process transcription frames and generate responses."""
        await super().process_frame(frame, direction)

        # Handle user transcripts
        if isinstance(frame, TranscriptionFrame):
            logger.debug(f"GeminiProcessor received TranscriptionFrame: text='{frame.text}', user_id='{getattr(frame, 'user_id', 'N/A')}'")

            # Check if it's a user transcript (not from bot)
            if frame.text.strip():
                logger.info(f"User transcript: {frame.text}")

                # Add user message to conversation
                self.conversation_manager.add_user_message(frame.text)

                # Generate response using Gemini with cache
                try:
                    full_response = ""
                    for text_chunk in self.conversation_manager.generate_response(streaming=True):
                        full_response += text_chunk

                    # Create text frame for TTS
                    if full_response.strip():
                        logger.info(f"Gemini response: {full_response}")
                        # Send text to TTS by creating appropriate frame
                        # The TTS service will pick this up
                        from pipecat.frames.frames import TextFrame
                        await self.push_frame(TextFrame(text=full_response))

                except Exception as e:
                    logger.error(f"Error generating Gemini response: {e}")

        await self.push_frame(frame, direction)


class SmartTurnMetricsProcessor(FrameProcessor):
    """Processes and logs Smart Turn V3 metrics.

    This processor extracts timing and prediction data from Smart Turn
    to monitor turn-taking performance and sends them to the client.
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames and extract Smart Turn metrics."""
        await super().process_frame(frame, direction)

        if isinstance(frame, MetricsFrame):
            for metrics in frame.data:
                if isinstance(metrics, SmartTurnMetricsData):
                    log_text = (
                        f"Smart Turn: "
                        f"{'COMPLETE' if metrics.is_complete else 'INCOMPLETE'}, "
                        f"Probability: {metrics.probability:.2%}, "
                        f"E2E: {metrics.e2e_processing_time_ms:.2f}ms"
                    )
                    logger.info(log_text)

                    # Send to client as a custom log frame
                    from pipecat.frames.frames import TextFrame
                    log_frame = TextFrame(text=f"[SmartTurn] {log_text}")
                    await self.push_frame(log_frame)

        await self.push_frame(frame, direction)


class ConversationLogger(FrameProcessor):
    """Logs conversation transcripts for debugging and sends to client."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Log transcript frames and forward to client."""
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            user_id = getattr(frame, "user_id", "")
            if user_id == "user" or not user_id:
                logger.info(f"User: {frame.text}")
            else:
                logger.info(f"Bot: {frame.text}")

        await self.push_frame(frame, direction)


class VADDebugLogger(FrameProcessor):
    """Logs VAD events to debug audio processing issues."""

    def __init__(self):
        super().__init__()
        self._audio_frame_count = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Log VAD and audio frames."""
        await super().process_frame(frame, direction)

        from pipecat.frames.frames import AudioRawFrame

        if isinstance(frame, UserStartedSpeakingFrame):
            logger.info("🎤 VAD: User STARTED speaking")
            self._audio_frame_count = 0
        elif isinstance(frame, UserStoppedSpeakingFrame):
            logger.info(f"🎤 VAD: User STOPPED speaking (captured {self._audio_frame_count} audio frames)")
        elif isinstance(frame, AudioRawFrame):
            self._audio_frame_count += 1
            if self._audio_frame_count % 50 == 0:  # Log every 50 frames
                logger.debug(f"🎤 Audio frame #{self._audio_frame_count} received ({len(frame.audio)} bytes)")

        await self.push_frame(frame, direction)


async def run_bot(websocket_transport: FastAPIWebsocketTransport):
    """Main bot pipeline setup and execution.

    Args:
        websocket_transport: WebSocket transport for client communication
    """

    # Load personality configuration (absolute path)
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../config'))
    config = ConfigLoader(config_dir=config_dir)
    logger.info(f"Loaded personality: {config.personality['name']}")

    # Initialize Gemini conversation manager with cache
    # gemini_cache.py now uses absolute paths to src/cache_transcripts
    conversation_manager = GeminiConversationManager(
        api_key=os.getenv("GOOGLE_API_KEY"),
        personality_config=config.personality
    )
    logger.info(f"Gemini cache initialized: {conversation_manager.cache_name}")

    # Use pre-loaded Whisper STT service
    stt = get_whisper_service()

    # Add event handlers for debugging STT issues
    @stt.event_handler("on_connected")
    async def on_stt_connected(service):
        logger.info("STT service connected")

    @stt.event_handler("on_disconnected")
    async def on_stt_disconnected(service):
        logger.warning("STT service disconnected")

    @stt.event_handler("on_connection_error")
    async def on_stt_error(service, error):
        logger.error(f"STT connection error: {error}")

    # Initialize VibeVoice TTS (uses environment variables)
    tts = create_vibevoice_service()

    # Initialize processors
    gemini_processor = GeminiProcessor(conversation_manager)
    interruption_handler = InterruptionHandler()
    smart_turn_metrics = SmartTurnMetricsProcessor()
    conversation_logger = ConversationLogger()
    vad_debug_logger = VADDebugLogger()

    # Build the pipeline
    pipeline = Pipeline(
        [
            websocket_transport.input(),  # Audio from Raspberry Pi
            vad_debug_logger,  # Debug VAD events
            conversation_logger,
            stt,  # Whisper STT
            gemini_processor,  # Gemini with cache and personality
            tts,  # VibeVoice TTS
            interruption_handler,  # Handle interruptions
            smart_turn_metrics,  # Log Smart Turn metrics
            websocket_transport.output(),  # Audio back to Raspberry Pi
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            allow_interruptions=True,  # Enable interruption handling
        ),
    )

    # Event handler for client disconnection
    @websocket_transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Client disconnected: {client}")
        # Cancel the task to stop the runner
        await task.cancel()

    # Run the pipeline
    # The transport will automatically handle StartFrame when client connects
    runner = PipelineRunner()
    await runner.run(task)


async def create_bot_instance(websocket):
    """Create a new bot instance for a WebSocket connection.

    Args:
        websocket: FastAPI WebSocket connection

    Returns:
        FastAPIWebsocketTransport: Configured transport instance
    """
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,  # Raw audio for efficiency
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(stop_secs=0.2)  # Optimal for Smart Turn V3
            ),
            turn_analyzer=LocalSmartTurnAnalyzerV3(),
            serializer=RawAudioSerializer(sample_rate=16000, num_channels=1),
        ),
    )

    return transport


# Pre-load Whisper model at module import time to avoid delays on first connection
_whisper_service = None
_whisper_call_count = 0

class WhisperSTTServiceDebug(WhisperSTTService):
    """Wrapper around WhisperSTTService that adds detailed logging."""

    async def run_stt(self, audio: bytes):
        """Override run_stt to add logging."""
        global _whisper_call_count
        _whisper_call_count += 1
        call_id = _whisper_call_count

        logger.info(f"🔊 Whisper transcription #{call_id} STARTED (audio size: {len(audio)} bytes)")

        try:
            result_count = 0
            async for frame in super().run_stt(audio):
                result_count += 1
                logger.info(f"🔊 Whisper transcription #{call_id} yielded frame #{result_count}: {type(frame).__name__}")
                yield frame

            if result_count == 0:
                logger.warning(f"🔊 Whisper transcription #{call_id} COMPLETED with NO results")
            else:
                logger.info(f"🔊 Whisper transcription #{call_id} COMPLETED successfully")
        except Exception as e:
            logger.error(f"🔊 Whisper transcription #{call_id} FAILED with error: {e}", exc_info=True)
            raise

def get_whisper_service():
    """Get or create the shared Whisper service instance."""
    global _whisper_service
    if _whisper_service is None:
        whisper_model = os.getenv("WHISPER_MODEL", "base")
        logger.info(f"Pre-loading Whisper model: {whisper_model}")
        _whisper_service = WhisperSTTServiceDebug(model=whisper_model)
        logger.info("Whisper model loaded and ready")
    return _whisper_service


if __name__ == "__main__":
    # This file is imported by server.py, not run directly
    logger.info("Bot module loaded")
