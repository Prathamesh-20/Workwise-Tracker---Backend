"""
Activity logs API endpoints - Batch 6
"""

from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
from typing import Optional

from app.schemas import (
    ActivityLogBatch,
    ActivityLogCreate,
    TokenData,
)
from app.auth import get_current_user, get_admin_user

router = APIRouter()

# In-memory log storage (replaced with DB in Batch 7)
_activity_logs: list[dict] = []


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def receive_log_batch(
    data: ActivityLogBatch,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Receive a batch of activity logs from extension.
    """
    received_count = 0
    
    for log in data.logs:
        log_entry = {
            "id": len(_activity_logs) + 1,
            "user_id": current_user.user_id,
            "user_email": current_user.email,
            "url": log.url,
            "domain": log.domain,
            "title": log.title,
            "start_time": datetime.fromtimestamp(log.start_time / 1000, tz=timezone.utc),
            "end_time": datetime.fromtimestamp(log.end_time / 1000, tz=timezone.utc),
            "duration_seconds": log.duration_seconds,
            "is_idle": log.is_idle,
            "category": None,  # Set in Batch 8
            "created_at": datetime.now(timezone.utc),
        }
        _activity_logs.append(log_entry)
        received_count += 1
    
    print(f"📥 Received {received_count} logs from {current_user.email}")
    
    return {
        "received": received_count,
        "total_stored": len(_activity_logs),
    }


@router.get("/me")
async def get_my_logs(
    current_user: TokenData = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0,
):
    """
    Get current user's activity logs.
    """
    user_logs = [
        log for log in _activity_logs 
        if log["user_id"] == current_user.user_id
    ]
    
    # Sort by start_time descending
    user_logs.sort(key=lambda x: x["start_time"], reverse=True)
    
    return {
        "total": len(user_logs),
        "logs": user_logs[offset:offset + limit],
    }


@router.get("/user/{user_id}")
async def get_user_logs(
    user_id: str,
    admin: TokenData = Depends(get_admin_user),
    limit: int = 100,
    offset: int = 0,
):
    """
    Get logs for a specific user (Admin only).
    """
    user_logs = [
        log for log in _activity_logs 
        if log["user_id"] == user_id
    ]
    
    user_logs.sort(key=lambda x: x["start_time"], reverse=True)
    
    return {
        "total": len(user_logs),
        "logs": user_logs[offset:offset + limit],
    }


@router.get("/all")
async def get_all_logs(
    admin: TokenData = Depends(get_admin_user),
    limit: int = 100,
    offset: int = 0,
):
    """
    Get all logs (Admin only).
    """
    sorted_logs = sorted(_activity_logs, key=lambda x: x["start_time"], reverse=True)
    
    return {
        "total": len(_activity_logs),
        "logs": sorted_logs[offset:offset + limit],
    }
