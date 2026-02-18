"""
FocusTrack Analytics - Data Export API Endpoint
Add this to your backend to expose a data export endpoint
that the dashboard or local scripts can call via HTTP.

To use: Import and include this router in your main.py
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from datetime import datetime, timedelta
from typing import Optional
import csv
import io

from app.database import get_db
from app.models import DesktopActivityLog, User
from app.api.sync import get_user_from_token, UserInfo

router = APIRouter(prefix="/analytics/export", tags=["Data Export"])


@router.get("/employee-summary")
async def export_employee_summary(
    days: int = Query(7, ge=1, le=90, description="Days to include"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Get aggregated daily employee summary data.
    Admin sees all employees. Employees see only their own data.
    
    Returns per-employee, per-day:
    - active_hours, idle_hours
    - total_mouse_events, total_key_events
    - unique_apps, top_app
    - activity_score (avg mouse+key per active interval)
    """
    if user.role != "admin" and user_id and user_id != user.id:
        raise HTTPException(status_code=403, detail="Can only view your own data")
    
    since = datetime.now() - timedelta(days=days)
    
    # Build query
    conditions = [DesktopActivityLog.timestamp >= since]
    
    if user_id:
        conditions.append(DesktopActivityLog.user_id == user_id)
    elif user.role != "admin":
        conditions.append(DesktopActivityLog.user_id == user.id)
    
    # Get all matching logs
    result = await db.execute(
        select(DesktopActivityLog)
        .where(and_(*conditions))
        .order_by(DesktopActivityLog.timestamp)
    )
    logs = result.scalars().all()
    
    # Get user mapping
    users_result = await db.execute(select(User))
    users_map = {u.id: {"email": u.email, "name": u.name} for u in users_result.scalars().all()}
    
    # Aggregate per user per day
    from collections import defaultdict
    daily_data = defaultdict(lambda: {
        "active_logs": 0, "idle_logs": 0,
        "mouse_total": 0, "key_total": 0,
        "apps": defaultdict(int),
    })
    
    for log in logs:
        date_str = log.timestamp.strftime("%Y-%m-%d")
        key = (log.user_id, date_str)
        
        if log.is_idle:
            daily_data[key]["idle_logs"] += 1
        else:
            daily_data[key]["active_logs"] += 1
            daily_data[key]["apps"][log.app_name] += 1
        
        daily_data[key]["mouse_total"] += log.mouse_count
        daily_data[key]["key_total"] += log.key_count
    
    # Build response
    summary = []
    for (uid, date_str), data in sorted(daily_data.items(), key=lambda x: (x[0][1], x[0][0]), reverse=True):
        user_info = users_map.get(uid, {"email": "unknown", "name": "Unknown"})
        active_hours = round((data["active_logs"] * 5) / 3600, 2)
        idle_hours = round((data["idle_logs"] * 5) / 3600, 2)
        
        # Top app
        top_app = max(data["apps"], key=data["apps"].get) if data["apps"] else "N/A"
        
        # Activity score: avg inputs per active interval
        avg_score = 0
        total_inputs = data["mouse_total"] + data["key_total"]
        if data["active_logs"] > 0:
            avg_score = round(total_inputs / data["active_logs"], 1)
        
        summary.append({
            "user_id": uid,
            "user_email": user_info["email"],
            "user_name": user_info["name"],
            "date": date_str,
            "active_hours": active_hours,
            "idle_hours": idle_hours,
            "total_hours": round(active_hours + idle_hours, 2),
            "total_mouse_events": data["mouse_total"],
            "total_key_events": data["key_total"],
            "unique_apps": len(data["apps"]),
            "top_app": top_app,
            "activity_score": avg_score,
        })
    
    return {
        "period_days": days,
        "total_records": len(summary),
        "data": summary
    }


@router.get("/employee-summary/csv")
async def export_employee_summary_csv(
    days: int = Query(7, ge=1, le=90),
    user_id: Optional[str] = Query(None),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """Export employee summary as downloadable CSV file."""
    
    # Reuse the JSON endpoint logic
    result = await export_employee_summary(days=days, user_id=user_id, user=user, db=db)
    data = result["data"]
    
    if not data:
        raise HTTPException(status_code=404, detail="No data found")
    
    # Build CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    
    output.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"employee_summary_{days}days_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/raw-logs")
async def export_raw_logs(
    days: int = Query(7, ge=1, le=30, description="Days (max 30 for raw logs)"),
    user_id: Optional[str] = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
    user: UserInfo = Depends(get_user_from_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Export raw activity logs with user info.
    Admin only — large dataset, use with caution.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required for raw export")
    
    since = datetime.now() - timedelta(days=days)
    
    conditions = [DesktopActivityLog.timestamp >= since]
    if user_id:
        conditions.append(DesktopActivityLog.user_id == user_id)
    
    result = await db.execute(
        select(DesktopActivityLog)
        .where(and_(*conditions))
        .order_by(DesktopActivityLog.timestamp.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    
    # Get user mapping
    users_result = await db.execute(select(User))
    users_map = {u.id: {"email": u.email, "name": u.name} for u in users_result.scalars().all()}
    
    return {
        "total_records": len(logs),
        "period_days": days,
        "data": [
            {
                "id": log.id,
                "user_email": users_map.get(log.user_id, {}).get("email", "unknown"),
                "user_name": users_map.get(log.user_id, {}).get("name", "Unknown"),
                "timestamp": log.timestamp.isoformat(),
                "app_name": log.app_name,
                "window_title": log.window_title,
                "mouse_count": log.mouse_count,
                "key_count": log.key_count,
                "is_idle": log.is_idle,
                "session_id": log.session_id,
            }
            for log in logs
        ]
    }
