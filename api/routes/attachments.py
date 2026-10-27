from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

import analysis
import attachments
import db
import extract
import vision
from api.deps import get_language
from api.routes.common import fail, not_found, require_case
from api.uploads import adapt_upload
from config import MAX_ATTACHMENT_MB
from i18n import t

router = APIRouter()


@router.get("/cases/{case_id}/attachments")
def list_case_attachments(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    rows = db.list_case_files(case_id)
    for row in rows:
        row["read_status"] = (
            "read" if row.get("description") or row.get("transcript")
            else "will_read" if row.get("kind") in ("text", "pdf", "file", "image", "video", "audio")
            else "unread"
        )
    return rows


@router.post("/cases/{case_id}/attachments")
async def upload_case_attachments(case_id: int, files: list[UploadFile] = File(...),
                                  reanalyze: bool = True,
                                  lang=Depends(get_language)):
    case = require_case(case_id, lang, db)
    uploaded, errors = [], []
    for file in files:
        adapter = await adapt_upload(file)
        ok, result = attachments.save(case_id, adapter)
        if ok:
            uploaded.append(result)
        else:
            reason = (t(lang, result, mb=MAX_ATTACHMENT_MB)
                      if result in ("att_empty", "att_too_big") else result)
            errors.append({"name": adapter.name, "error": reason})
    if uploaded and reanalyze and case["status"] in {"analyzed", "analyzing", "failed"}:
        analysis.start_analysis(case_id, lang)
    return {"uploaded": len(uploaded), "errors": errors, "attachments": db.list_case_files(case_id)}


@router.post("/cases/{case_id}/attachments/read-preview")
def read_preview(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    rows = db.list_case_files(case_id)
    cache = {row["id"]: row.get("description") for row in rows if row.get("description")}
    text, images = extract.describe(lang, rows, cache=cache)
    errors = []
    if images:
        described, errors = vision.describe_many(lang, images, cache=cache)
        text = "\n\n".join(part for part in (text, described) if part)
    return {"text": text, "errors": errors}


@router.get("/attachments/{attachment_id}/file")
def get_attachment_file(attachment_id: int, lang=Depends(get_language)):
    attachment = db.get_attachment(attachment_id)
    if not attachment:
        not_found(lang, "attachment")
    path = attachments.path_of(attachment)
    if not path:
        fail(404, "file_not_found", "الملف غير موجود." if lang == "ar" else "File not found.")
    return FileResponse(path, media_type=attachment.get("mime_type") or "application/octet-stream",
                        filename=attachment.get("file_name") or path.name)


@router.delete("/attachments/{attachment_id}", status_code=204)
def delete_attachment(attachment_id: int, lang=Depends(get_language)):
    attachment = db.get_attachment(attachment_id)
    if not attachment:
        not_found(lang, "attachment")
    attachments.remove(attachment)
