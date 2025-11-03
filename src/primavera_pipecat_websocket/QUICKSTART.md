# Quick Start Guide

Get up and running in 5 minutes!

## Prerequisites

- Python 3.10+ (server)
- Python 3.9+ (Raspberry Pi client)
- API keys ready (OpenAI, Google)
- VibeVoice server running

## Server Setup (30 seconds)

```bash
# Navigate to server directory
cd src/primavera_pipecat_websocket/server

# Create virtual environment and install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add your API keys

# Start server
python server.py
```

Server is now running at `ws://0.0.0.0:8765/ws`

## Client Setup (Raspberry Pi - 30 seconds)

```bash
# Navigate to client directory
cd src/primavera_pipecat_websocket/client

# Install system dependencies (Raspberry Pi only)
sudo apt-get install -y portaudio19-dev python3-pyaudio

# Create virtual environment and install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure server URL
cp .env.example .env
nano .env  # Set SERVER_URL to your server's IP

# Start client
python client.py
```

## Test It!

1. Server should show: `Client connected: [IP]:[PORT]`
2. Start speaking into the microphone
3. Bot will respond through the speaker

## Environment Variables Cheat Sheet

### Server (.env)

```bash
# Required
OPENAI_API_KEY=sk-...                        # Or use local Whisper
GOOGLE_API_KEY=AIza...
VIBEVOICE_BASE_URL=http://localhost:8000
VIBEVOICE_MODEL=your_model
VIBEVOICE_PATH=/path/to/voice.wav

# Optional
HOST=0.0.0.0
PORT=8765
```

### Client (.env)

```bash
SERVER_URL=ws://192.168.1.100:8765/ws   # Your server IP
```

## Common Issues

### "Cannot connect to server"
```bash
# On server machine, check it's accessible:
curl http://YOUR_SERVER_IP:8765/health

# Make sure firewall allows port 8765:
sudo ufw allow 8765
```

### "No audio devices found" (Raspberry Pi)
```bash
# Install PortAudio:
sudo apt-get install portaudio19-dev

# List available devices:
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)[\"name\"]}') for i in range(p.get_device_count())]"
```

### "VibeVoice connection failed"
```bash
# Check VibeVoice server is running:
curl http://YOUR_VIBEVOICE_SERVER:8000/health

# Check .env has correct VIBEVOICE_* variables
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize bot personality in `server/bot.py`
- Adjust audio parameters in `client/client.py`
- Enable interruption testing by talking while bot speaks

## Architecture Reminder

```
Raspberry Pi (client)  ──WebSocket──►  Server
    ↓                                    ↓
Microphone                          Whisper STT
    ↑                                    ↓
Speaker                             Gemini LLM
                                        ↓
                                   VibeVoice TTS
                                        ↓
                                   Smart Turn V3
```

All heavy processing happens on the server. The Raspberry Pi just streams audio in and out!
