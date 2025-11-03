"""
FastAPI WebSocket Server for Pipecat Voice Bot

This server handles WebSocket connections from Raspberry Pi clients,
manages bot instances, and provides health check endpoints.
"""

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from bot import create_bot_instance, run_bot

load_dotenv(override=True)

# Track active bot connections
active_bots: Dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown tasks."""
    logger.info("Server starting up...")

    # Pre-load Whisper model during startup to avoid client timeouts
    from bot import get_whisper_service
    logger.info("Pre-loading Whisper model...")
    get_whisper_service()
    logger.info("Whisper model ready!")

    yield
    logger.info("Server shutting down...")

    # Cancel all active bot tasks
    for client_id, task in active_bots.items():
        logger.info(f"Cancelling bot task for client: {client_id}")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# Initialize FastAPI app
app = FastAPI(
    title="Pipecat Voice Bot WebSocket Server",
    description="WebSocket server for real-time voice interaction with AI",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint with server information."""
    return {
        "name": "Pipecat Voice Bot WebSocket Server",
        "status": "running",
        "active_connections": len(active_bots),
        "websocket_endpoint": "/ws",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "active_connections": len(active_bots),
    }


@app.get("/status")
async def get_status():
    """Get detailed status of active connections."""
    return {
        "active_connections": len(active_bots),
        "clients": list(active_bots.keys()),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for voice bot connections.

    This endpoint:
    1. Accepts WebSocket connections from clients
    2. Creates a bot instance with Pipecat pipeline
    3. Handles bidirectional audio streaming
    4. Manages disconnections and cleanup
    """
    await websocket.accept()

    client_id = f"{websocket.client.host}:{websocket.client.port}"
    logger.info(f"Client connected: {client_id}")

    try:
        # Create bot transport for this WebSocket connection
        transport = await create_bot_instance(websocket)

        # Start the bot pipeline in a background task
        bot_task = asyncio.create_task(run_bot(transport))
        active_bots[client_id] = bot_task

        logger.info(f"Bot started for client: {client_id}")

        # Wait for the bot task to complete
        await bot_task

    except WebSocketDisconnect:
        logger.info(f"Client disconnected normally: {client_id}")

    except asyncio.CancelledError:
        logger.info(f"Bot task cancelled for client: {client_id}")

    except Exception as e:
        logger.exception(f"Error in WebSocket connection for {client_id}: {e}")

    finally:
        # Cleanup
        if client_id in active_bots:
            active_bots[client_id].cancel()
            try:
                await active_bots[client_id]
            except asyncio.CancelledError:
                pass
            del active_bots[client_id]

        logger.info(f"Cleaned up bot for client: {client_id}")


@app.get("/clients/{client_id}/disconnect")
async def disconnect_client(client_id: str):
    """Manually disconnect a specific client."""
    if client_id in active_bots:
        active_bots[client_id].cancel()
        try:
            await active_bots[client_id]
        except asyncio.CancelledError:
            pass
        del active_bots[client_id]

        return JSONResponse(
            content={"status": "disconnected", "client_id": client_id}
        )
    else:
        return JSONResponse(
            content={"error": "Client not found", "client_id": client_id},
            status_code=404,
        )


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Pipecat Voice Bot WebSocket Server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8765")),
        help="Port to bind to (default: 8765)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )

    args = parser.parse_args()

    # Run the server
    import uvicorn
    import sys

    logger.info(f"Starting server on {args.host}:{args.port}")

    try:
        config = uvicorn.Config(
            "server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info",
            timeout_graceful_shutdown=1,  # Only wait 1 second for graceful shutdown
        )
        server = uvicorn.Server(config)
        server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
