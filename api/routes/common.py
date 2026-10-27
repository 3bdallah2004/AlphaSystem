from fastapi import HTTPException


def fail(status_code, code, message):
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def localized(lang, arabic, english):
    return english if lang == "en" else arabic


def not_found(lang, item="case"):
    label = {
        "case": ("القضية", "Case"),
        "attachment": ("المرفق", "Attachment"),
        "message": ("الرسالة", "Message"),
        "version": ("نسخة التقرير", "Report version"),
    }[item]
    fail(404, f"{item}_not_found", f"{label[1] if lang == 'en' else label[0]} "
         f"{'not found.' if lang == 'en' else 'غير موجودة.'}")


def require_case(case_id, lang, db):
    case = db.get_case(case_id)
    if not case:
        not_found(lang)
    return case
