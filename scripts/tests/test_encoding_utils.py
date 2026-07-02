from seo_advisor.encoding_utils import decode_html_bytes, detect_html_encoding


def test_detects_utf8_bom():
    raw = "<html><title>你好</title></html>".encode("utf-8-sig")
    assert detect_html_encoding(raw) == "utf-8-sig"


def test_detects_meta_charset_declaration():
    html = '<html><head><meta charset="big5"></head><body>test</body></html>'
    raw = html.encode("big5")
    assert detect_html_encoding(raw) == "big5"


def test_detects_meta_http_equiv_charset():
    html = (
        '<html><head><meta http-equiv="Content-Type" '
        'content="text/html; charset=gb2312"></head></html>'
    )
    raw = html.encode("gb2312")
    assert detect_html_encoding(raw) == "gb2312"


def test_defaults_to_utf8_when_no_declaration():
    raw = "<html><body>plain</body></html>".encode("ascii")
    assert detect_html_encoding(raw) == "utf-8"


def test_decode_big5_content_correctly():
    original_text = "繁體中文網站範例"
    html = f'<html><head><meta charset="big5"></head><body>{original_text}</body></html>'
    raw = html.encode("big5")

    decoded = decode_html_bytes(raw)
    assert original_text in decoded


def test_decode_shift_jis_content_correctly():
    original_text = "日本語のサイト"
    html = f'<html><head><meta charset="shift_jis"></head><body>{original_text}</body></html>'
    raw = html.encode("shift_jis")

    decoded = decode_html_bytes(raw)
    assert original_text in decoded


def test_decode_falls_back_to_utf8_on_invalid_encoding_name():
    html = '<html><head><meta charset="not-a-real-encoding"></head><body>hi</body></html>'
    raw = html.encode("utf-8")

    decoded = decode_html_bytes(raw)
    assert "hi" in decoded


def test_decode_utf8_content_unaffected():
    original_text = "正常的繁體中文內容"
    html = f"<html><body>{original_text}</body></html>"
    raw = html.encode("utf-8")

    decoded = decode_html_bytes(raw)
    assert original_text in decoded
