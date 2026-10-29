from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

import chat
import chat_actions
import db
from api.deps import get_language
from api.routes.common import fail, not_found, require_case
from api.uploads import adapt_upload

router = APIRouter()


@router.get("/chat/messages")
def list_messages(lang=Depends(get_language)):
    return chat.messages()


@router.post("/chat/messages", status_code=status.HTTP_202_ACCEPTED)
async def send_message(text: str = Form(""), case_id: Optional[int] = Form(None),
                       request_id: Optional[str] = Form(None, max_length=128),
                       files: list[UploadFile] = File(default=[]), lang=Depends(get_language)):
    if not text.strip() and not files:
        fail(422, "empty_message", "اكتب رسالة أو أرفق ملفاً." if lang == "ar"
             else "Enter a message or attach a file.")
    if case_id is not None:
        require_case(case_id, lang, db)
    uploaded = [await adapt_upload(file) for file in files]
    try:
        user_id, reply_id, saved, errors = chat.ask(text, lang, uploaded, focus_case_id=case_id, request_id=request_id)
    except ValueError:
        fail(409, "duplicate_request", "معرّف الطلب مستخدم لرسالة أخرى." if lang == "ar" else "Request ID already used for another message.")
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
    chat.retry(message_id, lang)
    return {"status": "pending"}


def _pending_action(message_id, lang):
    message = db.get_message(message_id)
    if not message:
        not_found(lang, "message")
    action = chat_actions.load(message)
    if not action:
        fail(404, "action_not_found", "لا يوجد تغيير مقترح في هذه الرسالة." if lang == "ar"
             else "This message proposes no change.")
    return action


def _not_pending(lang):
    fail(409, "action_not_pending", "تم التعامل مع هذا التغيير من قبل." if lang == "ar"
         else "This change has already been handled.")


@router.post("/messages/{message_id}/action/confirm")
def confirm_action(message_id: int, lang=Depends(get_language)):
    _pending_action(message_id, lang)
    action = chat_actions.confirm(message_id, lang)
    if action is None:
        _not_pending(lang)
    return action


@router.post("/messages/{message_id}/action/cancel")
def cancel_action(message_id: int, lang=Depends(get_language)):
    _pending_action(message_id, lang)
    if not chat_actions.cancel(message_id):
        _not_pending(lang)
    return chat_actions.load(db.get_message(message_id))


@router.delete("/chat/messages", status_code=204)
def clear_messages(lang=Depends(get_language)):
    chat.clear()
