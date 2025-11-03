#!/usr/bin/env node
/**
 * Pipecat WebSocket Voice Client (JavaScript)
 *
 * Command-line voice client that connects to Pipecat WebSocket server.
 * Uses official Pipecat client library with proper Protobuf serialization.
 */

import { PipecatClient } from '@pipecat-ai/client-js';
import { WebSocketTransport, ProtobufFrameSerializer } from '@pipecat-ai/websocket-transport';
import { config } from 'dotenv';

// Load environment variables
config();

const SERVER_URL = process.env.SERVER_URL || 'ws://localhost:8765/ws';

console.log('=== Pipecat Voice Client ===');
console.log(`Server: ${SERVER_URL}`);
console.log('===========================');

// Create Pipecat client
const client = new PipecatClient({
  transport: new WebSocketTransport({
    uri: SERVER_URL,
    serializer: new ProtobufFrameSerializer(),
  }),
  enableMic: true,
  enableCam: false,
});

// Event handlers
client.on('connected', () => {
  console.log('✅ Connected to server!');
  console.log('🎤 Microphone active - start speaking...');
});

client.on('disconnected', () => {
  console.log('❌ Disconnected from server');
  process.exit(0);
});

client.on('error', (error) => {
  console.error('❌ Error:', error.message);
});

client.on('trackStarted', (track, participant) => {
  console.log(`🎵 Track started: ${track.kind} from ${participant?.name || 'bot'}`);
});

client.on('userTranscript', (data) => {
  if (data.final) {
    console.log(`👤 You: ${data.text}`);
  }
});

client.on('botTranscript', (data) => {
  console.log(`🤖 Bot: ${data.text}`);
});

// Handle shutdown
process.on('SIGINT', async () => {
  console.log('\n\n👋 Shutting down...');
  await client.disconnect();
  process.exit(0);
});

// Connect to server
async function main() {
  try {
    console.log('\n🔌 Connecting...');
    await client.connect();
  } catch (error) {
    console.error('❌ Connection failed:', error.message);
    process.exit(1);
  }
}

main();
