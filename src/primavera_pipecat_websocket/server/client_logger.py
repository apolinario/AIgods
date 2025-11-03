"""
Client Logger - Sends server logs to connected clients

This processor intercepts key events and sends them to the client
for display, mirroring the server-side debug output.
"""

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    MetricsFrame,
)
from pipecat.metrics.metrics import SmartTurnMetricsData
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class ClientLogFrame(Frame):
    """Custom frame for sending log messages to client."""

    def __init__(self, message: str, level: str = "INFO"):
        super().__init__()
        self.message = message
        self.level = level


class ClientLogger(FrameProcessor):
    """Sends server logs to client for real-time debugging."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Intercept frames and send relevant logs to client."""
        await super().process_frame(frame, direction)

        # Log user speech events
        if isinstance(frame, UserStartedSpeakingFrame):
            await self.push_frame(ClientLogFrame("🎤 User started speaking", "DEBUG"))

        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self.push_frame(ClientLogFrame("🔇 User stopped speaking", "DEBUG"))

        # Log bot speech events
        elif isinstance(frame, BotStartedSpeakingFrame):
            await self.push_frame(ClientLogFrame("🤖 Bot started speaking", "DEBUG"))

        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self.push_frame(ClientLogFrame("✅ Bot stopped speaking", "DEBUG"))

        # Log transcriptions
        elif isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                await self.push_frame(ClientLogFrame(f"📝 Transcription: {text}", "INFO"))

        # Log Smart Turn metrics
        elif isinstance(frame, MetricsFrame):
            for metrics in frame.data:
                if isinstance(metrics, SmartTurnMetricsData):
                    status = "COMPLETE" if metrics.is_complete else "INCOMPLETE"
                    msg = (
                        f"🔄 Smart Turn: {status}, "
                        f"Probability: {metrics.probability:.1%}, "
                        f"E2E: {metrics.e2e_processing_time_ms:.1f}ms"
                    )
                    await self.push_frame(ClientLogFrame(msg, "INFO"))

        await self.push_frame(frame, direction)
