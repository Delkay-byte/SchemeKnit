"""Authenticated referral endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_platform_admin
from ..database import get_db, User
from .. import referrals

router = APIRouter()


class TrackRequest(BaseModel):
    code: str


class SettingsRequest(BaseModel):
    reward_referrer: int
    reward_referred: int
    term_limit: int


@router.get("/me")
async def my_referrals(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return referrals.stats(db, user)


@router.post("/track")
async def track(req: TrackRequest, db: Session = Depends(get_db)):
    """Record a referral-link open. Safe for anonymous visitors."""
    return {"tracked": referrals.track_visit(db, req.code)}


@router.put("/settings")
async def update_settings(
    req: SettingsRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if req.reward_referrer < 0 or req.reward_referred < 0 or req.term_limit < 1:
        raise HTTPException(status_code=422, detail="Referral settings are invalid.")
    cfg = referrals.settings(db)
    cfg.reward_referrer = int(req.reward_referrer)
    cfg.reward_referred = int(req.reward_referred)
    cfg.term_limit = int(req.term_limit)
    cfg.updated_by = admin.id
    db.commit()
    return {
        "reward_referrer": cfg.reward_referrer,
        "reward_referred": cfg.reward_referred,
        "term_limit": cfg.term_limit,
    }
