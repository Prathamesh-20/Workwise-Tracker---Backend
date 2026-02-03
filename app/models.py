"""
SQLAlchemy Models - Batch 7
All database tables for the Employee Tracker
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Integer, BigInteger, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.database import Base


# ============================================================
# USER MODEL
# ============================================================

class User(Base):
    """User account (admin or employee)"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), 
        primary_key=True, 
        default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="employee")  # admin, employee
    team_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("teams.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    team: Mapped[Optional["Team"]] = relationship("Team", back_populates="members")
    activity_logs: Mapped[list["ActivityLog"]] = relationship("ActivityLog", back_populates="user")
    work_sessions: Mapped[list["WorkSession"]] = relationship("WorkSession", back_populates="user")


# ============================================================
# TEAM MODEL
# ============================================================

class Team(Base):
    """Team grouping for employees"""
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    manager_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    members: Mapped[list["User"]] = relationship("User", back_populates="team")


# ============================================================
# ACTIVITY LOG MODEL
# ============================================================

class ActivityLog(Base):
    """Individual activity log entry"""
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    
    # Activity data
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Timing
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Categorization
    is_idle: Mapped[bool] = mapped_column(Boolean, default=False)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="activity_logs")
    category: Mapped[Optional["Category"]] = relationship("Category")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_activity_user_time", "user_id", "start_time"),
        Index("ix_activity_domain", "domain"),
    )


# ============================================================
# CATEGORY MODEL
# ============================================================

class Category(Base):
    """Productivity category (Productive, Distraction, Neutral)"""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # productive, distraction, neutral
    color: Mapped[str] = mapped_column(String(7), default="#808080")  # Hex color
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# DOMAIN RULE MODEL
# ============================================================

class DomainRule(Base):
    """Rule to categorize domains"""
    __tablename__ = "domain_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_pattern: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"), nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=True)  # Applies to all users
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    category: Mapped["Category"] = relationship("Category")


# ============================================================
# WORK SESSION MODEL
# ============================================================

class WorkSession(Base):
    """Work session (start/stop tracking)"""
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_active_seconds: Mapped[int] = mapped_column(Integer, default=0)
    total_idle_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="work_sessions")


# ============================================================
# HEARTBEAT MODEL
# ============================================================

class Heartbeat(Base):
    """Real-time heartbeat for online status (consider Redis for production)"""
    __tablename__ = "heartbeats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    current_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    current_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )


# ============================================================
# DESKTOP ACTIVITY LOG MODEL
# ============================================================

class DesktopActivityLog(Base):
    """Activity log entry from desktop agent (app/window tracking)"""
    __tablename__ = "desktop_activity_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # No FK - users are in-memory
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    
    # Activity data from desktop agent
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    window_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Input activity
    mouse_count: Mapped[int] = mapped_column(Integer, default=0)
    key_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Status
    is_idle: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Categorization (can be set by admin rules)
    category_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    category: Mapped[Optional["Category"]] = relationship("Category")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_desktop_activity_user_time", "user_id", "timestamp"),
        Index("ix_desktop_activity_app", "app_name"),
        Index("ix_desktop_activity_session", "session_id"),
    )
