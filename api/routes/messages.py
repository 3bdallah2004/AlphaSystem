from fastapi import APIRouter, Depends, File, Form, UploadFile, status

import chat
import db
from api.deps import get_language
from api.routes.common import fail, not_found, require_case
from api.uploads import adapt_upload

router = APIRouter()


@router.get("/cases/{case_id}/messages")
def list_messages(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    messages = db.list_messages(case_id)
    for message in messages:
        message["attachments"] = db.list_message_attachments(message["id"])
    return messages


@router.post("/cases/{case_id}/messages", status_code=status.HTTP_202_ACCEPTED)
async def send_message(case_id: int, text: str = Form(""), files: list[UploadFile] = File(default=[]),
                       lang=Depends(get_language)):
    require_case(case_id, lang, db)
    if not text.strip() and not files:
        fail(422, "empty_message", "اكتب رسالة أو أرفق ملفاً." if lang == "ar"
             else "Enter a message or attach a file.")
    uploaded = [await adapt_upload(file) for file in files]
    user_id, reply_id, saved, errors = chat.ask(case_id, text, lang, uploaded)
    return {"message_id": user_id, "reply_id": reply_id, "files_saved": saved, "file_errors": errors}


@router.post("/messages/{message_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_message(message_id: int, lang=Depends(get_language)):
    message = db.get_message(message_id)
    if not message:
        not_found(lang, "message")
    if message.get("role") != "assistant":
        fail(422, "not_a_reply", "لا يمكن إعادة محاولة هذه الرسالة." if lang == "ar"
             else "This message cannot be retried.")
    if message.get("status") != "failed":
        fail(409, "reply_not_failed", "هذه الرسالة ليست فاشلة." if lang == "ar"
             else "This reply has not failed.")
    chat.retry(message["case_id"], message_id, lang)
    return {"status": "pending"}


@router.post("/messages/{message_id}/update-report")
def update_report(message_id: int, lang=Depends(get_language)):
    message = db.get_message(message_id)
    if not message:
        not_found(lang, "message")
    if message.get("role") != "assistant" or message.get("status") != "ok":
        fail(422, "reply_not_complete", "يجب أن تكون الرسالة رداً مكتملاً." if lang == "ar"
             else "The message must be a completed reply.")
    chat.update_report(message["case_id"], message_id, lang)
    return {"status": "updated", "case_id": message["case_id"]}


@router.delete("/cases/{case_id}/messages", status_code=204)
def clear_messages(case_id: int, lang=Depends(get_language)):
    require_case(case_id, lang, db)
    chat.clear(case_id)
