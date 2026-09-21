"""Decode bounded HTTP text without handing non-HTML assets to HTML analyzers."""

HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
TEXT_MEDIA_TYPES = frozenset({"application/xml", "application/json", "application/javascript"})


def snapshot_body_fields(body: bytes, content_type: str, encoding: str) -> dict:
    """Caller enforces its response-size limit before passing bytes here.

    None means an unsupported/missing content type, whereas an empty string is a
    captured empty textual response. Never store response content inside headers.
    """
    media_type = content_type.split(";", 1)[0].strip().lower()
    is_html = media_type in HTML_MEDIA_TYPES
    is_text = (
        is_html
        or media_type.startswith("text/")
        or media_type in TEXT_MEDIA_TYPES
        or ("/" in media_type and media_type.endswith(("+xml", "+json")))
    )
    if not is_text:
        return {"html": "", "text": None}
    try:
        text = body.decode(encoding, errors="replace")
    except (LookupError, ValueError):
        text = body.decode("utf-8", errors="replace")
    return {"html": text if is_html else "", "text": text}
