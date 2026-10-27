from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import Response as StarletteResponse

import analysis
import attachments
import db
import geocode
from api.deps import get_language
from api.routes.common import fail, not_found, require_case
from api.schemas import CaseCreate, CasePatch
from i18n import CASE_TYPES

router = APIRouter()
CSV_HEADERS = ["id", "number", "name", "type", "status", "severity", "location", "latitude",
               "longitude", "date", "case_text", "report_text", "timestamp"]


@router.get("/cases")
def list_cases(q: str = "", type: str | None = None, status_filter: str | None = Query(None, alias="status"),
               severity: str | None = None, lang=Depends(get_language)):
    rows = db.list_cases(search=q, case_type=type, status=status_filter, severity=severity)
    counts = db.attachment_counts()
    for row in rows:
        row["attachment_count"], row["attachment_bytes"] = counts.get(row["id"], (0, 0))
    analysis.locate_missing([row["id"] for row in rows], lang)
    return {"cases": rows, "stats": db.stats(), "count": len(rows)}


@router.get("/cases/export.csv")
def export_cases():
    return StarletteResponse(
        db.export_cases_csv(CSV_HEADERS),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="alpha-cases.csv"'},
    )


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate, lang=Depends(get_language)):
    case_id = db.create_draft(payload.case_text)
    case = db.get_case(case_id)
    case["case_number"] = db.next_case_number()
    db.update_case(case_id, case_number=case["case_number"])
    return case


@router.get("/cases/{case_id}")
def get_case(case_id: int, lang=Depends(get_language)):
    case = require_case(case_id, lang, db)
    report_text = case.get("report_text") or ""
    case.pop("worker", None)
    return {
        **case,
        "report": analysis.parse_report(report_text),
        "report_raw": report_text,
        "versions": db.list_report_versions(case_id),
        "attachments": db.list_case_files(case_id),
        "message_count": len(db.list_messages(case_id)),
    }


@router.patch("/cases/{case_id}")
def patch_case(case_id: int, payload: CasePatch, lang=Depends(get_language)):
    case = require_case(case_id, lang, db)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return {"case": case, "duplicate_case_number": False}
    if "case_type" in updates and updates["case_type"] not in CASE_TYPES:
        fail(422, "invalid_case_type", "نوع القضية غير صالح." if lang == "ar" else "Invalid case type.")
    if "location" in updates and "latitude" not in updates and "longitude" not in updates:
        updates["latitude"] = None
        updates["longitude"] = None
    db.update_case(case_id, **updates)
    if "location" in payload.model_fields_set and not (
        {"latitude", "longitude"} & payload.model_fields_set
    ):
        analysis.locate(case_id, lang)
    updated = db.get_case(case_id)
    updated.pop("worker", None)
    return {
        "case": updated,
        "duplicate_case_number": db.case_number_exists(updated.get("case_number"), exclude_id=case_id),
    }


@router.post("/cases/{case_id}/suggest")
def suggest_case_details(case_id: int, lang=Depends(get_language)):
    case = require_case(case_id, lang, db)
    return analysis.suggest_details(case.get("case_text") or "", lang)


@router.post("/cases/{case_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_case(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    analysis.start_analysis(case_id, lang)
    return {"status": "analyzing"}


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    attachments.remove_for_case(case_id)
    db.delete_case(case_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/cases/{case_id}/versions/{version_id}")
def get_version(case_id: int, version_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    version = next((item for item in db.list_report_versions(case_id) if item["id"] == version_id), None)
    if not version:
        not_found(lang, "version")
    version["report"] = analysis.parse_report(version["report_text"])
    return version


@router.get("/cases/{case_id}/report.txt")
def download_report(case_id: int, version: int | None = None, lang=Depends(get_language)):
    case = require_case(case_id, lang, db)
    report_text = case.get("report_text") or ""
    if version is not None:
        selected = next((item for item in db.list_report_versions(case_id) if item["id"] == version), None)
        if not selected:
            not_found(lang, "version")
        report_text = selected["report_text"]
    return StarletteResponse(
        analysis.report_as_text(report_text),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="case-{case_id}-report.txt"'},
    )
