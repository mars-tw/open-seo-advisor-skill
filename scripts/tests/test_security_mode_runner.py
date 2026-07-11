"""Security Mode runner 測試：授權確認閘門是這個模組最重要的安全機制，
沒有正確的確認字串就不能執行暴露檔案/目錄列表探測。"""

import httpx
import pytest
import respx

from seo_advisor.security_mode.runner import (
    AuthorizationRequiredError,
    build_confirmation_phrase,
    run_security_audit,
    verify_confirmation,
)


def test_build_confirmation_phrase_uses_hostname():
    assert build_confirmation_phrase("https://example.com/page") == "AUDIT example.com"


def test_verify_confirmation_is_case_insensitive_but_exact_host():
    assert verify_confirmation("audit example.com", "https://example.com") is True
    assert verify_confirmation("AUDIT example.com", "https://example.com") is True
    assert verify_confirmation("AUDIT other.com", "https://example.com") is False


def test_confirmation_treats_www_and_apex_as_same_target():
    """www/apex 是同一個網站的正規化寫法，AUDIT example.com 應該同樣涵蓋
    www.example.com，避免使用者誤以為兩者是不同的授權範圍。"""
    assert build_confirmation_phrase("https://www.example.com") == "AUDIT example.com"
    assert verify_confirmation("AUDIT example.com", "https://www.example.com") is True


def test_confirmation_phrase_includes_non_default_port():
    """非預設 port 視為可能是不同服務，確認字串需明確標示，避免
    example.com:8443 被誤判為與 example.com 同一個授權範圍。"""
    assert build_confirmation_phrase("https://example.com:8443") == "AUDIT example.com:8443"
    assert verify_confirmation("AUDIT example.com", "https://example.com:8443") is False


def test_confirmation_phrase_never_includes_userinfo():
    """即使 URL 意外帶有 username:password@host，確認字串也絕不能包含這段
    憑證資訊（雖然 CLI 層的 normalize_url 已經會拒絕這類 URL，這裡是底層
    函式本身的縱深防禦，避免繞過 CLI 直接呼叫 runner 時洩漏）。"""
    phrase = build_confirmation_phrase("https://admin:s3cr3t@example.com")
    assert "admin" not in phrase
    assert "s3cr3t" not in phrase
    assert phrase == "AUDIT example.com"
    assert verify_confirmation(None, "https://example.com") is False


@respx.mock
def test_run_security_audit_without_confirmation_raises():
    """沒提供確認字串、也沒用 passive_only 時，必須拒絕執行探測性檢查。"""
    with pytest.raises(AuthorizationRequiredError):
        run_security_audit("https://example.com")


@respx.mock
def test_run_security_audit_with_wrong_confirmation_raises():
    with pytest.raises(AuthorizationRequiredError):
        run_security_audit("https://example.com", confirm_authorized="AUDIT wrong-host.com")


@respx.mock
def test_run_security_audit_passive_only_skips_probes_without_confirmation():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Hi</body></html>", headers={"content-type": "text/html"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    report = run_security_audit("https://example.com", passive_only=True, skip_bot_compare=True)
    assert report.passive_only is True
    assert "exposed_file" in report.skipped_checks
    assert "directory_listing" in report.skipped_checks


def test_run_security_audit_rejects_url_with_userinfo():
    """即使繞過 CLI 層的 normalize_url 檢查直接呼叫本函式，含帳密的 URL
    也必須被拒絕，不能讓憑證意外流入報告的任何欄位。"""
    with pytest.raises(ValueError, match="帳號密碼"):
        run_security_audit("https://admin:secretpass@example.com", passive_only=True)


@respx.mock
def test_passive_only_also_skips_cloaking_even_without_explicit_skip_bot_compare():
    """cloaking UA 比較本質上也是額外的探測性請求，passive_only 時該自動
    跳過，不需要使用者額外傳 skip_bot_compare=True 才會跳過。"""
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Hi</body></html>", headers={"content-type": "text/html"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    report = run_security_audit("https://example.com", passive_only=True)
    assert "cloaking" in report.skipped_checks


@respx.mock
def test_run_security_audit_with_correct_confirmation_runs_probes():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Hi</body></html>", headers={"content-type": "text/html"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    report = run_security_audit(
        "https://example.com", confirm_authorized="AUDIT example.com", skip_bot_compare=True
    )
    assert "exposed_file" not in report.skipped_checks
    assert "directory_listing" not in report.skipped_checks


@respx.mock
def test_passive_only_also_skips_referrer_redirect_check():
    """惡意重導的 Referer 比較跟 cloaking 一樣是探測性請求，passive_only
    時應自動跳過。"""
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Hi</body></html>", headers={"content-type": "text/html"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    report = run_security_audit("https://example.com", passive_only=True)
    assert "referrer_redirect" in report.skipped_checks


@respx.mock
def test_skip_bot_compare_does_not_skip_referrer_redirect_check():
    """skip_bot_compare 只控制 cloaking UA 比較（既有 --no-bot-compare
    參數的既有語意），惡意重導的 Referer 比較是獨立的檢查項目，不受這個
    旗標影響——只受 passive_only 控制。"""
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Hi</body></html>", headers={"content-type": "text/html"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    report = run_security_audit(
        "https://example.com", confirm_authorized="AUDIT example.com", skip_bot_compare=True
    )
    assert "cloaking" in report.skipped_checks
    assert "referrer_redirect" not in report.skipped_checks
