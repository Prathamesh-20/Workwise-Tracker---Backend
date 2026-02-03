"""
Categorization API endpoints - Batch 8
Manage domain categorization rules
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.schemas import TokenData
from app.auth import get_current_user, get_admin_user
from app.categorization import (
    categorize_domain,
    add_custom_rule,
    remove_custom_rule,
    get_all_custom_rules,
    get_category_stats,
    CategoryType,
    get_category_color,
    PRODUCTIVE_DOMAINS,
    DISTRACTION_DOMAINS,
)

router = APIRouter()


# ============================================================
# REQUEST/RESPONSE MODELS
# ============================================================

class DomainRuleRequest(BaseModel):
    domain: str
    category: str  # productive, distraction, neutral


class CategorizeRequest(BaseModel):
    domain: str


# ============================================================
# ENDPOINTS
# ============================================================

@router.post("/categorize")
async def categorize_single_domain(
    data: CategorizeRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Get the category for a single domain.
    """
    result = categorize_domain(data.domain)
    result["color"] = get_category_color(result["category"])
    return result


@router.post("/rules", status_code=201)
async def add_rule(
    data: DomainRuleRequest,
    admin: TokenData = Depends(get_admin_user)
):
    """
    Add a custom categorization rule (Admin only).
    """
    if data.category not in [CategoryType.PRODUCTIVE, CategoryType.DISTRACTION, CategoryType.NEUTRAL]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {CategoryType.PRODUCTIVE}, {CategoryType.DISTRACTION}, {CategoryType.NEUTRAL}"
        )
    
    add_custom_rule(data.domain, data.category)
    
    return {
        "message": f"Rule added: {data.domain} -> {data.category}",
        "domain": data.domain,
        "category": data.category,
    }


@router.delete("/rules/{domain}")
async def delete_rule(
    domain: str,
    admin: TokenData = Depends(get_admin_user)
):
    """
    Remove a custom rule (Admin only).
    """
    if remove_custom_rule(domain):
        return {"message": f"Rule removed: {domain}"}
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No custom rule found for: {domain}"
        )


@router.get("/rules")
async def list_rules(
    admin: TokenData = Depends(get_admin_user)
):
    """
    List all categorization rules (Admin only).
    """
    return {
        "custom_rules": get_all_custom_rules(),
        "default_productive_count": len(PRODUCTIVE_DOMAINS),
        "default_distraction_count": len(DISTRACTION_DOMAINS),
    }


@router.get("/defaults")
async def get_default_domains(
    admin: TokenData = Depends(get_admin_user)
):
    """
    Get default domain categorizations (Admin only).
    """
    return {
        "productive": sorted(list(PRODUCTIVE_DOMAINS)),
        "distraction": sorted(list(DISTRACTION_DOMAINS)),
    }
