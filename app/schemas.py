"""
Pydantic schemas for API request/response validation
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    employee = "employee"


# ============================================================
# AUTH SCHEMAS
# ============================================================

class UserRegister(BaseModel):
    """Registration request"""
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)


class UserLogin(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class TokenData(BaseModel):
    """Decoded token payload"""
    user_id: str
    email: str
    role: UserRole


class UserResponse(BaseModel):
    """User data response (no password)"""
    id: str
    email: str
    name: str
    role: UserRole
    is_active: bool
    is_approved: bool = True  # False for pending approval
    created_at: datetime

    class Config:
        from_attributes = True


class UserInDB(BaseModel):
    """User stored in database"""
    id: str
    email: str
    name: str
    password_hash: str
    role: UserRole
    is_active: bool
    is_approved: bool = True  # False for pending approval
    created_at: datetime


class UserApprovalAction(BaseModel):
    """Admin action on user approval"""
    user_id: str


# ============================================================
# ACTIVITY LOG SCHEMAS
# ============================================================

class ActivityLogCreate(BaseModel):
    """Single activity log from extension"""
    url: str
    domain: str
    title: str
    start_time: int  # Unix timestamp ms
    end_time: int
    duration_seconds: int
    is_idle: bool = False


class ActivityLogBatch(BaseModel):
    """Batch of logs from extension"""
    logs: list[ActivityLogCreate]


class ActivityLogResponse(BaseModel):
    """Activity log response"""
    id: int
    user_id: str
    domain: str
    title: str
    start_time: datetime
    end_time: datetime
    duration_seconds: int
    is_idle: bool
    category: Optional[str] = None

    class Config:
        from_attributes = True


# ============================================================
# HEARTBEAT SCHEMAS
# ============================================================

class Heartbeat(BaseModel):
    """Heartbeat from extension"""
    current_domain: Optional[str] = None
    current_title: Optional[str] = None


class OnlineUser(BaseModel):
    """Online user status"""
    user_id: str
    email: str
    name: str
    current_domain: Optional[str]
    last_seen: datetime


# ============================================================
# DESKTOP APP LOG SCHEMAS
# ============================================================

class DesktopLogCreate(BaseModel):
    """Single activity log from desktop agent"""
    timestamp: str  # ISO format timestamp
    app_name: str
    window_title: Optional[str] = ""
    mouse_count: int = 0
    key_count: int = 0
    is_idle: bool = False
    session_id: Optional[str] = None


class DesktopLogBatch(BaseModel):
    """Batch of logs from desktop agent"""
    logs: list[DesktopLogCreate]


class SyncResponse(BaseModel):
    """Response for sync endpoint"""
    success: bool
    synced_count: int
    message: str
