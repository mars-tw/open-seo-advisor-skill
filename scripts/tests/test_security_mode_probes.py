"""Security Mode 暴露檔案/目錄列表偵測測試：確認 200 才算發現、403/404 不算，
且敏感路徑不會把內容存進 evidence。"""

from collections import Counter

import httpx
import respx

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import SafetyPolicy
from seo_advisor.security_mode.probes import check_directory_listing, check_exposed_files

# 測試對象是 respx mock，不是真實網站，不需要節流；用高速率 policy 避免測試
# 因為既有的 3 req/s 預設 rate limit 而跑得不必要地久。
_FAST_POLICY = SafetyPolicy(rate_limit_per_second=1000.0)


def _next_id_factory():
    counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        counter[category] += 1
        return f"SEC-{category.upper()}-{counter[category]:03d}"

    return next_id


@respx.mock
def test_exposed_env_file_returns_critical_finding_without_leaking_content():
    respx.get("https://example.com/.env").mock(
        return_value=httpx.Response(200, text="DB_PASSWORD=supersecret123", headers={"content-type": "text/plain"})
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_exposed_files(connector, _next_id_factory())

    env_findings = [f for f in findings if ".env" in f.title]
    assert len(env_findings) == 1
    finding = env_findings[0]
    assert finding.severity.value == "S0"
    assert finding.needs_credential_rotation is True
    # 關鍵：不能把 "supersecret123" 這種憑證內容洩漏進報告本身。
    assert "supersecret123" not in str(finding.evidence)
    assert "supersecret123" not in finding.recommendation


@respx.mock
def test_spa_fallback_200_for_env_path_is_not_flagged():
    """SPA/WAF 常對任何路徑都回 200 並附上自訂錯誤頁或首頁內容，這不代表
    .env 真的洩漏了——必須用內容簽章判斷排除，不能只憑 200 狀態碼斷言。"""
    respx.get("https://example.com/.env").mock(
        return_value=httpx.Response(200, text="<html><body>404 - Page Not Found</body></html>")
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_exposed_files(connector, _next_id_factory())
    assert findings == []


@respx.mock
def test_git_head_with_real_ref_content_flagged_high_confidence():
    respx.get("https://example.com/.git/HEAD").mock(
        return_value=httpx.Response(200, text="ref: refs/heads/main\n")
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_exposed_files(connector, _next_id_factory())
    git_findings = [f for f in findings if ".git/HEAD" in f.title]
    assert len(git_findings) == 1
    assert git_findings[0].confidence == 0.85


@respx.mock
def test_403_response_does_not_produce_finding():
    """403 代表被伺服器擋下，不能斷言檔案存在或內容外洩。"""
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(403))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_exposed_files(connector, _next_id_factory())
    assert findings == []


@respx.mock
def test_directory_listing_detected_only_with_index_marker():
    respx.get("https://example.com/uploads/").mock(
        return_value=httpx.Response(200, text="<html><title>Index of /uploads</title></html>")
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_directory_listing(connector, _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S1"


@respx.mock
def test_normal_200_page_without_index_marker_is_not_flagged():
    """200 但內容是正常頁面（非目錄列表特徵）不該被誤判。"""
    respx.get("https://example.com/uploads/").mock(
        return_value=httpx.Response(200, text="<html><body>Our uploads page</body></html>")
    )
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com", policy=_FAST_POLICY)
    findings = check_directory_listing(connector, _next_id_factory())
    assert findings == []
