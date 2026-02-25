"""
Desktop Activity Analytics - Data Processing Logic
Hierarchical Report: Date -> App -> Sub-activities (for browsers)

UPDATED: Added idle smoothing, gap detection, and improved accuracy.
Changes from original:
1. IDLE SMOOTHING - Short idle periods (<60s) between active periods on same app
   are reclassified as active (handles reading/thinking pauses)
2. GAP DETECTION - Gaps >5 min between snapshots are excluded from totals
   (handles agent stop/start, lunch breaks, etc.)
3. IMPROVED STATS - Added focus_time, true_idle, break_time breakdown
4. INPUT INTENSITY - Per-app avg mouse+key activity score
5. FOCUS STREAKS - Longest consecutive active streak per app
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


# ============================================================================
# CONFIGURATION
# ============================================================================

SNAPSHOT_INTERVAL = 5          # seconds between each agent snapshot
IDLE_SMOOTHING_WINDOW = 60     # seconds - idle periods shorter than this between
                                # active periods on same app are counted as active
GAP_THRESHOLD = 300            # seconds (5 min) - gaps larger than this between
                                # snapshots are excluded (agent was stopped/break)
MIN_IDLE_STREAK = 12           # minimum consecutive idle snapshots (60s) to count
                                # as truly idle


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
# IDLE SMOOTHING & GAP DETECTION
# ============================================================================


def smooth_idle_status(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Reclassify short idle periods as active when they occur during
    focused work on the same application.

    Logic:
    - Sort by timestamp
    - Find consecutive "idle" streaks
    - If an idle streak is shorter than IDLE_SMOOTHING_WINDOW (60s)
      AND the app before and after the streak is the same
      -> reclassify those idle snapshots as active

    This handles:
    - Reading/reviewing content (annotation work, code review)
    - Thinking pauses between actions
    - Short waits for page loads
    - Looking at images before clicking labels

    What stays idle:
    - Long periods of no input (>60s continuous)
    - Idle time with different apps before/after (user walked away)
    """
    if not logs:
        return logs

    # Sort by timestamp
    sorted_logs = sorted(logs, key=lambda x: x.get("timestamp", ""))

    # Create a working copy with smoothed is_idle
    smoothed = []
    for log in sorted_logs:
        smoothed.append({**log, "original_is_idle": log.get("is_idle", False)})

    n = len(smoothed)
    i = 0

    while i < n:
        # Find start of an idle streak
        if smoothed[i].get("is_idle", False):
            streak_start = i

            # Find end of idle streak
            while i < n and smoothed[i].get("is_idle", False):
                i += 1
            streak_end = i  # exclusive

            streak_length = streak_end - streak_start
            streak_seconds = streak_length * SNAPSHOT_INTERVAL

            # Check if this is a short idle streak (within smoothing window)
            if streak_seconds <= IDLE_SMOOTHING_WINDOW:
                # Get the app before the streak
                app_before = None
                if streak_start > 0:
                    app_before = smoothed[streak_start - 1].get("app_name", "")

                # Get the app after the streak
                app_after = None
                if streak_end < n:
                    app_after = smoothed[streak_end].get("app_name", "")

                # If same app before and after -> user was thinking/reading, not idle
                if app_before and app_after and app_before == app_after:
                    for j in range(streak_start, streak_end):
                        smoothed[j]["is_idle"] = False
                        smoothed[j]["smoothed"] = True  # flag for debugging

                # Even if different apps, if streak is very short (<=15s = 3 snapshots)
                # it's likely just an app switch, not real idle
                elif streak_seconds <= 15:
                    for j in range(streak_start, streak_end):
                        smoothed[j]["is_idle"] = False
                        smoothed[j]["smoothed"] = True
        else:
            i += 1

    return smoothed


def detect_gaps(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Mark gaps in activity where the agent was likely stopped.

    If there's a gap > GAP_THRESHOLD (5 min) between consecutive snapshots,
    mark those as a break/gap so they don't inflate idle time.
    """
    if not logs:
        return logs

    sorted_logs = sorted(logs, key=lambda x: x.get("timestamp", ""))

    for i in range(1, len(sorted_logs)):
        ts_prev = sorted_logs[i - 1].get("timestamp")
        ts_curr = sorted_logs[i].get("timestamp")

        if isinstance(ts_prev, str):
            ts_prev = datetime.fromisoformat(ts_prev.replace("Z", "+00:00"))
        if isinstance(ts_curr, str):
            ts_curr = datetime.fromisoformat(ts_curr.replace("Z", "+00:00"))

        if ts_prev and ts_curr:
            gap = (ts_curr - ts_prev).total_seconds()
            if gap > GAP_THRESHOLD:
                # Mark the snapshot after the gap
                sorted_logs[i]["after_gap"] = True
                sorted_logs[i]["gap_seconds"] = gap

    return sorted_logs


def compute_focus_streaks(logs: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Compute the longest consecutive active streak (in seconds) per app.
    Helps identify deep-work sessions.
    """
    streaks: Dict[str, int] = defaultdict(int)
    if not logs:
        return streaks

    current_app = None
    current_streak = 0

    for log in logs:
        app = log.get("app_name", "Unknown")
        is_idle = log.get("is_idle", False)

        if not is_idle and app == current_app:
            current_streak += SNAPSHOT_INTERVAL
        else:
            # Save previous streak if it was active
            if current_app and current_streak > 0:
                streaks[current_app] = max(streaks[current_app], current_streak)
            # Reset
            current_app = app
            current_streak = 0 if is_idle else SNAPSHOT_INTERVAL

    # Don't forget the last streak
    if current_app and current_streak > 0:
        streaks[current_app] = max(streaks[current_app], current_streak)

    return streaks


# ============================================================================
# DATA PROCESSING
# ============================================================================

def process_logs(logs: List[Dict[str, Any]], interval_seconds: int = SNAPSHOT_INTERVAL) -> Dict[str, Any]:
    """
    Process activity logs into hierarchical report with idle smoothing.

    IMPROVEMENTS over original:
    1. Idle smoothing: short idle pauses during focused work -> counted as active
    2. Gap detection: large gaps between snapshots excluded from idle time
    3. Better stats: focus_time, true_idle, break_time breakdown
    4. Input intensity: avg mouse+key per snapshot per app
    5. Focus streaks: longest consecutive active streak per app

    Structure:
    {
        "date": "2025-01-15",
        "total_hours": 8.5,
        "total_active_seconds": 30600,   # after smoothing
        "total_idle_seconds": 1800,      # true idle only
        "raw_active_seconds": 25000,     # before smoothing (for comparison)
        "raw_idle_seconds": 7400,        # before smoothing
        "smoothed_recovered_seconds": 5600,  # idle->active reclassification
        "gap_seconds": 0,               # time in gaps (agent stopped)
        "apps": [
            {
                "name": "Google Chrome",
                "duration": "4h 20m",
                "duration_seconds": 15600,
                "active_seconds": 14400,
                "is_browser": true,
                "input_intensity": 12.5,
                "longest_focus_streak": "45m",
                "longest_focus_streak_seconds": 2700,
                "sub_activities": [
                    {"name": "YouTube", "duration": "3h", "duration_seconds": 10800},
                    {"name": "Gmail", "duration": "1h 20m", "duration_seconds": 4800}
                ]
            },
            {
                "name": "VS Code",
                "duration": "2h",
                "duration_seconds": 7200,
                "active_seconds": 7000,
                "is_browser": false,
                "input_intensity": 35.2,
                "longest_focus_streak": "1h 10m",
                "longest_focus_streak_seconds": 4200,
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
            "raw_active_seconds": 0,
            "raw_idle_seconds": 0,
            "smoothed_recovered_seconds": 0,
            "gap_seconds": 0,
            "apps": []
        }

    # Step 1: Detect gaps (agent stop/start, breaks)
    logs_with_gaps = detect_gaps(logs)

    # Step 2: Apply idle smoothing
    smoothed_logs = smooth_idle_status(logs_with_gaps)

    # Step 3: Calculate raw stats (before smoothing) for comparison
    raw_active = sum(1 for log in logs if not log.get("is_idle", False))
    raw_idle = sum(1 for log in logs if log.get("is_idle", False))

    # Step 4: Compute focus streaks (on smoothed data)
    focus_streaks = compute_focus_streaks(smoothed_logs)

    # Step 5: Group by app name using smoothed data
    app_data = defaultdict(lambda: {
        "count": 0,
        "idle_count": 0,
        "smoothed_count": 0,
        "total_mouse": 0,
        "total_keys": 0,
        "input_snapshots": 0,
        "sub_activities": defaultdict(int)
    })

    total_gap_seconds = 0

    for log in smoothed_logs:
        app_name = log.get("app_name", "Unknown")
        is_idle = log.get("is_idle", False)
        was_smoothed = log.get("smoothed", False)
        window_title = log.get("window_title", "")

        # Track gap time separately
        if log.get("after_gap", False):
            total_gap_seconds += log.get("gap_seconds", 0)

        if is_idle:
            app_data[app_name]["idle_count"] += 1
        else:
            app_data[app_name]["count"] += 1
            if was_smoothed:
                app_data[app_name]["smoothed_count"] += 1

        # Track input activity for intensity score
        mouse = log.get("mouse_count", 0) or 0
        keys = log.get("key_count", 0) or 0
        if mouse > 0 or keys > 0:
            app_data[app_name]["total_mouse"] += mouse
            app_data[app_name]["total_keys"] += keys
            app_data[app_name]["input_snapshots"] += 1

        # Track sub-activity (for all apps, not just browsers)
        if window_title and not is_idle:
            if is_browser(app_name):
                sub_activity = extract_domain_from_title(window_title)
            else:
                sub_activity = window_title[:60] if len(window_title) > 60 else window_title

            if sub_activity:
                app_data[app_name]["sub_activities"][sub_activity] += 1

    # Step 6: Convert to output format
    apps = []
    total_active_seconds = 0
    total_idle_seconds = 0
    total_smoothed_seconds = 0

    for app_name, data in sorted(app_data.items(), key=lambda x: x[1]["count"], reverse=True):
        active_seconds = data["count"] * interval_seconds
        idle_seconds = data["idle_count"] * interval_seconds
        smoothed_seconds = data["smoothed_count"] * interval_seconds
        total_seconds = active_seconds + idle_seconds

        total_active_seconds += active_seconds
        total_idle_seconds += idle_seconds
        total_smoothed_seconds += smoothed_seconds

        # Compute input intensity: avg (mouse + keys) per active snapshot
        input_snaps = data["input_snapshots"]
        input_intensity = round(
            (data["total_mouse"] + data["total_keys"]) / max(input_snaps, 1), 1
        )

        app_entry = {
            "name": app_name,
            "duration": format_duration(total_seconds),
            "duration_seconds": total_seconds,
            "active_seconds": active_seconds,
            "is_browser": is_browser(app_name),
            "input_intensity": input_intensity,
            "longest_focus_streak": format_duration(focus_streaks.get(app_name, 0)),
            "longest_focus_streak_seconds": focus_streaks.get(app_name, 0),
            "sub_activities": []
        }

        if data["sub_activities"]:
            for site, count in sorted(data["sub_activities"].items(), key=lambda x: x[1], reverse=True):
                site_seconds = count * interval_seconds
                app_entry["sub_activities"].append({
                    "name": site,
                    "duration": format_duration(site_seconds),
                    "duration_seconds": site_seconds
                })

        apps.append(app_entry)

    # Determine date from first log
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
        "raw_active_seconds": raw_active * interval_seconds,
        "raw_idle_seconds": raw_idle * interval_seconds,
        "smoothed_recovered_seconds": total_smoothed_seconds,
        "gap_seconds": int(total_gap_seconds),
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
    Now includes idle smoothing for more accurate productivity measurement.
    
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
    Returns daily totals for the past 7 days (with idle smoothing).
    """
    target_user_id = user.id
    if user_id and user.role == "admin":
        target_user_id = user_id

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

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

    # Group by date
    daily_logs = defaultdict(list)
    for log in logs:
        date_str = log.timestamp.strftime("%Y-%m-%d")
        daily_logs[date_str].append({
            "timestamp": log.timestamp,
            "app_name": log.app_name,
            "window_title": log.window_title,
            "is_idle": log.is_idle,
            "mouse_count": log.mouse_count,
            "key_count": log.key_count
        })

    daily_data = []
    for date_str in sorted(daily_logs.keys()):
        # Process each day with smoothing
        day_report = process_logs(daily_logs[date_str])

        active_seconds = day_report["total_active_seconds"]
        idle_seconds = day_report["total_idle_seconds"]
        total_seconds = active_seconds + idle_seconds

        daily_data.append({
            "date": date_str,
            "total_hours": round(total_seconds / 3600, 2),
            "active_hours": round(active_seconds / 3600, 2),
            "idle_hours": round(idle_seconds / 3600, 2),
            "total_logs": len(daily_logs[date_str]),
            "productivity_pct": round((active_seconds / total_seconds * 100) if total_seconds > 0 else 0, 1),
            "smoothed_recovered_seconds": day_report.get("smoothed_recovered_seconds", 0)
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
        seconds = row.log_count * SNAPSHOT_INTERVAL
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


@router.get("/desktop/debug-smoothing")
async def debug_smoothing(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    user_id: Optional[str] = Query(None, description="User ID (admin only)"),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    DEBUG ENDPOINT: Compare raw vs smoothed idle/active counts.
    Shows exactly how many snapshots were reclassified.
    Useful for tuning smoothing parameters.
    """
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    target_user_id = user.id
    if user_id and user.role == "admin":
        target_user_id = user_id

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

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

    # Raw counts
    raw_active = sum(1 for l in log_dicts if not l.get("is_idle", False))
    raw_idle = sum(1 for l in log_dicts if l.get("is_idle", False))

    # Smoothed
    report = process_logs(log_dicts)

    smoothed_active = report["total_active_seconds"] // SNAPSHOT_INTERVAL
    smoothed_idle = report["total_idle_seconds"] // SNAPSHOT_INTERVAL
    recovered = report.get("smoothed_recovered_seconds", 0) // SNAPSHOT_INTERVAL

    return {
        "user_id": target_user_id,
        "date": target_date.strftime("%Y-%m-%d"),
        "total_snapshots": len(log_dicts),
        "raw": {
            "active_snapshots": raw_active,
            "idle_snapshots": raw_idle,
            "active_minutes": round(raw_active * SNAPSHOT_INTERVAL / 60, 1),
            "idle_minutes": round(raw_idle * SNAPSHOT_INTERVAL / 60, 1),
            "productivity_pct": round(raw_active / max(raw_active + raw_idle, 1) * 100, 1)
        },
        "smoothed": {
            "active_snapshots": smoothed_active,
            "idle_snapshots": smoothed_idle,
            "active_minutes": round(smoothed_active * SNAPSHOT_INTERVAL / 60, 1),
            "idle_minutes": round(smoothed_idle * SNAPSHOT_INTERVAL / 60, 1),
            "productivity_pct": round(smoothed_active / max(smoothed_active + smoothed_idle, 1) * 100, 1)
        },
        "improvement": {
            "recovered_snapshots": recovered,
            "recovered_minutes": round(recovered * SNAPSHOT_INTERVAL / 60, 1),
            "productivity_increase_pct": round(
                (smoothed_active / max(smoothed_active + smoothed_idle, 1) * 100) -
                (raw_active / max(raw_active + raw_idle, 1) * 100), 1
            )
        },
        "config": {
            "snapshot_interval_seconds": SNAPSHOT_INTERVAL,
            "idle_smoothing_window_seconds": IDLE_SMOOTHING_WINDOW,
            "gap_threshold_seconds": GAP_THRESHOLD
        }
    }
