"""
Raspberry Pi Phone Client for Pipecat Voice Bot

This client integrates with a rotary phone:
1. Detects when phone is picked up/hung up via GPIO
2. Plays dial tone and ringback tones
3. Detects dialing (pulse counting)
4. Connects to voice bot server via WebSocket
5. Streams audio bidirectionally

GPIO Pin Configuration:
- Pin 21: Phone handle sensor (pickup/hangup detection)
- Pin 23: Dial pulse enable (start/stop dialing)
- Pin 24: Dial pulse input (pulse counting)
"""

import argparse
import asyncio
import os
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Optional

import numpy as np
import pyaudio
import websockets
from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env file
load_dotenv()

# GPIO imports
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available - running in test mode")

# Audio configuration
INPUT_SAMPLE_RATE = 16000   # 16kHz for microphone input
OUTPUT_SAMPLE_RATE = 24000  # 24kHz for speaker output (matches VibeVoice)
CHANNELS = 1
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2

# GPIO Pin definitions
PHONE_HANDLE_PIN = 21  # Phone handle sensor
PULSE_ENABLE_PIN = 23  # Dial pulse enable
PULSE_INPUT_PIN = 24   # Dial pulse count


class ToneGenerator:
    """Generates dial tone and ringback tone audio."""

    @staticmethod
    def generate_dial_tone(duration=3.0):
        """Generate continuous dial tone (350Hz + 440Hz)."""
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        tone1 = np.sin(2 * np.pi * 350 * t)
        tone2 = np.sin(2 * np.pi * 440 * t)
        dial_tone = (tone1 + tone2) * 0.3 * 32767
        return dial_tone.astype(np.int16)

    @staticmethod
    def generate_ringback_tone(duration=2.0):
        """Generate ringback tone (beep-beep pattern)."""
        sample_rate = SAMPLE_RATE

        # Generate two short beeps
        t_beep = np.linspace(0, 0.4, int(sample_rate * 0.4), False)
        beep1 = np.sin(2 * np.pi * 440 * t_beep)
        beep2 = np.sin(2 * np.pi * 480 * t_beep)
        beep = (beep1 + beep2) * 0.3

        # Add fade in/out
        fade_samples = int(0.01 * sample_rate)
        beep[:fade_samples] *= np.linspace(0, 1, fade_samples)
        beep[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        # Create silence
        silence = np.zeros(int(sample_rate * 1.2))

        # Combine: beep + beep + silence
        ringback = np.concatenate([beep, beep, silence])
        ringback_audio = (ringback * 32767).astype(np.int16)

        return ringback_audio


class AudioPlayer:
    """Handles audio playback through speakers."""

    def __init__(self, device_index=None):
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.device_index = device_index
        self.playback_queue = deque()
        self.is_playing = False
        self.tone_playing = False

    def start(self):
        """Initialize audio output stream."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,  # Use 24kHz for VibeVoice output
            output=True,
            output_device_index=self.device_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        logger.info(f"Audio playback initialized at {OUTPUT_SAMPLE_RATE}Hz (device: {self.device_index})")

    def play_tone_loop(self, tone_data: np.ndarray):
        """Play a tone in a loop (for dial tone)."""
        self.tone_playing = True

        def play_loop():
            while self.tone_playing:
                try:
                    self.stream.write(tone_data.tobytes())
                except Exception as e:
                    logger.error(f"Error playing tone: {e}")
                    break

        threading.Thread(target=play_loop, daemon=True).start()

    def stop_tone(self):
        """Stop playing looping tone."""
        self.tone_playing = False

    def play_tone_once(self, tone_data: np.ndarray):
        """Play a tone once (for ringback)."""
        try:
            self.stream.write(tone_data.tobytes())
        except Exception as e:
            logger.error(f"Error playing tone: {e}")

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
                await asyncio.sleep(0.01)

    def stop(self):
        """Stop audio playback and cleanup."""
        self.is_playing = False
        self.tone_playing = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()
        logger.info("Audio playback stopped")


class AudioRecorder:
    """Handles audio capture from microphone."""

    def __init__(self, device_index=None):
        self.audio = pyaudio.PyAudio()
        self.stream: Optional[pyaudio.Stream] = None
        self.device_index = device_index
        self.is_recording = False

    def start(self):
        """Initialize audio input stream."""
        self.stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,  # Use 16kHz for microphone input
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        logger.info(f"Audio recording initialized at {INPUT_SAMPLE_RATE}Hz (device: {self.device_index})")

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


class PhoneVoiceBotClient:
    """Main phone client with GPIO support."""

    def __init__(self, server_url: str, input_device=None, output_device=None):
        self.server_url = server_url
        self.recorder = AudioRecorder(device_index=input_device)
        self.player = AudioPlayer(device_index=output_device)
        self.tone_gen = ToneGenerator()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False

        # Phone state
        self.phone_active = False
        self.conversation_active = False
        self.dial_tone_playing = False
        self.ringback_playing = False

        # GPIO state
        self.last_phone_state = True
        self.last_pulse_enable_state = True
        self.last_pulse_state = True
        self.pulse_count = 0
        self.counting_active = False

        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            logger.info("GPIO initialized for phone interface")

    def _play_dial_tone(self):
        """Play dial tone in loop."""
        if self.dial_tone_playing:
            return

        self.dial_tone_playing = True
        logger.info("Playing dial tone...")

        dial_tone = self.tone_gen.generate_dial_tone(duration=3.0)
        self.player.play_tone_loop(dial_tone)

    def _stop_dial_tone(self):
        """Stop dial tone."""
        if self.dial_tone_playing:
            self.dial_tone_playing = False
            self.player.stop_tone()
            logger.info("Dial tone stopped")

    def _play_ringback_tone(self):
        """Play ringback tone in loop."""
        if self.ringback_playing:
            return

        self.ringback_playing = True
        logger.info("Playing ringback tone...")

        def play_loop():
            ringback = self.tone_gen.generate_ringback_tone()
            while self.ringback_playing and self.phone_active:
                try:
                    self.player.play_tone_once(ringback)
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error playing ringback: {e}")
                    break

        threading.Thread(target=play_loop, daemon=True).start()

    def _stop_ringback_tone(self):
        """Stop ringback tone."""
        if self.ringback_playing:
            self.ringback_playing = False
            logger.info("Ringback tone stopped")

    async def _handle_phone_pickup(self):
        """Handle phone pickup event."""
        logger.info("☎️ Phone picked up!")
        self.phone_active = True
        self._play_dial_tone()

    async def _handle_phone_hangup(self):
        """Handle phone hangup event."""
        logger.info("📞 Phone hung up!")
        self.phone_active = False
        self.conversation_active = False

        # Stop all tones
        self._stop_dial_tone()
        self._stop_ringback_tone()

        # Disconnect from server
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        logger.info("✅ System reset - ready for next pickup")

    async def _start_conversation(self):
        """Start conversation (triggered by dialing)."""
        if self.conversation_active:
            return

        self.conversation_active = True
        self._stop_dial_tone()

        logger.info("Starting conversation...")
        self._play_ringback_tone()

        # Connect to WebSocket server
        await self._connect_to_server()

    async def _connect_to_server(self):
        """Connect to WebSocket server and start audio streaming."""
        try:
            logger.info(f"Connecting to server at {self.server_url}...")

            self.websocket = await websockets.connect(
                self.server_url,
                ping_interval=20,
                ping_timeout=10,
            )

            logger.info("Connected to server!")
            self._stop_ringback_tone()

            # Initialize audio I/O
            self.recorder.start()
            if not self.player.stream:
                self.player.start()

            self.is_running = True

            # Start audio streaming tasks
            send_task = asyncio.create_task(self.send_audio())
            receive_task = asyncio.create_task(self.receive_audio())
            play_task = asyncio.create_task(self.player.play_loop())

            await asyncio.gather(send_task, receive_task, play_task, return_exceptions=True)

        except Exception as e:
            logger.error(f"Connection error: {e}")
            self._stop_ringback_tone()
            self.conversation_active = False

    async def send_audio(self):
        """Send audio to server."""
        logger.info("Starting audio transmission...")

        while self.is_running and self.conversation_active:
            try:
                audio_chunk = self.recorder.read_chunk()

                if audio_chunk and self.websocket:
                    # Send raw audio bytes to server
                    await self.websocket.send(audio_chunk)

                await asyncio.sleep(0.001)

            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                break

    async def receive_audio(self):
        """Receive audio from server."""
        logger.info("Starting audio reception...")

        while self.is_running and self.conversation_active:
            try:
                if self.websocket:
                    # Receive audio chunk from server
                    audio_chunk = await self.websocket.recv()

                    if isinstance(audio_chunk, bytes):
                        # Add to playback queue
                        self.player.add_audio(audio_chunk)

            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed by server")
                break
            except Exception as e:
                logger.error(f"Error receiving audio: {e}")
                break

    async def gpio_monitor_loop(self):
        """Monitor GPIO pins for phone events."""
        if not GPIO_AVAILABLE:
            logger.error("GPIO not available!")
            return

        logger.info("GPIO monitoring started")

        while True:
            try:
                phone_state = GPIO.input(PHONE_HANDLE_PIN)
                pulse_enable_state = GPIO.input(PULSE_ENABLE_PIN)
                pulse_state = GPIO.input(PULSE_INPUT_PIN)

                # Phone handle detection
                if self.last_phone_state == True and phone_state == False:
                    await self._handle_phone_pickup()
                elif self.last_phone_state == False and phone_state == True:
                    await self._handle_phone_hangup()

                # Pulse counting (dialing)
                if self.phone_active and not self.conversation_active:
                    # Start counting
                    if self.last_pulse_enable_state == True and pulse_enable_state == False:
                        logger.info("📞 Dialing started...")
                        self.counting_active = True
                        self.pulse_count = 0
                        self._stop_dial_tone()

                    # Stop counting and process
                    elif self.last_pulse_enable_state == False and pulse_enable_state == True:
                        if self.counting_active:
                            self.counting_active = False
                            dialed_number = self.pulse_count if self.pulse_count < 10 else 0
                            logger.info(f"Dialed: {dialed_number}")
                            await self._start_conversation()

                    # Count pulses
                    if self.counting_active:
                        if self.last_pulse_state == True and pulse_state == False:
                            self.pulse_count += 1
                            logger.info(f"Pulse {self.pulse_count}")

                # Update states
                self.last_phone_state = phone_state
                self.last_pulse_enable_state = pulse_enable_state
                self.last_pulse_state = pulse_state

                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"GPIO error: {e}")
                await asyncio.sleep(1)

    async def test_mode_loop(self):
        """Test loop for systems without GPIO."""
        logger.info("\nTest mode - keyboard commands:")
        logger.info("  p: Pick up phone")
        logger.info("  h: Hang up phone")
        logger.info("  d: Dial (start conversation)")
        logger.info("  q: Quit")

        while True:
            # Non-blocking input with asyncio
            cmd = await asyncio.to_thread(input, "\nCommand: ")
            cmd = cmd.strip().lower()

            if cmd == 'p':
                await self._handle_phone_pickup()
            elif cmd == 'h':
                await self._handle_phone_hangup()
            elif cmd == 'd':
                self._stop_dial_tone()
                await self._start_conversation()
            elif cmd == 'q':
                break

    def cleanup(self):
        """Cleanup resources."""
        self.is_running = False
        self.phone_active = False
        self.conversation_active = False

        self._stop_dial_tone()
        self._stop_ringback_tone()

        self.recorder.stop()
        self.player.stop()

        if GPIO_AVAILABLE:
            GPIO.cleanup()

        logger.info("Client cleanup complete")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Raspberry Pi Phone Voice Bot Client")
    parser.add_argument(
        "--server",
        type=str,
        default=os.getenv("SERVER_URL", "ws://localhost:8765/ws"),
        help="WebSocket server URL",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=int(os.getenv("AUDIO_INPUT_DEVICE", "-1")),
        help="Audio input device index (-1 for default)",
    )
    parser.add_argument(
        "--output-device",
        type=int,
        default=int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1")),
        help="Audio output device index (-1 for default)",
    )

    args = parser.parse_args()

    # Use None for default devices
    input_dev = None if args.input_device == -1 else args.input_device
    output_dev = None if args.output_device == -1 else args.output_device

    logger.info("=== Raspberry Pi Phone Voice Bot ===")
    logger.info(f"Server: {args.server}")
    logger.info(f"Input Device: {input_dev}")
    logger.info(f"Output Device: {output_dev}")
    logger.info(f"GPIO Available: {GPIO_AVAILABLE}")
    logger.info("====================================")

    # Create client
    client = PhoneVoiceBotClient(args.server, input_dev, output_dev)

    try:
        if GPIO_AVAILABLE:
            # Real phone mode with GPIO
            await client.gpio_monitor_loop()
        else:
            # Test mode without GPIO
            await client.test_mode_loop()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
