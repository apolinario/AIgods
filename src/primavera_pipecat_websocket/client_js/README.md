# JavaScript Pipecat Client

Command-line voice client using the official Pipecat JavaScript library.

## Quick Start

```bash
# Install dependencies
npm install

# Configure server URL
cp .env.example .env
nano .env  # Set SERVER_URL=ws://100.79.41.86:8765/ws

# Run the client
npm start
```

## Features

- ✅ Official Pipecat client library
- ✅ Proper Protobuf serialization
- ✅ Automatic microphone access
- ✅ Real-time transcription display
- ✅ Command-line interface

## Usage

1. Make sure the server is running at the URL in `.env`
2. Run `npm start`
3. Allow microphone access when prompted
4. Start speaking - you'll see transcriptions and bot responses
5. Press `Ctrl+C` to quit

## Requirements

- Node.js 16+
- Microphone access
- WebSocket connection to Pipecat server

## Troubleshooting

**"Connection failed"**
- Check server is running: `curl http://100.79.41.86:8765/health`
- Verify SERVER_URL in `.env` is correct

**"Microphone not accessible"**
- Grant microphone permissions to your terminal/Node.js
- On macOS: System Preferences → Security & Privacy → Microphone
