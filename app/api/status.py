"""
Status and heartbeat API endpoints - Batch 6
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from typing import Dict

from app.schemas import Heartbeat, OnlineUser, TokenData
from app.auth import get_current_user, get_admin_user
from app.users import get_user_by_id

router = APIRouter()

# In-memory heartbeat storage (replaced with Redis in production)
# user_id -> { domain, title, last_seen }
_heartbeats: Dict[str, dict] = {}

# Consider user offline after 60 seconds
ONLINE_THRESHOLD_SECONDS = 60


@router.post("/heartbeat")
async def receive_heartbeat(
    data: Heartbeat,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Receive heartbeat from extension to track online status.
    """
    _heartbeats[current_user.user_id] = {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "current_domain": data.current_domain,
        "current_title": data.current_title,
        "last_seen": datetime.now(timezone.utc),
    }
    
    return {"status": "ok"}


@router.get("/online", response_model=list[OnlineUser])
async def get_online_users(
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get list of currently online users (Admin only).
    """
    now = datetime.now(timezone.utc)
    online_users = []
    
    for user_id, heartbeat in _heartbeats.items():
        time_diff = (now - heartbeat["last_seen"]).total_seconds()
        
        if time_diff <= ONLINE_THRESHOLD_SECONDS:
            user = get_user_by_id(user_id)
            online_users.append(OnlineUser(
                user_id=user_id,
                email=heartbeat["email"],
                name=user.name if user else "Unknown",
                current_domain=heartbeat["current_domain"],
                last_seen=heartbeat["last_seen"],
            ))
    
    return online_users


@router.get("/summary")
async def get_status_summary(
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get overall status summary (Admin only).
    """
    now = datetime.now(timezone.utc)
    online_count = 0
    
    for heartbeat in _heartbeats.values():
        time_diff = (now - heartbeat["last_seen"]).total_seconds()
        if time_diff <= ONLINE_THRESHOLD_SECONDS:
            online_count += 1
    
    return {
        "online_users": online_count,
        "total_heartbeats": len(_heartbeats),
        "threshold_seconds": ONLINE_THRESHOLD_SECONDS,
    }
