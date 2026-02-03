"""
Productivity Categorization Engine - Batch 8
Auto-categorizes domains as productive, distraction, or neutral
"""

from typing import Optional

# ============================================================
# DEFAULT CATEGORIZATION RULES
# ============================================================

# Productive domains - work-related
PRODUCTIVE_DOMAINS = {
    # Development
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "stackoverflow.com",
    "developer.mozilla.org",
    
    # Communication
    "slack.com",
    "teams.microsoft.com",
    "discord.com",
    "zoom.us",
    
    # Productivity tools
    "notion.so",
    "trello.com",
    "asana.com",
    "jira.atlassian.com",
    "confluence.atlassian.com",
    "monday.com",
    "clickup.com",
    
    # Google Workspace
    "docs.google.com",
    "sheets.google.com",
    "slides.google.com",
    "drive.google.com",
    "calendar.google.com",
    "mail.google.com",
    
    # Microsoft 365
    "outlook.office.com",
    "office.com",
    "onedrive.com",
    
    # Design
    "figma.com",
    "canva.com",
    "adobe.com",
    
    # Cloud providers
    "console.aws.amazon.com",
    "console.cloud.google.com",
    "portal.azure.com",
    "vercel.com",
    "railway.app",
    "heroku.com",
    
    # Learning
    "udemy.com",
    "coursera.org",
    "linkedin.com/learning",
}

# Distraction domains - entertainment/social
DISTRACTION_DOMAINS = {
    # Social media
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "snapchat.com",
    "pinterest.com",
    
    # Entertainment
    "youtube.com",
    "netflix.com",
    "hulu.com",
    "disneyplus.com",
    "primevideo.com",
    "twitch.tv",
    "spotify.com",
    
    # Gaming
    "steampowered.com",
    "epicgames.com",
    "roblox.com",
    
    # News/Forums
    "reddit.com",
    "9gag.com",
    "buzzfeed.com",
    
    # Shopping
    "amazon.com",
    "ebay.com",
    "etsy.com",
    "aliexpress.com",
}

# ============================================================
# CATEGORIZATION LOGIC
# ============================================================

class CategoryType:
    PRODUCTIVE = "productive"
    DISTRACTION = "distraction"
    NEUTRAL = "neutral"


# Custom rules storage (in production, load from DB)
_custom_rules: dict[str, str] = {}


def categorize_domain(domain: str) -> dict:
    """
    Categorize a domain as productive, distraction, or neutral.
    
    Priority:
    1. Custom rules (admin-defined)
    2. Default productive list
    3. Default distraction list
    4. Neutral (fallback)
    """
    domain_lower = domain.lower()
    
    # Check custom rules first
    if domain_lower in _custom_rules:
        category_type = _custom_rules[domain_lower]
        return {
            "domain": domain,
            "category": category_type,
            "source": "custom",
        }
    
    # Check if domain or parent domain is in productive list
    for prod_domain in PRODUCTIVE_DOMAINS:
        if domain_lower == prod_domain or domain_lower.endswith(f".{prod_domain}"):
            return {
                "domain": domain,
                "category": CategoryType.PRODUCTIVE,
                "source": "default",
            }
    
    # Check distraction list
    for dist_domain in DISTRACTION_DOMAINS:
        if domain_lower == dist_domain or domain_lower.endswith(f".{dist_domain}"):
            return {
                "domain": domain,
                "category": CategoryType.DISTRACTION,
                "source": "default",
            }
    
    # Default to neutral
    return {
        "domain": domain,
        "category": CategoryType.NEUTRAL,
        "source": "default",
    }


def add_custom_rule(domain: str, category_type: str) -> None:
    """Add a custom categorization rule"""
    _custom_rules[domain.lower()] = category_type


def remove_custom_rule(domain: str) -> bool:
    """Remove a custom rule, returns True if existed"""
    return _custom_rules.pop(domain.lower(), None) is not None


def get_all_custom_rules() -> dict[str, str]:
    """Get all custom rules"""
    return _custom_rules.copy()


def get_category_color(category_type: str) -> str:
    """Get display color for category"""
    colors = {
        CategoryType.PRODUCTIVE: "#00d26a",  # Green
        CategoryType.DISTRACTION: "#ff6b6b",  # Red
        CategoryType.NEUTRAL: "#808080",      # Gray
    }
    return colors.get(category_type, "#808080")


def get_category_stats(logs: list[dict]) -> dict:
    """
    Calculate productivity statistics from logs.
    Returns time breakdown by category.
    """
    stats = {
        CategoryType.PRODUCTIVE: 0,
        CategoryType.DISTRACTION: 0,
        CategoryType.NEUTRAL: 0,
        "total": 0,
    }
    
    for log in logs:
        domain = log.get("domain", "")
        duration = log.get("duration_seconds", 0)
        is_idle = log.get("is_idle", False)
        
        if is_idle:
            continue  # Don't count idle time
        
        category_info = categorize_domain(domain)
        category = category_info["category"]
        
        stats[category] = stats.get(category, 0) + duration
        stats["total"] += duration
    
    # Calculate percentages
    total = stats["total"] or 1  # Avoid division by zero
    stats["productive_percent"] = round(stats[CategoryType.PRODUCTIVE] / total * 100, 1)
    stats["distraction_percent"] = round(stats[CategoryType.DISTRACTION] / total * 100, 1)
    stats["neutral_percent"] = round(stats[CategoryType.NEUTRAL] / total * 100, 1)
    
    return stats
