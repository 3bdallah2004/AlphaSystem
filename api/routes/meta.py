from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

import analysis
import geocode
from api.deps import get_language
from api.routes.common import fail
from config import MAX_ATTACHMENT_MB
from i18n import CASE_TYPES, SEVERITIES, STATUSES
from samples import SAMPLES

router = APIRouter()


@router.get("/health")
def health(lang=Depends(get_language)):
    level, message = analysis.check_n8n(lang)
    return {"level": level, "message": message}


@router.get("/meta")
def metadata():
    return {
        "case_types": CASE_TYPES,
        "statuses": STATUSES,
        "severities": SEVERITIES,
        "max_attachment_mb": MAX_ATTACHMENT_MB,
    }


@router.get("/samples")
def samples(lang=Depends(get_language)):
    return SAMPLES[lang]


@router.get("/geocode")
def geocode_place(q: str = Query(min_length=1), lang=Depends(get_language)):
    point = geocode.find(q, lang)
    return {"latitude": point[0], "longitude": point[1]} if point else None


@router.get("/assets/{asset_name}")
def get_about_asset(asset_name: str, lang=Depends(get_language)):
    assets_dir = Path(__file__).resolve().parents[2] / "app" / "assets"
    allowed = {"about-video-user.mp4": "video/mp4"}
    if asset_name not in allowed:
        fail(404, "asset_not_found", "الملف غير موجود." if lang == "ar" else "Asset not found.")
    path = assets_dir / asset_name
    if not path.is_file():
        fail(404, "asset_not_found", "الملف غير موجود." if lang == "ar" else "Asset not found.")
    return FileResponse(path, media_type=allowed[asset_name])
