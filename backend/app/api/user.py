"""
User settings and reports API routes
"""
import json
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from datetime import datetime

from backend.app.db import get_db, User, UserSettings, Report
from backend.app.services.auth_utils import verify_access_token, encrypt_settings, decrypt_settings

router = APIRouter(prefix="/api/user", tags=["User"])


# ============== Pydantic Models ==============

class SettingsUpdate(BaseModel):
    """API settings to save"""
    openai_api_key: str = ""
    alpha_vantage_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    grok_api_key: str = ""
    deepseek_api_key: str = ""
    qwen_api_key: str = ""
    finmind_api_key: str = ""
    custom_base_url: str = ""
    custom_api_key: str = ""


class ReportCreate(BaseModel):
    """Report to save"""
    ticker: str
    market_type: str  # us, twse, tpex
    analysis_date: str
    result: dict
    language: Optional[str] = None


class ReportResponse(BaseModel):
    """Report response"""
    id: str
    ticker: str
    market_type: str
    analysis_date: str
    result: dict
    language: Optional[str] = None
    created_at: str


# ============== Auth Dependency ==============

async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user from JWT token (optional - returns None if not authenticated)"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "")
    payload = verify_access_token(token)
    
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    try:
        result = await db.execute(
            select(User).where(User.id == UUID(user_id))
        )
        return result.scalar_one_or_none()
    except:
        return None


async def get_current_user_required(
    user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    """Require authenticated user"""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ============== Settings Routes ==============

@router.get("/settings")
async def get_settings(
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Get user's saved API settings (decrypted)"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        return {"settings": None}
    
    try:
        decrypted = decrypt_settings(settings.encrypted_settings)
        return {"settings": json.loads(decrypted)}
    except Exception as e:
        print(f"Failed to decrypt settings: {e}")
        return {"settings": None}


@router.put("/settings")
async def update_settings(
    settings_data: SettingsUpdate,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Save user's API settings (encrypted)"""
    # Convert to JSON and encrypt
    settings_json = json.dumps(settings_data.model_dump())
    encrypted = encrypt_settings(settings_json)
    
    # Find existing settings
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        existing.encrypted_settings = encrypted
        existing.updated_at = datetime.utcnow()
    else:
        new_settings = UserSettings(
            user_id=user.id,
            encrypted_settings=encrypted
        )
        db.add(new_settings)
    
    await db.commit()
    
    return {"success": True, "message": "Settings saved successfully"}


# ============== Reports Routes ==============

@router.get("/reports", response_model=List[ReportResponse])
async def get_reports(
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
    market_type: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get user's reports with optional filtering and pagination

    Args:
        market_type: Filter by market type (us, twse, tpex)
        language: Filter by language (en, zh-TW)
        limit: Maximum number of reports to return (default 100, max 500)
        offset: Number of reports to skip for pagination
    """
    # Cap limit at 500 to prevent memory issues
    limit = min(limit, 500)

    # Build query with filters
    query = select(Report).where(Report.user_id == user.id)

    if market_type:
        query = query.where(Report.market_type == market_type)

    if language:
        query = query.where(Report.language == language)

    # Order by created_at DESC and apply pagination
    query = query.order_by(Report.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    reports = result.scalars().all()

    return [
        ReportResponse(
            id=str(r.id),
            ticker=r.ticker,
            market_type=r.market_type,
            analysis_date=r.analysis_date,
            result=r.result,
            language=r.language,
            created_at=r.created_at.isoformat() + "Z"
        )
        for r in reports
    ]


@router.post("/reports")
async def create_report(
    report_data: ReportCreate,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Save a report (upsert: update if same ticker/date/market_type/language exists)"""
    # Normalize language: treat None as "zh-TW" to avoid NULL matching issues
    language = report_data.language or "zh-TW"

    # Check for existing report with same key to prevent duplicates
    existing_result = await db.execute(
        select(Report)
        .where(Report.user_id == user.id)
        .where(Report.ticker == report_data.ticker)
        .where(Report.analysis_date == report_data.analysis_date)
        .where(Report.market_type == report_data.market_type)
        .where(func.coalesce(Report.language, "zh-TW") == language)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        # Update existing report instead of creating a duplicate
        existing.result = report_data.result
        existing.language = language
        await db.commit()
        return {
            "success": True,
            "report_id": str(existing.id),
            "message": "Report updated successfully"
        }

    # No existing report found — create new
    report = Report(
        user_id=user.id,
        ticker=report_data.ticker,
        market_type=report_data.market_type,
        analysis_date=report_data.analysis_date,
        result=report_data.result,
        language=language,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    return {
        "success": True,
        "report_id": str(report.id),
        "message": "Report saved successfully"
    }


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific report"""
    try:
        result = await db.execute(
            select(Report)
            .where(Report.id == UUID(report_id))
            .where(Report.user_id == user.id)
        )
        report = result.scalar_one_or_none()
    except:
        raise HTTPException(status_code=400, detail="Invalid report ID")
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return ReportResponse(
        id=str(report.id),
        ticker=report.ticker,
        market_type=report.market_type,
        analysis_date=report.analysis_date,
        result=report.result,
        language=report.language,
        created_at=report.created_at.isoformat() + "Z"
    )


@router.delete("/reports/cleanup-duplicates")
async def cleanup_duplicate_reports(
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Remove duplicate reports, keeping only the most recent one per (ticker, analysis_date, market_type, language)"""
    # Fetch all user reports ordered newest first
    result = await db.execute(
        select(Report)
        .where(Report.user_id == user.id)
        .order_by(Report.created_at.desc())
    )
    all_reports = result.scalars().all()

    seen: set = set()
    ids_to_delete: list = []

    for report in all_reports:
        # Normalize language
        lang = report.language or "zh-TW"
        key = (report.ticker, report.analysis_date, report.market_type, lang)
        if key in seen:
            ids_to_delete.append(report.id)
        else:
            seen.add(key)

    if ids_to_delete:
        await db.execute(
            delete(Report)
            .where(Report.user_id == user.id)
            .where(Report.id.in_(ids_to_delete))
        )
        await db.commit()

    return {
        "success": True,
        "deleted": len(ids_to_delete),
        "message": f"Cleaned up {len(ids_to_delete)} duplicate reports"
    }


@router.delete("/reports/{report_id}")
async def delete_report(
    report_id: str,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Delete a report"""
    try:
        result = await db.execute(
            select(Report)
            .where(Report.id == UUID(report_id))
            .where(Report.user_id == user.id)
        )
        report = result.scalar_one_or_none()
    except:
        raise HTTPException(status_code=400, detail="Invalid report ID")
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    await db.delete(report)
    await db.commit()
    
    return {"success": True, "message": "Report deleted successfully"}


@router.delete("/reports")
async def delete_all_reports(
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db)
):
    """Delete all user's reports"""
    await db.execute(
        delete(Report).where(Report.user_id == user.id)
    )
    await db.commit()
    
    return {"success": True, "message": "All reports deleted successfully"}
