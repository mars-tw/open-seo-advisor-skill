"""https_check.check_certificate 的憑證邏輯測試：mock 掉 ssl/socket 層，
只測純邏輯（過期判斷、即將到期判斷、TLS 版本判斷），不依賴真實網路連線
（避免 CI 因外部網站/網路狀況不穩定而變成 flaky test）。"""

import ssl
from collections import Counter
from unittest.mock import MagicMock, patch

from seo_advisor.security_mode import https_check


def _next_id_factory():
    counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        counter[category] += 1
        return f"SEC-{category.upper()}-{counter[category]:03d}"

    return next_id


def _mock_ssl_socket(cert: dict, tls_version: str = "TLSv1.3"):
    mock_ssock = MagicMock()
    mock_ssock.getpeercert.return_value = cert
    mock_ssock.version.return_value = tls_version
    mock_ssock.__enter__ = MagicMock(return_value=mock_ssock)
    mock_ssock.__exit__ = MagicMock(return_value=False)
    return mock_ssock


def test_non_https_url_flagged_immediately_without_network_call():
    findings = https_check.check_certificate("http://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].category == "https"
    assert findings[0].severity.value == "S1"


@patch("socket.create_connection")
def test_expired_certificate_flagged_as_critical(mock_connect):
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_sock

    with patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_wrap.return_value = _mock_ssl_socket({"notAfter": "Jan  1 00:00:00 2020 GMT"})
        findings = https_check.check_certificate("https://example.com", _next_id_factory())

    expired = [f for f in findings if f.category == "https" and "過期" in f.title]
    assert len(expired) == 1
    assert expired[0].severity.value == "S0"


@patch("socket.create_connection")
def test_certificate_expiring_soon_flagged_as_high(mock_connect):
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_sock

    from datetime import datetime, timedelta, timezone

    soon = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%b %d %H:%M:%S %Y GMT")

    with patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_wrap.return_value = _mock_ssl_socket({"notAfter": soon})
        findings = https_check.check_certificate("https://example.com", _next_id_factory())

    expiring = [f for f in findings if "到期" in f.title]
    assert len(expiring) == 1
    assert expiring[0].severity.value == "S1"


@patch("socket.create_connection")
def test_outdated_tls_version_flagged(mock_connect):
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_sock

    from datetime import datetime, timedelta, timezone

    far_future = (datetime.now(timezone.utc) + timedelta(days=300)).strftime("%b %d %H:%M:%S %Y GMT")

    with patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_wrap.return_value = _mock_ssl_socket({"notAfter": far_future}, tls_version="TLSv1.1")
        findings = https_check.check_certificate("https://example.com", _next_id_factory())

    outdated = [f for f in findings if "TLS" in f.title and "過時" in f.title]
    assert len(outdated) == 1
    assert outdated[0].severity.value == "S2"


@patch("socket.create_connection")
def test_healthy_certificate_produces_no_findings(mock_connect):
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_sock

    from datetime import datetime, timedelta, timezone

    far_future = (datetime.now(timezone.utc) + timedelta(days=300)).strftime("%b %d %H:%M:%S %Y GMT")

    with patch("ssl.SSLContext.wrap_socket") as mock_wrap:
        mock_wrap.return_value = _mock_ssl_socket({"notAfter": far_future}, tls_version="TLSv1.3")
        findings = https_check.check_certificate("https://example.com", _next_id_factory())

    assert findings == []


@patch("socket.create_connection")
def test_certificate_verification_failure_flagged_critical(mock_connect):
    mock_sock = MagicMock()
    mock_sock.__enter__ = MagicMock(return_value=mock_sock)
    mock_sock.__exit__ = MagicMock(return_value=False)
    mock_connect.return_value = mock_sock

    with patch("ssl.SSLContext.wrap_socket", side_effect=ssl.SSLCertVerificationError("cert verify failed")):
        findings = https_check.check_certificate("https://example.com", _next_id_factory())

    assert len(findings) == 1
    assert findings[0].severity.value == "S0"
    assert findings[0].category == "https"
