"""Health check endpoints"""

from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available
    TODO: Add DB and Redis connectivity checks in Batch 6
    """
    return {
        "status": "ready",
        "checks": {
            "database": "pending",  # Will implement in Batch 7
            "redis": "pending",     # Will implement in Batch 6
        }
    }
