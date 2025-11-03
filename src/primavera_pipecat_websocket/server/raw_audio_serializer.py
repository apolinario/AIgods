"""
Raw Audio Serializer for Pipecat WebSocket Transport

This serializer handles raw audio bytes from custom clients (like our Raspberry Pi phone).
It wraps raw bytes in a minimal format that the WebSocket transport can process.
"""

import struct
from typing import Any

from loguru import logger
from pipecat.frames.frames import AudioRawFrame, Frame
from pipecat.serializers.base_serializer import FrameSerializer


class RawAudioSerializer(FrameSerializer):
    """Simple serializer for raw audio byte streams.

    Protocol:
    - Client sends: raw audio bytes (16-bit PCM, 16kHz, mono)
    - Server sends: raw audio bytes (same format)

    No complex framing needed - just raw audio in/out.
    """

    def __init__(self, sample_rate: int = 16000, num_channels: int = 1):
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        logger.info(f"RawAudioSerializer initialized: {sample_rate}Hz, {num_channels} channel(s)")

    async def serialize(self, frame: Frame) -> bytes | None:
        """Serialize frames to send to client.

        Only AudioRawFrame is serialized - everything else is ignored.
        """
        if isinstance(frame, AudioRawFrame):
            # Just return raw audio bytes
            return frame.audio

        # Ignore other frame types (client doesn't need them)
        return None

    async def deserialize(self, data: bytes) -> Frame | None:
        """Deserialize incoming data from client.

        Assumes all incoming bytes are audio data.
        """
        if not data:
            return None

        # Wrap raw bytes in AudioRawFrame
        return AudioRawFrame(
            audio=data,
            sample_rate=self._sample_rate,
            num_channels=self._num_channels,
        )
