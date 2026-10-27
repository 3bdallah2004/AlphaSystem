from fastapi import Request


def get_language(request: Request):
    query_lang = request.query_params.get("lang", "").lower()
    if query_lang in ("ar", "en"):
        return query_lang
    accept_language = request.headers.get("accept-language", "").lower()
    return "en" if any(part.strip().split(";", 1)[0].split("-", 1)[0] == "en"
                       for part in accept_language.split(",")) else "ar"
