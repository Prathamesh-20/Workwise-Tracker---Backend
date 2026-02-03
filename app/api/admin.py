"""
Admin API endpoints for user management and approval workflow
Now uses database storage for persistence
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import UserResponse, UserRole, TokenData
from app.auth import get_current_user
from app.database import get_db
from app.users import (
    get_all_users_async,
    get_user_by_id_async,
    delete_user_async,
)


router = APIRouter()


def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    """Dependency to require admin role"""
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return current_user


# =============================================================
# PENDING APPROVALS (simplified - all DB users are approved)
# =============================================================

@router.get("/admin/pending-users", response_model=list[UserResponse])
async def get_pending_users(
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all users pending approval (admin only)"""
    # For now, return empty - all database users are considered approved
    return []


@router.post("/admin/approve-user/{user_id}")
async def approve_user(
    user_id: str, 
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Approve a pending user (admin only)"""
    user = await get_user_by_id_async(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Users in DB are already approved
    return {
        "success": True,
        "message": f"User {user.email} approved successfully",
        "user": UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_active=user.is_active,
            is_approved=user.is_approved,
            created_at=user.created_at
        )
    }


@router.post("/admin/reject-user/{user_id}")
async def reject_user(
    user_id: str, 
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reject (delete) a pending user (admin only)"""
    success = await delete_user_async(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "message": "User rejected and removed"}


# =============================================================
# EMPLOYEE MANAGEMENT
# =============================================================

@router.get("/admin/employees", response_model=list[UserResponse])
async def get_all_employees(
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all approved employees (admin only)"""
    all_users = await get_all_users_async(db)
    return [UserResponse(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        is_active=u.is_active,
        is_approved=u.is_approved,
        created_at=u.created_at
    ) for u in all_users if u.is_approved]


@router.delete("/admin/delete-user/{user_id}")
async def delete_user(
    user_id: str, 
    admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user (admin only)"""
    # Prevent admin from deleting themselves
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    success = await delete_user_async(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "message": "User deleted successfully"}
