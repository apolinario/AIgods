"""
Raspberry Pi WebSocket Client for Pipecat Voice Bot

This lightweight client runs on a Raspberry Pi and:
1. Captures audio from the microphone
2. Streams audio chunks to the server via WebSocket
3. Receives processed audio from the server
4. Plays audio through speakers

All heavy processing (Whisper, Gemini, TTS, Smart Turn) happens on the server.
"""

import argparse
import asyncio
import os
import struct
import wave
from collections import deque
from typing import Optional

import numpy as np
import pyaudio
import websockets
from loguru import logger

# Import Pipecat serializer for protocol compatibility
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.frames.frames import AudioRawFrame, Frame

# Audio configuration
SAMPLE_RATE = 16000  # 16kHz for voice
CHANNELS = 1  # Mono
CHUNK_SIZE = 1024  # Samples per chunk
FORMAT = pyaudio.paInt16  # 16-bit audio
BYTES_PER_SAMPLE = 2


class AudioPlayer:
    """Handles audio playback through speakers."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.playback_queue = deque()
        self.is_playing = False

    def start(self):
        """Initialize audio output stream."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        logger.info("Audio playback initialized")

    def add_audio(self, audio_data: bytes):
        """Add audio data to playback queue."""
        self.playback_queue.append(audio_data)

    async def play_loop(self):
        """Continuously play audio from queue."""
        self.is_playing = True
        logger.info("Audio playback loop started")

        while self.is_playing:
            if self.playback_queue:
                audio_chunk = self.playback_queue.popleft()
                try:
                    self.stream.write(audio_chunk)
                except Exception as e:
                    logger.error(f"Error playing audio: {e}")
            else:
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.01)

    def stop(self):
        """Stop audio playback and cleanup."""
        self.is_playing = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        logger.info("Audio playback stopped")


class AudioRecorder:
    """Handles audio capture from microphone."""

    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.is_recording = False

    def start(self):
        """Initialize audio input stream."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        logger.info("Audio recording initialized")

    def read_chunk(self) -> bytes:
        """Read one chunk of audio data from microphone."""
        try:
            data = self.stream.read(CHUNK_SIZE, exception_on_overflow=False)
            return data
        except Exception as e:
            logger.error(f"Error reading audio: {e}")
            return b""

    def stop(self):
        """Stop audio recording and cleanup."""
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        logger.info("Audio recording stopped")


class VoiceBotClient:
    """Main client class that coordinates audio I/O and WebSocket communication."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.recorder = AudioRecorder()
        self.player = AudioPlayer()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        self.serializer = ProtobufFrameSerializer()  # Match server protocol

    async def send_audio(self):
        """Continuously capture and send audio to server."""
        logger.info("Starting audio transmission...")

        while self.is_running:
            try:
                # Read audio chunk from microphone
                audio_chunk = self.recorder.read_chunk()

                if audio_chunk and self.websocket:
                    # Create AudioRawFrame
                    frame = AudioRawFrame(
                        audio=audio_chunk,
                        sample_rate=SAMPLE_RATE,
                        num_channels=CHANNELS,
                    )

                    # Serialize and send
                    serialized = self.serializer.serialize(frame)
                    await self.websocket.send(serialized)

                # Small delay to prevent overwhelming the connection
                await asyncio.sleep(0.001)

            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                break

    async def receive_audio(self):
        """Continuously receive and play audio from server."""
        logger.info("Starting audio reception...")

        while self.is_running:
            try:
                if self.websocket:
                    # Receive serialized frame from server
                    serialized_data = await self.websocket.recv()

                    if isinstance(serialized_data, bytes):
                        # Deserialize the frame
                        frame = self.serializer.deserialize(serialized_data)

                        # Extract audio from AudioRawFrame
                        if isinstance(frame, AudioRawFrame):
                            self.player.add_audio(frame.audio)

            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed by server")
                break
            except Exception as e:
                logger.error(f"Error receiving audio: {e}")
                break

    async def connect_and_run(self):
        """Main connection loop."""
        logger.info(f"Connecting to server at {self.server_url}...")

        try:
            async with websockets.connect(
                self.server_url,
                ping_interval=20,
                ping_timeout=10,
            ) as websocket:
                self.websocket = websocket
                self.is_running = True

                logger.info("Connected to server!")

                # Initialize audio I/O
                self.recorder.start()
                self.player.start()

                # Start concurrent tasks
                tasks = [
                    asyncio.create_task(self.send_audio()),
                    asyncio.create_task(self.receive_audio()),
                    asyncio.create_task(self.player.play_loop()),
                ]

                # Run until all tasks complete or are cancelled
                await asyncio.gather(*tasks, return_exceptions=True)

        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        self.is_running = False
        self.recorder.stop()
        self.player.stop()
        logger.info("Client cleanup complete")


async def main():
    """Main entry point for the client application."""
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Voice Bot Client"
    )
    parser.add_argument(
        "--server",
        type=str,
        default=os.getenv("SERVER_URL", "ws://localhost:8765/ws"),
        help="WebSocket server URL (e.g., ws://192.168.1.100:8765/ws)",
    )

    args = parser.parse_args()

    logger.info("=== Raspberry Pi Voice Bot Client ===")
    logger.info(f"Server: {args.server}")
    logger.info(f"Sample Rate: {SAMPLE_RATE}Hz")
    logger.info(f"Channels: {CHANNELS} (Mono)")
    logger.info(f"Chunk Size: {CHUNK_SIZE} samples")
    logger.info("=====================================")

    # Create and run client
    client = VoiceBotClient(args.server)

    try:
        await client.connect_and_run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
