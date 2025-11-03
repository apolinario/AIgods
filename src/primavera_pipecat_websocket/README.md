# Primavera Phone Bot - Pipecat WebSocket Edition

A server-client voice bot architecture using Pipecat AI framework integrated with a rotary phone. The Raspberry Pi handles phone interface and audio I/O, while all heavy processing (Local Whisper STT, Gemini LLM with Cache, VibeVoice TTS, Smart Turn V3) happens on a powerful server.

**Based on:** `primavera_streaming_gemini_phone_vibevoice.py`

## Architecture

```
┌──────────────────────────┐         WebSocket          ┌─────────────────────┐
│   Raspberry Pi + Phone   │◄──────────────────────────►│   Server            │
│   (Client)               │                             │                     │
│                          │                             │  ┌──────────────┐   │
│  ┌────────────────┐      │    Raw Audio (16kHz)       │  │ Local Whisper│   │
│  │ Rotary Phone   │      │                             │  │ STT          │   │
│  │  - Handset     │──────┼────────────────────────────┼─►│              │   │
│  │  - Dial (GPIO) │      │                             │  └──────┬───────┘   │
│  │  - Microphone  │      │                             │         │           │
│  │  - Speaker     │◄─────┼────────────────────────────┼──┐      │           │
│  └────────────────┘      │    Processed Audio          │  │      │           │
│                          │                             │  │ ┌────▼────────┐  │
│  ┌────────────────┐      │                             │  │ │ Gemini 2.0  │  │
│  │ GPIO Pins      │      │                             │  │ │ + Cache     │  │
│  │  - Pin 21      │      │                             │  │ │ (Primavera) │  │
│  │  - Pin 23      │      │                             │  │ └────┬────────┘  │
│  │  - Pin 24      │      │                             │  │      │           │
│  └────────────────┘      │                             │  │ ┌────▼────────┐  │
│                          │                             │  │ │ VibeVoice   │  │
│  ┌────────────────┐      │                             │  │ │ TTS         │  │
│  │ Dial Tone      │      │                             │  │ └────┬────────┘  │
│  │ Ringback Tone  │      │                             │  │      │           │
│  └────────────────┘      │                             │  └──────┘           │
│                          │                             │                     │
│                          │                             │  ┌──────────────┐   │
│                          │                             │  │ Smart Turn   │   │
│                          │                             │  │ V3           │   │
│                          │                             │  └──────────────┘   │
└──────────────────────────┘                             └─────────────────────┘
```

## Features

- ✅ **Rotary Phone Integration**: Full GPIO support for vintage phone
- ✅ **Server-Side Processing**: All AI/ML processing on powerful server
- ✅ **Local Whisper STT**: On-device speech-to-text (no API costs)
- ✅ **Smart Turn V3**: Intelligent conversation turn-taking
- ✅ **Gemini 2.0 + Cache**: Primavera personality with cached context
- ✅ **VibeVoice TTS**: High-quality neural text-to-speech
- ✅ **Interruption Handling**: Interrupt the bot mid-speech
- ✅ **WebSocket Streaming**: Low-latency bidirectional audio
- ✅ **Phone Features**: Dial tone, ringback tone, pulse dialing
- ✅ **ConfigLoader**: Personality system from JSON config
- ✅ **Conversation Manager**: Full conversation history with Gemini cache

## Directory Structure

```
primavera_pipecat_websocket/
├── README.md                    # This file
├── QUICKSTART.md               # Quick setup guide
├── server/                      # Server-side code
│   ├── bot.py                  # Main bot pipeline with Gemini cache
│   ├── server.py               # FastAPI WebSocket server
│   ├── vibevoice_tts.py        # VibeVoice TTS service
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variables template
└── client/                      # Raspberry Pi client code
    ├── phone_client.py         # Phone client with GPIO support
    ├── client.py               # Simple audio client (no GPIO)
    ├── requirements.txt        # Python dependencies
    └── .env.example            # Environment variables template

Shared modules (imported from parent src/):
├── config_loader.py            # Personality configuration system
├── conversation_manager.py     # Gemini conversation with cache
└── gemini_cache.py            # Gemini cache management
```

## Prerequisites

### Server Requirements

- Python 3.10+
- 4GB+ RAM (8GB+ recommended)
- GPU optional (CPU works fine for this setup)
- Linux/macOS/Windows

### Client (Raspberry Pi) Requirements

- Raspberry Pi 3 or newer
- USB microphone
- Speaker (3.5mm jack or USB)
- Python 3.9+
- Internet connection

### API Keys & Services

You'll need:

1. **Google API Key** (for Gemini LLM with caching)
   - Get from: https://aistudio.google.com/app/apikey
   - Used for: Primavera personality with cached context

2. **VibeVoice Server** (for TTS)
   - Set up your own VibeVoice server
   - No API key needed if self-hosted

3. **Local Whisper** (for STT)
   - No API key needed - runs locally on server
   - Model auto-downloads on first run

### Hardware (Raspberry Pi)

For rotary phone integration:
- Rotary phone with pulse dialing
- GPIO connections (pins 21, 23, 24)
- USB microphone (or phone handset wired to USB audio)
- Speaker output (3.5mm jack or USB)

## Installation

### Server Setup

1. **Clone and navigate to server directory:**
   ```bash
   cd src/primavera_pipecat_websocket/server
   ```

2. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your API keys
   ```

   Required variables:
   ```bash
   GOOGLE_API_KEY=AIza...
   VIBEVOICE_BASE_URL=http://your-vibevoice-server:8000
   VIBEVOICE_MODEL=your_model_name
   VIBEVOICE_PATH=/path/to/voice.wav
   WHISPER_MODEL=base
   ```

5. **Run the server:**
   ```bash
   python server.py
   ```

   The server will start on `ws://0.0.0.0:8765/ws`

   **Optional flags:**
   ```bash
   python server.py --host 0.0.0.0 --port 8765 --reload
   ```

### Client Setup (Raspberry Pi)

1. **Clone and navigate to client directory:**
   ```bash
   cd src/primavera_pipecat_websocket/client
   ```

2. **Install system dependencies (Raspberry Pi):**
   ```bash
   sudo apt-get update
   sudo apt-get install portaudio19-dev python3-pyaudio
   ```

3. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure server URL:**
   ```bash
   cp .env.example .env
   nano .env
   ```

   Set your server's IP:
   ```bash
   SERVER_URL=ws://192.168.1.100:8765/ws
   ```

6. **Test audio devices:**
   ```bash
   python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)[\"name\"]}') for i in range(p.get_device_count())]"
   ```

7. **Run the client:**

   **For rotary phone (with GPIO):**
   ```bash
   python phone_client.py
   ```

   **For simple audio client (no phone):**
   ```bash
   python client.py --server ws://192.168.1.100:8765/ws
   ```

   **With custom audio devices:**
   ```bash
   python phone_client.py --input-device 2 --output-device 1
   ```

## Configuration

### Whisper Model Selection (Server)

Local Whisper is used by default. Adjust the model size in `.env`:

```bash
WHISPER_MODEL=base  # Options: tiny, base, small, medium, large
```

**Model comparison:**
- `tiny`: Fastest, lowest accuracy (~1GB RAM)
- `base`: Good balance (default) (~1GB RAM)
- `small`: Better accuracy (~2GB RAM)
- `medium`: High accuracy (~5GB RAM)
- `large`: Best accuracy (~10GB RAM)

### Phone GPIO Wiring

Connect your rotary phone to Raspberry Pi GPIO:

```
Phone Component          →  GPIO Pin
─────────────────────────────────────
Handset Switch (pickup)  →  Pin 21 (BCM)
Dial Pulse Enable        →  Pin 23 (BCM)
Dial Pulse Counter       →  Pin 24 (BCM)
Ground                   →  GND
```

### Adjusting Smart Turn Sensitivity

Edit `bot.py` in the server:

```python
turn_analyzer=LocalSmartTurnAnalyzerV3(
    # Adjust these parameters for turn detection
    # (check Pipecat docs for available options)
)
```

### Audio Configuration

**Server (in bot.py):**
```python
params=FastAPIWebsocketParams(
    audio_in_enabled=True,
    audio_out_enabled=True,
    vad_analyzer=SileroVADAnalyzer(
        params=VADParams(stop_secs=0.3)  # Adjust VAD sensitivity
    ),
    # ... other params
)
```

**Client (in client.py):**
```python
SAMPLE_RATE = 16000  # Audio sample rate
CHANNELS = 1         # Mono audio
CHUNK_SIZE = 1024    # Samples per chunk
```

## Usage

### Starting the System

1. **Start the server** (on your powerful machine):
   ```bash
   cd server
   source venv/bin/activate
   python server.py
   ```

2. **Start the phone client** (on Raspberry Pi):
   ```bash
   cd client
   source venv/bin/activate
   python phone_client.py
   ```

### Using the Phone

1. **Pick up the phone** - You'll hear a dial tone
2. **Dial any number** (1-9, 0) - Dial tone stops, ringback tone plays
3. **Wait for connection** - Ringback stops when bot is ready
4. **Talk to Primavera!** The bot will:
   - Transcribe your speech with local Whisper
   - Generate responses using Gemini + Primavera's cached personality
   - Synthesize speech with VibeVoice
   - Stream audio back through the phone
5. **Hang up** - Conversation ends, system resets

### Test Mode (No GPIO)

If running without GPIO (testing on laptop):

```bash
python phone_client.py
```

Commands:
- `p` - Pick up phone
- `d` - Dial (start conversation)
- `h` - Hang up
- `q` - Quit

### Interrupting the Bot

Simply start speaking while the bot is talking - the interruption handler will:
- Detect that you've started speaking
- Stop the bot's current response
- Process your new input

## Monitoring

### Server Logs

The server provides detailed logging:
```
INFO - Client connected: 192.168.1.50:12345
INFO - Bot started for client: 192.168.1.50:12345
INFO - VibeVoice stream started: 24000Hz
DEBUG - VibeVoice TTS request: Hello, how can I help you?
INFO - Smart Turn: COMPLETE, Probability: 95.3%, Inference: 12.5ms
```

### Server Endpoints

- `GET /` - Server info and status
- `GET /health` - Health check
- `GET /status` - Active connections
- `WS /ws` - WebSocket endpoint for clients
- `GET /clients/{client_id}/disconnect` - Manually disconnect a client

### Checking Server Status

```bash
curl http://localhost:8765/
curl http://localhost:8765/health
curl http://localhost:8765/status
```

## Troubleshooting

### Server Issues

**Q: "Module not found" errors**
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Q: VibeVoice connection fails**
```bash
# Check VibeVoice server is running
curl http://your-vibevoice-server:8000/health

# Check .env configuration
cat .env | grep VIBEVOICE
```

**Q: Whisper is slow**
- Use smaller model: `model="tiny"` or `model="base"`
- Or use OpenAI API instead of local Whisper

### Client Issues

**Q: No audio devices found**
```bash
# List audio devices
python -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)}') for i in range(p.get_device_count())]"

# Install PortAudio
sudo apt-get install portaudio19-dev
```

**Q: Cannot connect to server**
```bash
# Test server connectivity
ping 192.168.1.100

# Test WebSocket endpoint
curl http://192.168.1.100:8765/health
```

**Q: Audio choppy or delayed**
- Reduce `CHUNK_SIZE` in client.py
- Check network latency: `ping -c 10 your-server-ip`
- Ensure good WiFi signal on Raspberry Pi

### Network Issues

**Q: Server not accessible from other machines**
```bash
# Check firewall allows port 8765
sudo ufw allow 8765

# Or on the server, bind to all interfaces
python server.py --host 0.0.0.0 --port 8765
```

## Performance Tips

### Server Optimization

1. **Use GPU for Whisper** (if available):
   ```python
   stt = WhisperSTTService(model="base", device="cuda")
   ```

2. **Adjust VAD parameters** for faster turn detection:
   ```python
   VADParams(stop_secs=0.2)  # Faster response
   ```

3. **Use smaller Gemini model** if speed is critical:
   ```python
   llm = GoogleLLMService(model="gemini-1.5-flash")
   ```

### Client Optimization

1. **Use wired ethernet** instead of WiFi on Raspberry Pi
2. **Reduce chunk size** for lower latency (at cost of CPU)
3. **Close other applications** on Raspberry Pi

## Advanced Usage

### Running on Remote Server

To run the server on a cloud instance:

1. **Set up firewall rules** to allow port 8765
2. **Use HTTPS/WSS** in production (not WS)
3. **Configure reverse proxy** (nginx/caddy) for SSL:
   ```nginx
   location /ws {
       proxy_pass http://localhost:8765;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

### Using with Multiple Clients

The server supports multiple concurrent clients. Each client gets its own bot instance.

### Customizing the Bot Personality

Edit the system message in `bot.py`:

```python
messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant specializing in [your domain]. "
                   "Keep responses concise and natural for voice conversation."
    },
]
```

## Credits

- **Pipecat AI**: https://github.com/pipecat-ai/pipecat
- **Whisper**: OpenAI speech recognition
- **Gemini**: Google's LLM
- **VibeVoice**: Neural TTS
- **Smart Turn V3**: Turn-taking detection

## License

See the project root for license information.
