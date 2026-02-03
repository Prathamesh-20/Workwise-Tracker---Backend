"""
Desktop Activity Analytics - Data Processing Logic
Hierarchical Report: Date -> App -> Sub-activities (for browsers)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict
import re

from app.database import get_db
from app.models import DesktopActivityLog
from app.api.sync import get_user_from_token, UserInfo


router = APIRouter()


# ============================================================================
# BROWSER DETECTION & DOMAIN EXTRACTION
# ============================================================================

BROWSERS = ["chrome", "firefox", "edge", "safari", "brave", "opera", "arc"]


def is_browser(app_name: str) -> bool:
    """Check if an app is a web browser."""
    app_lower = app_name.lower()
    return any(browser in app_lower for browser in BROWSERS)


def extract_domain_from_title(window_title: str) -> str:
    """
    Extract website/service name from browser window title.
    
    Examples:
    - "Funny Cat Video - YouTube" -> "YouTube"
    - "Gmail - Inbox" -> "Gmail"
    - "GitHub - Repository" -> "GitHub"
    - "google.com - Search" -> "google.com"
    """
    if not window_title:
        return "Unknown"
    
    # Common patterns for extracting site names
    # Pattern 1: "Title - SiteName" (most common)
    if " - " in window_title:
        parts = window_title.rsplit(" - ", 1)
        if len(parts) == 2:
            site_name = parts[1].strip()
            # Check if it's a browser name (ignore it)
            if not any(browser in site_name.lower() for browser in BROWSERS):
                return site_name
    
    # Pattern 2: "Title | SiteName"
    if " | " in window_title:
        parts = window_title.rsplit(" | ", 1)
        if len(parts) == 2:
            site_name = parts[1].strip()
            if not any(browser in site_name.lower() for browser in BROWSERS):
                return site_name
    
    # Pattern 3: Contains a domain-like string
    domain_match = re.search(r'(\w+\.(com|org|io|net|co|app|dev))', window_title, re.IGNORECASE)
    if domain_match:
        return domain_match.group(1)
    
    # Fallback: use first 30 chars of title
    return window_title[:30] if len(window_title) > 30 else window_title


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


# ============================================================================
# DATA PROCESSING
# ============================================================================

def process_logs(logs: List[Dict[str, Any]], interval_seconds: int = 5) -> Dict[str, Any]:
    """
    Process activity logs into hierarchical report.
    
    Structure:
    {
        "date": "2025-01-15",
        "total_hours": 8.5,
        "total_active_seconds": 30600,
        "total_idle_seconds": 1800,
        "apps": [
            {
                "name": "Google Chrome",
                "duration": "4h 20m",
                "duration_seconds": 15600,
                "is_browser": true,
                "sub_activities": [
                    {"name": "YouTube", "duration": "3h", "duration_seconds": 10800},
                    {"name": "Gmail", "duration": "1h 20m", "duration_seconds": 4800}
                ]
            },
            {
                "name": "VS Code",
                "duration": "2h",
                "duration_seconds": 7200,
                "is_browser": false,
                "sub_activities": []
            }
        ]
    }
    """
    if not logs:
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_hours": 0,
            "total_active_seconds": 0,
            "total_idle_seconds": 0,
            "apps": []
        }
    
    # Group by app name
    app_data = defaultdict(lambda: {
        "count": 0,
        "idle_count": 0,
        "sub_activities": defaultdict(int)
    })
    
    for log in logs:
        app_name = log.get("app_name", "Unknown")
        is_idle = log.get("is_idle", False)
        window_title = log.get("window_title", "")
        
        if is_idle:
            app_data[app_name]["idle_count"] += 1
        else:
            app_data[app_name]["count"] += 1
        
        # Track sub-activity (for all apps, not just browsers)
        if window_title and not is_idle:
            if is_browser(app_name):
                # For browsers, extract the domain/site name
                sub_activity = extract_domain_from_title(window_title)
            else:
                # For other apps, use the window title (truncated for readability)
                sub_activity = window_title[:60] if len(window_title) > 60 else window_title
            
            if sub_activity:
                app_data[app_name]["sub_activities"][sub_activity] += 1
    
    # Convert to output format
    apps = []
    total_active_seconds = 0
    total_idle_seconds = 0
    
    for app_name, data in sorted(app_data.items(), key=lambda x: x[1]["count"], reverse=True):
        active_seconds = data["count"] * interval_seconds
        idle_seconds = data["idle_count"] * interval_seconds
        total_seconds = active_seconds + idle_seconds
        
        total_active_seconds += active_seconds
        total_idle_seconds += idle_seconds
        
        app_entry = {
            "name": app_name,
            "duration": format_duration(total_seconds),
            "duration_seconds": total_seconds,
            "active_seconds": active_seconds,
            "is_browser": is_browser(app_name),
            "sub_activities": []
        }
        
        # Add sub-activities for browsers
        if data["sub_activities"]:
            for site, count in sorted(data["sub_activities"].items(), key=lambda x: x[1], reverse=True):
                site_seconds = count * interval_seconds
                app_entry["sub_activities"].append({
                    "name": site,
                    "duration": format_duration(site_seconds),
                    "duration_seconds": site_seconds
                })
        
        apps.append(app_entry)
    
    # Determine the date from first log
    first_timestamp = logs[0].get("timestamp")
    if isinstance(first_timestamp, str):
        date_str = first_timestamp[:10]
    elif isinstance(first_timestamp, datetime):
        date_str = first_timestamp.strftime("%Y-%m-%d")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    total_seconds = total_active_seconds + total_idle_seconds
    total_hours = round(total_seconds / 3600, 2)
    
    return {
        "date": date_str,
        "total_hours": total_hours,
        "total_active_seconds": total_active_seconds,
        "total_idle_seconds": total_idle_seconds,
        "apps": apps
    }


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/desktop/daily-report")
async def get_daily_report(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    user_id: Optional[str] = Query(None, description="User ID (admin only)"),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get hierarchical daily activity report for desktop tracking.
    
    Returns apps grouped by usage with browser sub-activities.
    
    Query params:
    - date: Date to get report for (default: today)
    - user_id: (admin only) Get report for specific user
    """
    # Parse date
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()
    
    # Determine which user to query
    target_user_id = user.id
    if user_id and user.role == "admin":
        target_user_id = user_id
    
    # Get date range
    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    
    # Query logs
    result = await db.execute(
        select(DesktopActivityLog)
        .where(
            and_(
                DesktopActivityLog.user_id == target_user_id,
                DesktopActivityLog.timestamp >= start_of_day,
                DesktopActivityLog.timestamp < end_of_day
            )
        )
        .order_by(DesktopActivityLog.timestamp)
    )
    
    logs = result.scalars().all()
    
    # Convert to dict list
    log_dicts = [
        {
            "timestamp": log.timestamp,
            "app_name": log.app_name,
            "window_title": log.window_title,
            "is_idle": log.is_idle,
            "mouse_count": log.mouse_count,
            "key_count": log.key_count
        }
        for log in logs
    ]
    
    # Process and return
    report = process_logs(log_dicts)
    report["user_id"] = target_user_id
    
    return report


@router.get("/desktop/weekly-summary")
async def get_weekly_summary(
    user_id: Optional[str] = Query(None, description="User ID (admin only)"),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get weekly summary of desktop activity.
    
    Returns daily totals for the past 7 days.
    """
    target_user_id = user.id
    if user_id and user.role == "admin":
        target_user_id = user_id
    
    # Get past 7 days
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    
    # Get all logs for the period and process in Python
    result = await db.execute(
        select(DesktopActivityLog)
        .where(
            and_(
                DesktopActivityLog.user_id == target_user_id,
                DesktopActivityLog.timestamp >= week_ago
            )
        )
        .order_by(DesktopActivityLog.timestamp)
    )
    
    logs = result.scalars().all()
    
    # Group by date in Python
    from collections import defaultdict
    daily_counts = defaultdict(lambda: {"total": 0, "active": 0})
    
    for log in logs:
        date_str = log.timestamp.strftime("%Y-%m-%d")
        daily_counts[date_str]["total"] += 1
        if not log.is_idle:
            daily_counts[date_str]["active"] += 1
    
    daily_data = []
    for date_str in sorted(daily_counts.keys()):
        counts = daily_counts[date_str]
        active_seconds = counts["active"] * 5
        total_seconds = counts["total"] * 5
        
        daily_data.append({
            "date": date_str,
            "total_hours": round(total_seconds / 3600, 2),
            "active_hours": round(active_seconds / 3600, 2),
            "total_logs": counts["total"]
        })
    
    return {
        "user_id": target_user_id,
        "period": "7_days",
        "start_date": week_ago.strftime("%Y-%m-%d"),
        "end_date": today.strftime("%Y-%m-%d"),
        "daily_data": daily_data
    }


@router.get("/desktop/top-apps")
async def get_top_apps(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    limit: int = Query(10, ge=1, le=50, description="Number of apps to return"),
    user_id: Optional[str] = Query(None, description="User ID (admin only)"),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get top apps by usage time.
    """
    target_user_id = user.id
    if user_id and user.role == "admin":
        target_user_id = user_id
    
    since = datetime.now() - timedelta(days=days)
    
    # Query logs grouped by app
    result = await db.execute(
        select(
            DesktopActivityLog.app_name,
            func.count(DesktopActivityLog.id).label("log_count")
        )
        .where(
            and_(
                DesktopActivityLog.user_id == target_user_id,
                DesktopActivityLog.timestamp >= since,
                DesktopActivityLog.is_idle == False
            )
        )
        .group_by(DesktopActivityLog.app_name)
        .order_by(func.count(DesktopActivityLog.id).desc())
        .limit(limit)
    )
    
    apps = []
    for row in result.all():
        seconds = row.log_count * 5
        apps.append({
            "app_name": row.app_name,
            "duration": format_duration(seconds),
            "duration_seconds": seconds,
            "is_browser": is_browser(row.app_name)
        })
    
    return {
        "user_id": target_user_id,
        "period_days": days,
        "apps": apps
    }
