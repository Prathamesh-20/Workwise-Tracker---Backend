"""
Desktop Sync API - Handles activity log sync from desktop agents
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional

from app.database import get_db, async_session_maker
from app.models import DesktopActivityLog
from app.schemas import DesktopLogBatch, SyncResponse
from app.auth import decode_access_token
from app.users import get_user_by_id_async, cache_user

router = APIRouter()


class UserInfo:
    """Simple user info class for API responses."""
    def __init__(self, user_id: str, email: str, role: str, name: str = "", is_active: bool = True):
        self.id = user_id
        self.email = email
        self.role = role
        self.name = name
        self.is_active = is_active


async def get_user_from_token(
    authorization: Optional[str] = Header(None),
) -> UserInfo:
    """
    Extract and validate user from Authorization header.
    Expected format: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    try:
        # Extract token from "Bearer <token>"
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    # Verify the token
    token_data = decode_access_token(token)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    # Get user from database
    async with async_session_maker() as db:
        user = await get_user_by_id_async(db, token_data.user_id)
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        if not user.is_active:
            raise HTTPException(status_code=401, detail="User is deactivated")
        
        # Cache user for other operations
        cache_user(user)
        
        return UserInfo(
            user_id=user.id,
            email=user.email,
            role=user.role.value if hasattr(user.role, 'value') else user.role,
            name=user.name,
            is_active=user.is_active
        )


@router.post("/sync-logs", response_model=SyncResponse)
async def sync_desktop_logs(
    batch: DesktopLogBatch,
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Receive and store activity logs from desktop agent.
    
    The desktop agent sends batches of logs periodically (every 60 seconds).
    Logs are stored in the desktop_activity_logs table.
    
    Request body:
    ```json
    {
        "logs": [
            {
                "timestamp": "2025-01-15T12:00:00",
                "app_name": "Google Chrome",
                "window_title": "YouTube - Video Title",
                "mouse_count": 50,
                "key_count": 20,
                "is_idle": false,
                "session_id": "uuid-string"
            }
        ]
    }
    ```
    """
    if not batch.logs:
        return SyncResponse(
            success=True,
            synced_count=0,
            message="No logs to sync"
        )
    
    synced_count = 0
    errors = []
    
    for log in batch.logs:
        try:
            # Parse timestamp from ISO format
            try:
                timestamp = datetime.fromisoformat(log.timestamp.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.now()
            
            # Create new desktop activity log
            db_log = DesktopActivityLog(
                user_id=user.id,
                session_id=log.session_id,
                timestamp=timestamp,
                app_name=log.app_name,
                window_title=log.window_title or "",
                mouse_count=log.mouse_count,
                key_count=log.key_count,
                is_idle=log.is_idle
            )
            
            db.add(db_log)
            synced_count += 1
            
        except Exception as e:
            errors.append(str(e))
    
    # Commit all logs at once
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save logs: {str(e)}"
        )
    
    message = f"Successfully synced {synced_count} logs"
    if errors:
        message += f" ({len(errors)} errors)"
    
    return SyncResponse(
        success=True,
        synced_count=synced_count,
        message=message
    )


@router.get("/sync-status")
async def get_sync_status(
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get sync status for the current user.
    Returns count of logs synced today and total.
    """
    from sqlalchemy import func
    
    # Count total logs for user
    total_result = await db.execute(
        select(func.count(DesktopActivityLog.id))
        .where(DesktopActivityLog.user_id == user.id)
    )
    total_count = total_result.scalar() or 0
    
    # Count today's logs
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_result = await db.execute(
        select(func.count(DesktopActivityLog.id))
        .where(DesktopActivityLog.user_id == user.id)
        .where(DesktopActivityLog.timestamp >= today_start)
    )
    today_count = today_result.scalar() or 0
    
    # Get last sync time
    last_sync_result = await db.execute(
        select(DesktopActivityLog.created_at)
        .where(DesktopActivityLog.user_id == user.id)
        .order_by(DesktopActivityLog.created_at.desc())
        .limit(1)
    )
    last_sync = last_sync_result.scalar()
    
    return {
        "user_id": user.id,
        "total_logs": total_count,
        "today_logs": today_count,
        "last_sync": last_sync.isoformat() if last_sync else None
    }
