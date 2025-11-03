"""
Simple Pipecat WebSocket Client (No GPIO)

This is a minimal client that works with Pipecat's WebSocket server.
For phone integration with GPIO, use phone_client.py instead.
"""

import argparse
import asyncio
import os
from dotenv import load_dotenv
from loguru import logger

# Import Pipecat client libraries
try:
    from pipecat_client import PipecatClient
    from pipecat_client.transports.websocket import WebSocketTransport
    from pipecat_client.serializers.protobuf import ProtobufFrameSerializer

    PIPECAT_CLIENT_AVAILABLE = True
except ImportError:
    PIPECAT_CLIENT_AVAILABLE = False
    logger.error("Pipecat client libraries not available!")
    logger.error("Install with: pip install pipecat-client websockets")

load_dotenv()


async def main():
    """Main entry point."""
    if not PIPECAT_CLIENT_AVAILABLE:
        logger.error("Cannot run without pipecat-client. Exiting.")
        return

    parser = argparse.ArgumentParser(description="Simple Voice Bot Client")
    parser.add_argument(
        "--server",
        type=str,
        default=os.getenv("SERVER_URL", "ws://localhost:8765/ws"),
        help="WebSocket server URL",
    )

    args = parser.parse_args()

    logger.info("=== Simple Voice Bot Client ===")
    logger.info(f"Server: {args.server}")
    logger.info("===============================")

    # Create Pipecat client
    client = PipecatClient(
        transport=WebSocketTransport(
            url=args.server,
            serializer=ProtobufFrameSerializer(),
        ),
        enable_mic=True,
        enable_cam=False,
    )

    try:
        # Connect and run
        logger.info("Connecting to server...")
        await client.connect()
        logger.info("Connected! Start speaking...")

        # Keep running until interrupted
        while client.is_connected():
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await client.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
