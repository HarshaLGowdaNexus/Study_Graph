"""
Main FastAPI Application Entrypoint for StudyGraph.
Relies on Decision D04: Python with FastAPI.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routes.candidates import router as candidates_router
from backend.app.api.routes.dedupe import router as dedupe_router
from backend.app.api.routes.edges import router as edges_router
from backend.app.api.routes.topics import router as topics_router
from backend.app.api.routes.upload import router as upload_router
from backend.app.core.config import settings

app = FastAPI(
    title="StudyGraph API",
    description="Backend engine for StudyGraph: knowledge graphs, note ingestion, and grounded study chat.",
    version="0.1.0",
)

# Configure CORS so the React frontend (Vite) can communicate with this API
origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(upload_router, prefix="/api")
app.include_router(topics_router, prefix="/api")
app.include_router(dedupe_router, prefix="/api")
app.include_router(candidates_router)
app.include_router(edges_router)


@app.get("/", tags=["Health"])
def root_check():
    """
    Root endpoint confirming the API server is active.
    """
    return {
        "app": "StudyGraph API",
        "status": "healthy",
        "version": "0.1.0",
        "environment": settings.APP_ENV,
    }


@app.get("/health", tags=["Health"])
def health_check():
    """
    Health check endpoint for monitoring uptime.
    """
    return {"status": "ok"}

