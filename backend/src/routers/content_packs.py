"""
SchemeKnit Content Pack Router

CRUD operations for content packs.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_db, User, ContentPackDB, ContentPackLessonDB, ContentPackPurchaseDB, generate_id
from ..auth import get_current_user, require_admin
from ..logging_config import get_logger

router = APIRouter()
logger = get_logger()


class ContentPackCreateRequest(BaseModel):
    name: str
    description: str = ""
    class_level: str
    subject: str
    term: str
    academic_year: str
    educational_level: str
    template_family: str
    version: str = "1.0"
    author: str = "SchemeKnit"
    is_official: bool = False
    is_premium: bool = False
    price: float = 0.0


class ContentPackUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    is_premium: Optional[bool] = None
    price: Optional[float] = None
    status: Optional[str] = None


@router.get("/")
async def list_content_packs(
    educational_level: Optional[str] = None,
    class_level: Optional[str] = None,
    subject: Optional[str] = None,
    db=Depends(get_db),
):
    """List content packs with optional filters."""
    q = db.query(ContentPackDB).filter(ContentPackDB.status == "active")
    if educational_level:
        q = q.filter(ContentPackDB.educational_level == educational_level)
    if class_level:
        q = q.filter(ContentPackDB.class_level == class_level)
    if subject:
        q = q.filter(ContentPackDB.subject == subject)

    packs = q.order_by(ContentPackDB.created_at.desc()).all()
    return {
        "packs": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "class_level": p.class_level,
                "subject": p.subject,
                "term": p.term,
                "academic_year": p.academic_year,
                "educational_level": p.educational_level,
                "template_family": p.template_family,
                "version": p.version,
                "author": p.author,
                "is_official": p.is_official,
                "is_premium": p.is_premium,
                "price": p.price,
                "lesson_count": p.lesson_count,
                "status": p.status,
            }
            for p in packs
        ],
        "total": len(packs),
    }


@router.get("/{pack_id}")
async def get_content_pack(pack_id: str, db=Depends(get_db)):
    """Get a specific content pack."""
    pack = db.query(ContentPackDB).filter(ContentPackDB.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")

    return {
        "id": pack.id,
        "name": pack.name,
        "description": pack.description,
        "class_level": pack.class_level,
        "subject": pack.subject,
        "term": pack.term,
        "academic_year": pack.academic_year,
        "educational_level": pack.educational_level,
        "template_family": pack.template_family,
        "version": pack.version,
        "author": pack.author,
        "is_official": pack.is_official,
        "is_premium": pack.is_premium,
        "price": pack.price,
        "lesson_count": pack.lesson_count,
        "status": pack.status,
    }


@router.post("/")
async def create_content_pack(
    req: ContentPackCreateRequest,
    user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Create a content pack (admin only)."""
    pack = ContentPackDB(
        id=generate_id(),
        name=req.name,
        description=req.description,
        class_level=req.class_level,
        subject=req.subject,
        term=req.term,
        academic_year=req.academic_year,
        educational_level=req.educational_level,
        template_family=req.template_family,
        version=req.version,
        author=req.author,
        is_official=req.is_official,
        is_premium=req.is_premium,
        price=req.price,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(pack)
    db.commit()
    db.refresh(pack)
    return {"id": pack.id, "message": "Content pack created."}


@router.put("/{pack_id}")
async def update_content_pack(
    pack_id: str,
    req: ContentPackUpdateRequest,
    user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Update a content pack (admin only)."""
    pack = db.query(ContentPackDB).filter(ContentPackDB.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")

    if req.name is not None:
        pack.name = req.name
    if req.description is not None:
        pack.description = req.description
    if req.version is not None:
        pack.version = req.version
    if req.is_premium is not None:
        pack.is_premium = req.is_premium
    if req.price is not None:
        pack.price = req.price
    if req.status is not None:
        pack.status = req.status
    pack.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Content pack updated."}


@router.delete("/{pack_id}")
async def archive_content_pack(
    pack_id: str,
    user: User = Depends(require_admin),
    db=Depends(get_db),
):
    """Archive a content pack (admin only). Soft delete."""
    pack = db.query(ContentPackDB).filter(ContentPackDB.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")

    has_purchases = db.query(ContentPackPurchaseDB).filter(
        ContentPackPurchaseDB.pack_id == pack_id
    ).count() > 0

    if has_purchases:
        pack.status = "archived"
    else:
        db.delete(pack)
    pack.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Content pack archived."}


@router.get("/{pack_id}/lessons")
async def get_pack_lessons(pack_id: str, db=Depends(get_db)):
    """Get lessons in a content pack."""
    pack = db.query(ContentPackDB).filter(ContentPackDB.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")

    lessons = db.query(ContentPackLessonDB).filter(
        ContentPackLessonDB.pack_id == pack_id
    ).order_by(ContentPackLessonDB.week_number, ContentPackLessonDB.lesson_sequence).all()

    return {
        "pack_id": pack_id,
        "lessons": [
            {
                "id": l.id,
                "week_number": l.week_number,
                "lesson_sequence": l.lesson_sequence,
                "preview_text": l.preview_text,
            }
            for l in lessons
        ],
        "total": len(lessons),
    }
