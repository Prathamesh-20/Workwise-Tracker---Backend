"""
Database-backed user store
Persists across backend restarts
"""

from datetime import datetime, timezone
from typing import Optional, List
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User as DBUser
from app.schemas import UserInDB, UserRole
from app.auth import hash_password
from app.database import async_session_maker


# ============================================================
# ASYNC DATABASE OPERATIONS
# ============================================================

async def create_user_async(
    db: AsyncSession,
    email: str, 
    password: str, 
    name: str, 
    role: UserRole = UserRole.employee, 
    is_approved: bool = True
) -> UserInDB:
    """Create a new user in database"""
    user_id = str(uuid.uuid4())
    
    db_user = DBUser(
        id=user_id,
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role.value,
        is_active=True,
    )
    
    db.add(db_user)
    await db.flush()
    
    return UserInDB(
        id=user_id,
        email=email.lower(),
        name=name,
        password_hash=db_user.password_hash,
        role=role,
        is_active=True,
        is_approved=is_approved,
        created_at=db_user.created_at,
    )


async def get_user_by_id_async(db: AsyncSession, user_id: str) -> Optional[UserInDB]:
    """Get user by ID from database"""
    result = await db.execute(select(DBUser).where(DBUser.id == user_id))
    db_user = result.scalar_one_or_none()
    
    if db_user:
        return _db_user_to_schema(db_user)
    return None


async def get_user_by_email_async(db: AsyncSession, email: str) -> Optional[UserInDB]:
    """Get user by email from database"""
    result = await db.execute(select(DBUser).where(DBUser.email == email.lower()))
    db_user = result.scalar_one_or_none()
    
    if db_user:
        return _db_user_to_schema(db_user)
    return None


async def get_all_users_async(db: AsyncSession) -> List[UserInDB]:
    """Get all users from database"""
    result = await db.execute(select(DBUser))
    db_users = result.scalars().all()
    return [_db_user_to_schema(u) for u in db_users]


async def user_exists_async(db: AsyncSession, email: str) -> bool:
    """Check if user exists by email"""
    result = await db.execute(select(DBUser.id).where(DBUser.email == email.lower()))
    return result.scalar_one_or_none() is not None


async def get_approved_users_async(db: AsyncSession) -> List[UserInDB]:
    """Get all approved/active users"""
    result = await db.execute(select(DBUser).where(DBUser.is_active == True))
    db_users = result.scalars().all()
    return [_db_user_to_schema(u) for u in db_users]


async def delete_user_async(db: AsyncSession, user_id: str) -> bool:
    """Delete a user"""
    result = await db.execute(select(DBUser).where(DBUser.id == user_id))
    db_user = result.scalar_one_or_none()
    
    if db_user:
        await db.delete(db_user)
        return True
    return False


def _db_user_to_schema(db_user: DBUser) -> UserInDB:
    """Convert database model to Pydantic schema"""
    return UserInDB(
        id=db_user.id,
        email=db_user.email,
        name=db_user.name,
        password_hash=db_user.password_hash,
        role=UserRole(db_user.role),
        is_active=db_user.is_active,
        is_approved=True,  # All DB users are approved
        created_at=db_user.created_at,
    )


# ============================================================
# SYNCHRONOUS WRAPPERS (for backwards compatibility)
# These use a new session for each call
# ============================================================

import asyncio

def _run_async(coro):
    """Run async function from sync context"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop:
        # Already in async context - create a task
        return asyncio.ensure_future(coro)
    else:
        # Not in async context - run in new loop
        return asyncio.run(coro)


# ============================================================
# STARTUP INITIALIZATION
# ============================================================

async def create_default_users_async():
    """Create default admin user if it doesn't exist"""
    async with async_session_maker() as db:
        try:
            # Check and create admin only
            if not await user_exists_async(db, "admin@company.com"):
                await create_user_async(
                    db,
                    email="admin@company.com",
                    password="admin123",
                    name="Admin User",
                    role=UserRole.admin
                )
                print("📧 Default admin created: admin@company.com")
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"⚠️ Error creating default admin: {e}")


# ============================================================
# LEGACY SYNC API (for existing code compatibility)
# These maintain backwards compatibility with auth.py, etc.
# ============================================================

# In-memory cache for current session (performance optimization)
_user_cache = {}

def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Sync wrapper - get user by email (uses cache first)"""
    email = email.lower()
    if email in _user_cache:
        return _user_cache[email]
    return None  # Will be populated by auth flow


def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """Sync wrapper - get user by id"""
    for user in _user_cache.values():
        if user.id == user_id:
            return user
    return None


def user_exists(email: str) -> bool:
    """Sync check if user exists in cache"""
    return email.lower() in _user_cache


def cache_user(user: UserInDB):
    """Add user to in-memory cache"""
    _user_cache[user.email.lower()] = user


def get_all_users() -> list[UserInDB]:
    """Get all cached users"""
    return list(_user_cache.values())


# Note: For backwards compatibility, we also keep create_user sync
# but it should NOT be called - use create_user_async instead
def create_user(email: str, password: str, name: str, role: UserRole = UserRole.employee, is_approved: bool = True) -> UserInDB:
    """Legacy sync create - creates in cache only (temporary during migration)"""
    user_id = str(uuid.uuid4())
    
    user = UserInDB(
        id=user_id,
        email=email.lower(),
        name=name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        is_approved=is_approved,
        created_at=datetime.now(timezone.utc),
    )
    
    _user_cache[email.lower()] = user
    return user
