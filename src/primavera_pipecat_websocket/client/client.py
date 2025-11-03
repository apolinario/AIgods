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
import json
import os
import struct
import wave
from collections import deque
from typing import Optional

import numpy as np
import pyaudio
import websockets
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file
load_dotenv()

# Audio configuration
INPUT_SAMPLE_RATE = 16000   # 16kHz for microphone input
OUTPUT_SAMPLE_RATE = 24000  # 24kHz for speaker output (matches VibeVoice)
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
        self._callback_data = b""

    def _callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback for continuous playback."""
        bytes_needed = frame_count * CHANNELS * BYTES_PER_SAMPLE

        # Get audio from queue
        while len(self._callback_data) < bytes_needed and self.playback_queue:
            self._callback_data += self.playback_queue.popleft()

        # Extract what we need
        if len(self._callback_data) >= bytes_needed:
            output = self._callback_data[:bytes_needed]
            self._callback_data = self._callback_data[bytes_needed:]
        else:
            # Not enough data - pad with silence
            output = self._callback_data + (b'\x00' * (bytes_needed - len(self._callback_data)))
            self._callback_data = b""

        return (output, pyaudio.paContinue)

    def start(self):
        """Initialize audio output stream with callback for smooth playback."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,  # Use 24kHz for VibeVoice output
            output=True,
            frames_per_buffer=1024,
            stream_callback=self._callback,  # Use callback mode for proper timing
        )
        self.stream.start_stream()
        logger.info(f"Audio playback initialized at {OUTPUT_SAMPLE_RATE}Hz with callback")

    def add_audio(self, audio_data: bytes):
        """Add audio data to playback queue."""
        self.playback_queue.append(audio_data)

    async def play_loop(self):
        """Keep alive while playing (callback handles actual playback)."""
        self.is_playing = True
        logger.info("Audio playback active (callback-driven)")

        # Just keep the coroutine alive - callback handles playback
        while self.is_playing:
            await asyncio.sleep(0.1)

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
            rate=INPUT_SAMPLE_RATE,  # Use 16kHz for microphone input
            input=True,
            frames_per_buffer=CHUNK_SIZE,
        )
        logger.info(f"Audio recording initialized at {INPUT_SAMPLE_RATE}Hz")

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
        self.bot_is_speaking = False  # Track when bot is speaking to mute mic

    async def send_audio(self):
        """Continuously capture and send audio to server."""
        logger.info("Starting audio transmission...")

        while self.is_running:
            try:
                # Read audio chunk from microphone
                audio_chunk = self.recorder.read_chunk()

                if audio_chunk and self.websocket:
                    # Send raw audio bytes to server
                    await self.websocket.send(audio_chunk)

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
                    # Receive message from server
                    message = await self.websocket.recv()

                    if isinstance(message, bytes):
                        # Check message type by prefix
                        if message.startswith(b"AUDIO:"):
                            # Audio data
                            audio_data = message[6:]  # Skip "AUDIO:" prefix
                            logger.debug(f"Received audio chunk: {len(audio_data)} bytes")
                            self.player.add_audio(audio_data)

                        elif message.startswith(b"LOG:"):
                            # Log message
                            log_data = message[4:].decode("utf-8")
                            log_msg = json.loads(log_data)

                            if log_msg["type"] == "transcription":
                                logger.info(f"📝 Transcription: {log_msg['text']}")
                            elif log_msg["type"] == "text":
                                logger.info(f"💬 Bot: {log_msg['text']}")

                        else:
                            # Fallback: treat as raw audio (backward compatibility)
                            logger.debug(f"Received raw audio: {len(message)} bytes")
                            self.player.add_audio(message)

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
    logger.info(f"Input Sample Rate: {INPUT_SAMPLE_RATE}Hz")
    logger.info(f"Output Sample Rate: {OUTPUT_SAMPLE_RATE}Hz")
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
