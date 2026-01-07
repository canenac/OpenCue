"""
OpenCue Backend - Main Entry Point

FastAPI application serving:
- REST API for dashboard
- WebSocket server for browser extension
- Static files for dashboard UI
"""

import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from websocket_server import start_websocket_server, stop_websocket_server

# Paths
BASE_DIR = Path(__file__).parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    print("[OpenCue] Starting backend...")
    websocket_task = asyncio.create_task(start_websocket_server())
    print("[OpenCue] WebSocket server started on ws://localhost:8765")
    print("[OpenCue] Dashboard available at http://localhost:8080")

    yield

    # Shutdown
    print("[OpenCue] Shutting down...")
    await stop_websocket_server()
    websocket_task.cancel()
    try:
        await websocket_task
    except asyncio.CancelledError:
        pass


# Create FastAPI app
app = FastAPI(
    title="OpenCue",
    description="Cue-based playback overlay system",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "opencue",
        "version": "0.1.0"
    }


# API endpoints
@app.get("/api/status")
async def get_status():
    """Get current backend status"""
    from websocket_server import get_connection_count
    return {
        "websocket_connections": get_connection_count(),
        "overlay_engine": "active"
    }


@app.get("/api/recent-events")
async def get_recent_events():
    """Get recent overlay events"""
    from overlay_engine import get_recent_events
    return {
        "events": get_recent_events()
    }


@app.get("/api/cues")
async def list_cue_files():
    """List available cue files"""
    from cue_manager import get_cue_manager
    manager = get_cue_manager()
    return {
        "cue_files": [
            {
                "id": Path(info.path).stem,
                "title": info.title,
                "duration_ms": info.duration_ms,
                "cue_count": info.cue_count,
                "has_fingerprints": info.has_fingerprints,
                "imdb_id": info.imdb_id
            }
            for info in manager.get_available()
        ]
    }


@app.get("/api/cues/{cue_id}")
async def get_cue_file(cue_id: str):
    """Get a specific cue file"""
    from cue_manager import get_cue_manager
    manager = get_cue_manager()
    data = manager.load(cue_id)
    if data:
        return data
    return {"error": "Cue file not found"}


@app.get("/api/cues/search/{query}")
async def search_cue_files(query: str):
    """Search for cue files"""
    from cue_manager import get_cue_manager
    manager = get_cue_manager()
    results = manager.search(query)
    return {
        "results": [
            {
                "id": Path(info.path).stem,
                "title": info.title,
                "cue_count": info.cue_count
            }
            for info in results
        ]
    }


@app.get("/api/sessions")
async def get_sessions():
    """Get active sync sessions"""
    from sync_session import get_session_manager
    manager = get_session_manager()
    return manager.get_stats()


@app.post("/api/cues/refresh")
async def refresh_cue_index():
    """Refresh the cue file index"""
    from cue_manager import get_cue_manager
    manager = get_cue_manager()
    manager.refresh_index()
    return {"status": "refreshed", "count": len(manager.get_available())}


# Dashboard static files
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")

    @app.get("/")
    async def serve_dashboard():
        """Serve dashboard index.html"""
        index_path = DASHBOARD_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "Dashboard not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )
