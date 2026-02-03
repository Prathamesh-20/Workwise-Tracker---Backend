"""
Analytics API endpoints - Batch 10
Productivity stats, time breakdowns, daily summaries
"""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from app.schemas import TokenData
from app.auth import get_current_user, get_admin_user
from app.categorization import categorize_domain, CategoryType, get_category_color

# Import logs from in-memory store
from app.api.logs import _activity_logs

router = APIRouter()


@router.get("/productivity")
async def get_productivity_stats(
    user_id: Optional[str] = None,
    days: int = Query(default=7, ge=1, le=30),
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get productivity breakdown for a user or all users.
    """
    # Filter logs by timeframe
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    filtered_logs = [
        log for log in _activity_logs
        if log["start_time"] >= cutoff
        and (user_id is None or log["user_id"] == user_id)
        and not log.get("is_idle", False)
    ]
    
    # Calculate time by category
    stats = {
        CategoryType.PRODUCTIVE: 0,
        CategoryType.DISTRACTION: 0,
        CategoryType.NEUTRAL: 0,
    }
    
    domain_times: dict[str, int] = defaultdict(int)
    
    for log in filtered_logs:
        domain = log["domain"]
        duration = log["duration_seconds"]
        
        category_info = categorize_domain(domain)
        stats[category_info["category"]] += duration
        domain_times[domain] += duration
    
    total = sum(stats.values()) or 1
    
    # Top domains
    top_domains = sorted(
        domain_times.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    return {
        "days": days,
        "total_seconds": total,
        "productive_seconds": stats[CategoryType.PRODUCTIVE],
        "distraction_seconds": stats[CategoryType.DISTRACTION],
        "neutral_seconds": stats[CategoryType.NEUTRAL],
        "productive_percent": round(stats[CategoryType.PRODUCTIVE] / total * 100, 1),
        "distraction_percent": round(stats[CategoryType.DISTRACTION] / total * 100, 1),
        "neutral_percent": round(stats[CategoryType.NEUTRAL] / total * 100, 1),
        "top_domains": [
            {
                "domain": domain,
                "seconds": seconds,
                "category": categorize_domain(domain),
            }
            for domain, seconds in top_domains
        ],
    }


@router.get("/daily")
async def get_daily_breakdown(
    user_id: Optional[str] = None,
    days: int = Query(default=7, ge=1, le=30),
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get daily time breakdown.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    daily_data: dict[str, dict] = {}
    
    for log in _activity_logs:
        if log["start_time"] < cutoff:
            continue
        if user_id and log["user_id"] != user_id:
            continue
        if log.get("is_idle"):
            continue
        
        date_key = log["start_time"].strftime("%Y-%m-%d")
        
        if date_key not in daily_data:
            daily_data[date_key] = {
                "date": date_key,
                CategoryType.PRODUCTIVE: 0,
                CategoryType.DISTRACTION: 0,
                CategoryType.NEUTRAL: 0,
                "total": 0,
            }
        
        category = categorize_domain(log["domain"])["category"]
        daily_data[date_key][category] += log["duration_seconds"]
        daily_data[date_key]["total"] += log["duration_seconds"]
    
    # Sort by date
    result = sorted(daily_data.values(), key=lambda x: x["date"])
    
    return {
        "days": days,
        "data": result,
    }


@router.get("/leaderboard")
async def get_productivity_leaderboard(
    days: int = Query(default=7, ge=1, le=30),
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get productivity leaderboard across all users.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    user_stats: dict[str, dict] = {}
    
    for log in _activity_logs:
        if log["start_time"] < cutoff or log.get("is_idle"):
            continue
        
        user_id = log["user_id"]
        user_email = log.get("user_email", "Unknown")
        
        if user_id not in user_stats:
            user_stats[user_id] = {
                "user_id": user_id,
                "email": user_email,
                CategoryType.PRODUCTIVE: 0,
                CategoryType.DISTRACTION: 0,
                "total": 0,
            }
        
        category = categorize_domain(log["domain"])["category"]
        if category in [CategoryType.PRODUCTIVE, CategoryType.DISTRACTION]:
            user_stats[user_id][category] += log["duration_seconds"]
        user_stats[user_id]["total"] += log["duration_seconds"]
    
    # Calculate productivity scores
    leaderboard = []
    for user in user_stats.values():
        total = user["total"] or 1
        score = round(user[CategoryType.PRODUCTIVE] / total * 100, 1)
        leaderboard.append({
            **user,
            "productivity_score": score,
        })
    
    # Sort by productivity score
    leaderboard.sort(key=lambda x: x["productivity_score"], reverse=True)
    
    return {
        "days": days,
        "users": leaderboard,
    }
