"""Decode bounded text without handing non-HTML assets to HTML analyzers."""

import mimetypes
from pathlib import PurePosixPath

from seo_advisor.encoding_utils import detect_html_encoding

HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
TEXT_MEDIA_TYPES = frozenset({"application/xml", "application/json", "application/javascript"})


def file_snapshot_fields(path: str, body: bytes) -> dict:
    """Classify a static file when the connector has no HTTP response headers."""
    suffix = PurePosixPath(path).suffix.lower()
    media_type = {
        ".html": "text/html",
        ".htm": "text/html",
        ".xhtml": "application/xhtml+xml",
        ".xml": "application/xml",
        ".txt": "text/plain",
        ".json": "application/json",
        ".css": "text/css",
    }.get(suffix)
    if not media_type:
        media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if not suffix:
            try:
                prefix = body[:512].decode(detect_html_encoding(body), errors="ignore")
            except LookupError:
                prefix = body[:512].decode("ascii", errors="ignore")
            if prefix.lstrip("\ufeff").lstrip().casefold().startswith(("<!doctype html", "<html")):
                media_type = "text/html"
    encoding = detect_html_encoding(body)
    fields = snapshot_body_fields(body, media_type, encoding)
    return {
        **fields,
        "headers": {"content-type": media_type},
        "encoding": encoding if fields["text"] is not None else None,
    }


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
