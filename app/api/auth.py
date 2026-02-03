"""
Authentication API endpoints - Batch 4
Now uses database storage for user persistence
"""

from fastapi import APIRouter, HTTPException, status, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas import (
    UserRegister,
    UserLogin,
    Token,
    UserResponse,
    UserRole,
    TokenData,
)
from app.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    get_admin_user,
)
from app.users import (
    create_user_async,
    get_user_by_email_async,
    get_user_by_id_async,
    user_exists_async,
    get_all_users_async,
    cache_user,
)
from app.database import get_db

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register a new employee account.
    Account will require admin approval before login.
    """
    # Check if user already exists
    if await user_exists_async(db, data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create the user with is_approved=False (pending admin approval)
    user = await create_user_async(
        db,
        email=data.email,
        password=data.password,
        name=data.name,
        role=UserRole.employee,
        is_approved=False  # Requires admin approval
    )
    
    # Add to cache for immediate use
    cache_user(user)

    return {
        "success": True,
        "message": "Registration successful! Your account is pending admin approval.",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }


@router.post("/login", response_model=Token)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Login with email and password.
    Returns JWT token on success.
    """
    # Find user from database
    user = await get_user_by_email_async(db, data.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Verify password
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Check if active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    # Check if approved (for employees)
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending approval. Please wait for admin to approve your registration."
        )
    
    # Add to cache for other operations
    cache_user(user)

    # Generate token
    token, expires_at = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role
    )

    return Token(
        access_token=token,
        token_type="bearer",
        expires_at=expires_at
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current authenticated user's info.
    """
    user = await get_user_by_id_async(db, current_user.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        is_approved=user.is_approved,
        created_at=user.created_at
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: TokenData = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all users (Admin only).
    """
    users = await get_all_users_async(db)
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            is_active=u.is_active,
            is_approved=u.is_approved,
            created_at=u.created_at
        )
        for u in users
    ]
