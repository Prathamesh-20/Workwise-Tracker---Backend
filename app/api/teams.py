"""
Teams API - Team management, app rules, member assignment, and productivity
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.models import Team, User, TeamAppRule, DesktopActivityLog
from app.schemas import TokenData, UserRole
from app.auth import get_current_user, get_admin_user


router = APIRouter()


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================

class TeamCreate(BaseModel):
    name: str

class TeamUpdate(BaseModel):
    name: str

class AssignUser(BaseModel):
    user_id: str
    team_id: str

class BulkAssign(BaseModel):
    user_ids: list[str]
    team_id: str

class RuleCreate(BaseModel):
    app_pattern: str
    category: str = "neutral"
    match_type: str = "contains"

class BulkRules(BaseModel):
    productive: list[str] = []
    neutral: list[str] = []
    non_productive: list[str] = []


# ============================================================
# HELPER: require admin
# ============================================================

def require_admin(current_user: TokenData = Depends(get_current_user)) -> TokenData:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ============================================================
# TEAM CRUD
# ============================================================

@router.get("/teams")
async def list_teams(
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all teams with member counts."""
    result = await db.execute(select(Team))
    teams = result.scalars().all()

    team_list = []
    for team in teams:
        # Count members
        member_count_result = await db.execute(
            select(func.count(User.id)).where(User.team_id == team.id)
        )
        member_count = member_count_result.scalar() or 0

        # Count rules
        rule_count_result = await db.execute(
            select(func.count(TeamAppRule.id)).where(TeamAppRule.team_id == team.id)
        )
        rule_count = rule_count_result.scalar() or 0

        team_list.append({
            "id": team.id,
            "name": team.name,
            "member_count": member_count,
            "rule_count": rule_count,
            "created_at": team.created_at.isoformat() if team.created_at else None,
        })

    return team_list


@router.get("/teams/{team_id}")
async def get_team_detail(
    team_id: str,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get team detail with members and rules."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get members
    members_result = await db.execute(
        select(User).where(User.team_id == team_id)
    )
    members = members_result.scalars().all()

    # Get rules
    rules_result = await db.execute(
        select(TeamAppRule).where(TeamAppRule.team_id == team_id).order_by(TeamAppRule.category, TeamAppRule.app_pattern)
    )
    rules = rules_result.scalars().all()

    return {
        "id": team.id,
        "name": team.name,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "members": [
            {
                "id": m.id,
                "name": m.name,
                "email": m.email,
                "role": m.role,
                "is_active": m.is_active,
            }
            for m in members
        ],
        "rules": [
            {
                "id": r.id,
                "app_pattern": r.app_pattern,
                "category": r.category,
                "match_type": r.match_type,
            }
            for r in rules
        ],
    }


@router.post("/teams")
async def create_team(
    body: TeamCreate,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new team."""
    team = Team(name=body.name)
    db.add(team)
    await db.flush()
    return {"id": team.id, "name": team.name, "success": True}


@router.put("/teams/{team_id}")
async def update_team(
    team_id: str,
    body: TeamUpdate,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update team name."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = body.name
    return {"id": team.id, "name": team.name, "success": True}


@router.delete("/teams/{team_id}")
async def delete_team(
    team_id: str,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a team. Members become unassigned."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Unassign members first
    members_result = await db.execute(select(User).where(User.team_id == team_id))
    for member in members_result.scalars().all():
        member.team_id = None

    await db.delete(team)
    return {"success": True, "message": f"Team '{team.name}' deleted"}


# ============================================================
# MEMBER ASSIGNMENT
# ============================================================

@router.post("/teams/assign")
async def assign_user_to_team(
    body: AssignUser,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Assign a user to a team."""
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    team_result = await db.execute(select(Team).where(Team.id == body.team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    user.team_id = body.team_id
    return {"success": True, "message": f"{user.name} assigned to team"}


@router.post("/teams/assign-bulk")
async def bulk_assign(
    body: BulkAssign,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Bulk assign users to a team."""
    team_result = await db.execute(select(Team).where(Team.id == body.team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    count = 0
    for uid in body.user_ids:
        user_result = await db.execute(select(User).where(User.id == uid))
        user = user_result.scalar_one_or_none()
        if user:
            user.team_id = body.team_id
            count += 1

    return {"success": True, "assigned_count": count}


# ============================================================
# APP RULES
# ============================================================

@router.get("/teams/{team_id}/rules")
async def get_team_rules(
    team_id: str,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all app rules for a team."""
    result = await db.execute(
        select(TeamAppRule)
        .where(TeamAppRule.team_id == team_id)
        .order_by(TeamAppRule.category, TeamAppRule.app_pattern)
    )
    rules = result.scalars().all()

    return [
        {
            "id": r.id,
            "app_pattern": r.app_pattern,
            "category": r.category,
            "match_type": r.match_type,
        }
        for r in rules
    ]


@router.post("/teams/{team_id}/rules")
async def add_team_rule(
    team_id: str,
    body: RuleCreate,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Add a single app rule to a team."""
    # Verify team exists
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    # Check for duplicate
    existing = await db.execute(
        select(TeamAppRule).where(
            and_(TeamAppRule.team_id == team_id, TeamAppRule.app_pattern == body.app_pattern)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Rule for '{body.app_pattern}' already exists")

    rule = TeamAppRule(
        team_id=team_id,
        app_pattern=body.app_pattern,
        category=body.category,
        match_type=body.match_type,
    )
    db.add(rule)
    await db.flush()

    return {"id": rule.id, "app_pattern": rule.app_pattern, "category": rule.category, "success": True}


@router.put("/teams/{team_id}/rules/bulk")
async def bulk_update_rules(
    team_id: str,
    body: BulkRules,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Replace all rules for a team."""
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Team not found")

    # Delete existing rules
    await db.execute(delete(TeamAppRule).where(TeamAppRule.team_id == team_id))

    # Insert new rules
    count = 0
    for pattern in body.productive:
        db.add(TeamAppRule(team_id=team_id, app_pattern=pattern, category="productive"))
        count += 1
    for pattern in body.neutral:
        db.add(TeamAppRule(team_id=team_id, app_pattern=pattern, category="neutral"))
        count += 1
    for pattern in body.non_productive:
        db.add(TeamAppRule(team_id=team_id, app_pattern=pattern, category="non_productive"))
        count += 1

    return {"success": True, "total_rules": count}


@router.delete("/teams/{team_id}/rules/{rule_id}")
async def delete_team_rule(
    team_id: str,
    rule_id: int,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a single rule."""
    result = await db.execute(
        select(TeamAppRule).where(
            and_(TeamAppRule.id == rule_id, TeamAppRule.team_id == team_id)
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    return {"success": True, "message": f"Rule '{rule.app_pattern}' deleted"}


# ============================================================
# PRODUCTIVITY CALCULATION
# ============================================================

def classify_activity(app_name: str, window_title: str, rules: list[TeamAppRule]) -> str:
    """
    Classify a single activity log against team rules.
    Matches BOTH app_name and window_title (case-insensitive contains).
    Returns: 'productive', 'non_productive', or 'neutral'
    """
    combined = f"{app_name} {window_title or ''}".lower()

    for rule in rules:
        pattern = rule.app_pattern.lower()
        match = False

        if rule.match_type == "exact":
            match = pattern == app_name.lower() or pattern == (window_title or "").lower()
        elif rule.match_type == "startswith":
            match = app_name.lower().startswith(pattern) or (window_title or "").lower().startswith(pattern)
        else:  # contains (default)
            match = pattern in combined

        if match:
            return rule.category

    return "neutral"


@router.get("/teams/{team_id}/productivity")
async def get_team_productivity(
    team_id: str,
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get team productivity report for a given date.
    Classifies each activity log against team rules.
    Score = productive / (productive + non_productive) * 100
    """
    # Verify team
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Parse date
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # Get team members
    members_result = await db.execute(
        select(User).where(User.team_id == team_id)
    )
    members = members_result.scalars().all()

    if not members:
        return {
            "team_id": team_id,
            "team_name": team.name,
            "date": target_date.strftime("%Y-%m-%d"),
            "members": [],
            "summary": {
                "total_productive_seconds": 0,
                "total_neutral_seconds": 0,
                "total_non_productive_seconds": 0,
                "team_productivity_score": 0,
                "member_count": 0,
            }
        }

    # Get team rules
    rules_result = await db.execute(
        select(TeamAppRule).where(TeamAppRule.team_id == team_id)
    )
    rules = rules_result.scalars().all()

    INTERVAL = 5  # seconds per log entry

    team_productive = 0
    team_neutral = 0
    team_non_productive = 0
    member_reports = []

    for member in members:
        # Get activity logs for this member on this date
        logs_result = await db.execute(
            select(DesktopActivityLog)
            .where(
                and_(
                    DesktopActivityLog.user_id == member.id,
                    DesktopActivityLog.timestamp >= start_of_day,
                    DesktopActivityLog.timestamp < end_of_day,
                    DesktopActivityLog.is_idle == False,
                )
            )
            .order_by(DesktopActivityLog.timestamp)
        )
        logs = logs_result.scalars().all()

        productive_secs = 0
        neutral_secs = 0
        non_productive_secs = 0
        top_apps: dict[str, dict[str, int]] = {}  # app -> {productive, neutral, non_productive}

        for log in logs:
            category = classify_activity(log.app_name, log.window_title or "", rules)

            # Use combined name for display
            display_name = log.app_name

            if display_name not in top_apps:
                top_apps[display_name] = {"productive": 0, "neutral": 0, "non_productive": 0}
            top_apps[display_name][category] += INTERVAL

            if category == "productive":
                productive_secs += INTERVAL
            elif category == "non_productive":
                non_productive_secs += INTERVAL
            else:
                neutral_secs += INTERVAL

        denom = productive_secs + non_productive_secs
        score = round((productive_secs / denom) * 100) if denom > 0 else 0

        team_productive += productive_secs
        team_neutral += neutral_secs
        team_non_productive += non_productive_secs

        # Top apps sorted by total time
        sorted_apps = sorted(
            top_apps.items(),
            key=lambda x: sum(x[1].values()),
            reverse=True
        )[:10]

        member_reports.append({
            "user_id": member.id,
            "name": member.name,
            "email": member.email,
            "productive_seconds": productive_secs,
            "neutral_seconds": neutral_secs,
            "non_productive_seconds": non_productive_secs,
            "productivity_score": score,
            "total_logs": len(logs),
            "top_apps": [
                {
                    "name": app_name,
                    "productive_seconds": data["productive"],
                    "neutral_seconds": data["neutral"],
                    "non_productive_seconds": data["non_productive"],
                    "total_seconds": sum(data.values()),
                }
                for app_name, data in sorted_apps
            ],
        })

    team_denom = team_productive + team_non_productive
    team_score = round((team_productive / team_denom) * 100) if team_denom > 0 else 0

    return {
        "team_id": team_id,
        "team_name": team.name,
        "date": target_date.strftime("%Y-%m-%d"),
        "members": member_reports,
        "summary": {
            "total_productive_seconds": team_productive,
            "total_neutral_seconds": team_neutral,
            "total_non_productive_seconds": team_non_productive,
            "team_productivity_score": team_score,
            "member_count": len(members),
        }
    }


# ============================================================
# TEAM COMPARISON
# ============================================================

@router.get("/teams/compare")
async def compare_teams(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Compare productivity scores across all teams for a given date."""
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    result = await db.execute(select(Team))
    teams = result.scalars().all()

    comparison = []

    for team in teams:
        # Get members
        members_result = await db.execute(select(User).where(User.team_id == team.id))
        members = members_result.scalars().all()

        if not members:
            comparison.append({
                "team_id": team.id,
                "team_name": team.name,
                "productivity_score": 0,
                "productive_seconds": 0,
                "neutral_seconds": 0,
                "non_productive_seconds": 0,
                "member_count": 0,
                "active_members": 0,
            })
            continue

        # Get rules
        rules_result = await db.execute(select(TeamAppRule).where(TeamAppRule.team_id == team.id))
        rules = rules_result.scalars().all()

        t_prod = 0
        t_neutral = 0
        t_nonprod = 0
        active_count = 0
        INTERVAL = 5

        for member in members:
            logs_result = await db.execute(
                select(DesktopActivityLog).where(
                    and_(
                        DesktopActivityLog.user_id == member.id,
                        DesktopActivityLog.timestamp >= start_of_day,
                        DesktopActivityLog.timestamp < end_of_day,
                        DesktopActivityLog.is_idle == False,
                    )
                )
            )
            logs = logs_result.scalars().all()

            if logs:
                active_count += 1

            for log in logs:
                cat = classify_activity(log.app_name, log.window_title or "", rules)
                if cat == "productive":
                    t_prod += INTERVAL
                elif cat == "non_productive":
                    t_nonprod += INTERVAL
                else:
                    t_neutral += INTERVAL

        denom = t_prod + t_nonprod
        score = round((t_prod / denom) * 100) if denom > 0 else 0

        comparison.append({
            "team_id": team.id,
            "team_name": team.name,
            "productivity_score": score,
            "productive_seconds": t_prod,
            "neutral_seconds": t_neutral,
            "non_productive_seconds": t_nonprod,
            "member_count": len(members),
            "active_members": active_count,
        })

    # Sort by score descending
    comparison.sort(key=lambda x: x["productivity_score"], reverse=True)

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "teams": comparison,
    }


# ============================================================
# HISTORICAL TRENDS
# ============================================================

@router.get("/teams/{team_id}/trends")
async def get_team_trends(
    team_id: str,
    days: int = Query(7, ge=1, le=30, description="Number of days"),
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get daily productivity scores for past N days."""
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get members
    members_result = await db.execute(select(User).where(User.team_id == team_id))
    members = members_result.scalars().all()

    # Get rules
    rules_result = await db.execute(select(TeamAppRule).where(TeamAppRule.team_id == team_id))
    rules = rules_result.scalars().all()

    INTERVAL = 5
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    trend_data = []

    for i in range(days - 1, -1, -1):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        day_prod = 0
        day_neutral = 0
        day_nonprod = 0
        active_count = 0

        for member in members:
            logs_result = await db.execute(
                select(DesktopActivityLog).where(
                    and_(
                        DesktopActivityLog.user_id == member.id,
                        DesktopActivityLog.timestamp >= day_start,
                        DesktopActivityLog.timestamp < day_end,
                        DesktopActivityLog.is_idle == False,
                    )
                )
            )
            logs = logs_result.scalars().all()

            if logs:
                active_count += 1

            for log in logs:
                cat = classify_activity(log.app_name, log.window_title or "", rules)
                if cat == "productive":
                    day_prod += INTERVAL
                elif cat == "non_productive":
                    day_nonprod += INTERVAL
                else:
                    day_neutral += INTERVAL

        denom = day_prod + day_nonprod
        score = round((day_prod / denom) * 100) if denom > 0 else 0

        trend_data.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "day": day_start.strftime("%a"),
            "productivity_score": score,
            "productive_seconds": day_prod,
            "neutral_seconds": day_neutral,
            "non_productive_seconds": day_nonprod,
            "active_members": active_count,
        })

    return {
        "team_id": team_id,
        "team_name": team.name,
        "days": days,
        "trends": trend_data,
    }


# ============================================================
# AUTO-RULE SUGGESTIONS
# ============================================================

# Common app category heuristics
_PRODUCTIVE_HINTS = [
    "visual studio", "vscode", "code", "pycharm", "intellij", "webstorm",
    "android studio", "xcode", "eclipse", "sublime", "vim", "neovim",
    "terminal", "powershell", "cmd", "git", "github", "gitlab", "bitbucket",
    "jira", "confluence", "notion", "linear", "asana", "trello",
    "figma", "sketch", "adobe", "photoshop", "illustrator",
    "postman", "insomnia", "docker", "kubernetes",
    "slack", "teams", "microsoft teams", "zoom",
    "google docs", "google sheets", "google slides",
    "excel", "word", "powerpoint", "outlook",
    "encord", "labelbox", "roboflow",
]

_NON_PRODUCTIVE_HINTS = [
    "youtube", "netflix", "twitch", "tiktok", "instagram", "facebook",
    "twitter", "reddit", "9gag", "imgur", "pinterest",
    "spotify", "music", "whatsapp", "telegram", "discord",
    "steam", "epic games", "game", "gaming",
    "amazon", "flipkart", "shopping", "ebay",
]


@router.get("/teams/{team_id}/suggest-rules")
async def suggest_rules(
    team_id: str,
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyze activity data and suggest app categorizations.
    Finds the top apps used by team members that don't already have rules,
    and suggests categories using heuristics.
    """
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get team members
    members_result = await db.execute(select(User).where(User.team_id == team_id))
    members = members_result.scalars().all()
    member_ids = [m.id for m in members]

    if not member_ids:
        return {"team_id": team_id, "suggestions": []}

    # Get existing rules patterns
    rules_result = await db.execute(
        select(TeamAppRule.app_pattern).where(TeamAppRule.team_id == team_id)
    )
    existing_patterns = {r.lower() for r in rules_result.scalars().all()}

    # Get last 7 days of activity
    since = datetime.now() - timedelta(days=7)

    # Find top apps by usage
    app_usage: dict[str, int] = {}
    for mid in member_ids:
        logs_result = await db.execute(
            select(DesktopActivityLog.app_name).where(
                and_(
                    DesktopActivityLog.user_id == mid,
                    DesktopActivityLog.timestamp >= since,
                    DesktopActivityLog.is_idle == False,
                )
            )
        )
        for (app_name,) in logs_result.all():
            if app_name:
                app_usage[app_name] = app_usage.get(app_name, 0) + 5

    # Filter out apps that already have matching rules
    unclassified = {}
    for app, secs in app_usage.items():
        app_lower = app.lower()
        already_covered = any(pat in app_lower for pat in existing_patterns)
        if not already_covered:
            unclassified[app] = secs

    # Sort by usage and take top 20
    top_unclassified = sorted(unclassified.items(), key=lambda x: x[1], reverse=True)[:20]

    suggestions = []
    for app_name, total_secs in top_unclassified:
        app_lower = app_name.lower()

        # Heuristic categorization
        suggested = "neutral"
        confidence = "low"

        for hint in _PRODUCTIVE_HINTS:
            if hint in app_lower:
                suggested = "productive"
                confidence = "high"
                break

        if suggested == "neutral":
            for hint in _NON_PRODUCTIVE_HINTS:
                if hint in app_lower:
                    suggested = "non_productive"
                    confidence = "high"
                    break

        suggestions.append({
            "app_pattern": app_name,
            "suggested_category": suggested,
            "confidence": confidence,
            "total_seconds": total_secs,
            "usage_display": f"{total_secs // 3600}h {(total_secs % 3600) // 60}m" if total_secs >= 3600 else f"{total_secs // 60}m",
        })

    return {
        "team_id": team_id,
        "team_name": team.name,
        "suggestions": suggestions,
    }


# ============================================================
# CSV EXPORT
# ============================================================

@router.get("/teams/{team_id}/export")
async def export_team_report(
    team_id: str,
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Export team productivity report as CSV."""
    from fastapi.responses import StreamingResponse
    import io

    # Get the productivity data using existing logic
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    members_result = await db.execute(select(User).where(User.team_id == team_id))
    members = members_result.scalars().all()

    rules_result = await db.execute(select(TeamAppRule).where(TeamAppRule.team_id == team_id))
    rules = rules_result.scalars().all()

    INTERVAL = 5

    # Build CSV
    output = io.StringIO()
    output.write("Employee,Email,Productive Time,Neutral Time,Non-Productive Time,Productivity Score,Top Apps\n")

    for member in members:
        logs_result = await db.execute(
            select(DesktopActivityLog).where(
                and_(
                    DesktopActivityLog.user_id == member.id,
                    DesktopActivityLog.timestamp >= start_of_day,
                    DesktopActivityLog.timestamp < end_of_day,
                    DesktopActivityLog.is_idle == False,
                )
            )
        )
        logs = logs_result.scalars().all()

        prod = 0
        neutral = 0
        nonprod = 0
        app_times: dict[str, int] = {}

        for log in logs:
            cat = classify_activity(log.app_name, log.window_title or "", rules)
            if cat == "productive":
                prod += INTERVAL
            elif cat == "non_productive":
                nonprod += INTERVAL
            else:
                neutral += INTERVAL
            app_times[log.app_name] = app_times.get(log.app_name, 0) + INTERVAL

        denom = prod + nonprod
        score = round((prod / denom) * 100) if denom > 0 else 0

        top_apps = sorted(app_times.items(), key=lambda x: x[1], reverse=True)[:5]
        top_apps_str = "; ".join(f"{a} ({s // 60}m)" for a, s in top_apps)

        def fmt_time(s: int) -> str:
            h, m = s // 3600, (s % 3600) // 60
            return f"{h}h {m}m" if h > 0 else f"{m}m"

        name_clean = member.name.replace('"', '""')
        email_clean = member.email.replace('"', '""')
        apps_clean = top_apps_str.replace('"', '""')

        output.write(f'"{name_clean}","{email_clean}","{fmt_time(prod)}","{fmt_time(neutral)}","{fmt_time(nonprod)}",{score}%,"{apps_clean}"\n')

    csv_content = output.getvalue()
    output.close()

    date_str = target_date.strftime("%Y-%m-%d")
    filename = f"{team.name.replace(' ', '_')}_productivity_{date_str}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ============================================================
# MEMBER DRILL-DOWN
# ============================================================

@router.get("/teams/{team_id}/members/{user_id}/activity")
async def get_member_activity(
    team_id: str,
    user_id: str,
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    _admin: TokenData = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Detailed app-by-app breakdown for a single team member."""
    # Verify team and member
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            target_date = datetime.now()
    else:
        target_date = datetime.now()

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # Get team rules
    rules_result = await db.execute(select(TeamAppRule).where(TeamAppRule.team_id == team_id))
    rules = rules_result.scalars().all()

    # Get activity logs
    logs_result = await db.execute(
        select(DesktopActivityLog).where(
            and_(
                DesktopActivityLog.user_id == user_id,
                DesktopActivityLog.timestamp >= start_of_day,
                DesktopActivityLog.timestamp < end_of_day,
                DesktopActivityLog.is_idle == False,
            )
        ).order_by(DesktopActivityLog.timestamp)
    )
    logs = logs_result.scalars().all()

    INTERVAL = 5
    prod = 0
    neutral = 0
    nonprod = 0
    app_details: dict[str, dict] = {}  # app_name -> {productive, neutral, non_productive, windows: set}
    timeline: list[dict] = []

    for log in logs:
        cat = classify_activity(log.app_name, log.window_title or "", rules)

        if cat == "productive":
            prod += INTERVAL
        elif cat == "non_productive":
            nonprod += INTERVAL
        else:
            neutral += INTERVAL

        if log.app_name not in app_details:
            app_details[log.app_name] = {
                "productive": 0,
                "neutral": 0,
                "non_productive": 0,
                "windows": set(),
            }
        app_details[log.app_name][cat] += INTERVAL
        if log.window_title:
            app_details[log.app_name]["windows"].add(log.window_title[:80])

        # Build simplified timeline (sample every 12 entries = 1 minute)
        if len(timeline) == 0 or len(logs) < 200 or logs.index(log) % 12 == 0:
            timeline.append({
                "time": log.timestamp.strftime("%H:%M"),
                "app": log.app_name,
                "category": cat,
            })

    denom = prod + nonprod
    score = round((prod / denom) * 100) if denom > 0 else 0

    # Build app breakdown
    apps = []
    for app_name, data in sorted(app_details.items(), key=lambda x: sum(v for k, v in x[1].items() if k != "windows"), reverse=True):
        total = data["productive"] + data["neutral"] + data["non_productive"]
        primary_cat = max(
            ["productive", "neutral", "non_productive"],
            key=lambda c: data[c]
        )
        apps.append({
            "app_name": app_name,
            "productive_seconds": data["productive"],
            "neutral_seconds": data["neutral"],
            "non_productive_seconds": data["non_productive"],
            "total_seconds": total,
            "primary_category": primary_cat,
            "windows": list(data["windows"])[:5],
        })

    return {
        "team_id": team_id,
        "team_name": team.name,
        "user_id": user_id,
        "name": user.name,
        "email": user.email,
        "date": target_date.strftime("%Y-%m-%d"),
        "productive_seconds": prod,
        "neutral_seconds": neutral,
        "non_productive_seconds": nonprod,
        "productivity_score": score,
        "total_seconds": prod + neutral + nonprod,
        "apps": apps,
        "timeline": timeline[:100],  # Cap at 100 entries
    }

