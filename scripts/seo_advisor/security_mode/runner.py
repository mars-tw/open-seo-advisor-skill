"""Security Mode 執行入口：run_security_audit()。

授權邊界（務必先讀）：暴露檔案偵測、目錄列表偵測、cloaking UA 比較本質上
都是對目標網站發送額外的探測性請求，即使只確認狀態碼、不下載內容，仍是
一種偵查行為。因此：
- 預設（passive_only=False）必須提供 confirm_authorized，且其內容必須
  精確等於 "AUDIT <host>"（host 為目標網址的網域），才會執行這三類檢查。
- passive_only=True 可以跳過確認，但只會執行完全不發送額外請求的被動檢查
  （HTTPS 憑證/HSTS/mixed content/SEO spam/CMS 版本提示——這些只需要首頁
  抓取階段已經取得的內容，不對其他路徑或用不同 UA 發送任何請求）。
這個確認機制是本模組的核心信任邊界，任何修改都需要同樣審慎地重新檢視。

Rate limit：整個 audit 過程中可能建立多個 HTTPConnector（主要抓取、
cloaking 比較用的第二個 UA），全部共用同一個 RateLimiter 實例，確保「對
目標網站的總請求速率」不會因為多開 connector 而被稀釋（見
connectors/http.py 的 rate_limiter 參數與 cloaking.check_cloaking）。
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security_mode import cloaking, cms, https_check, probes, spam
from seo_advisor.security_mode.models import SecurityFinding, SecurityReport
from seo_advisor.url_utils import normalize_host


class AuthorizationRequiredError(ValueError):
    """執行探測性檢查（暴露檔案/目錄列表）前，未取得正確的授權確認字串。"""


def _confirmation_target(url: str) -> str:
    """把 URL 正規化成確認字串比對用的目標：lowercase host（www/apex 視為
    同一個確認範圍，避免使用者誤以為 AUDIT example.com 跟 AUDIT
    www.example.com 是不同授權）；normalize_host 本身會保留非預設 port
    （避免 example.com:8443 與 example.com 被誤判為同一個確認範圍——不同
    port 可能是完全不同的服務），只去掉 80/443 這類預設 port。不使用 URL
    裡的 username/password（那部分屬於憑證，不該出現在確認字串或任何
    提示訊息裡）。
    """
    parsed = urlparse(url)
    return normalize_host(parsed.netloc.split("@")[-1])  # 去掉可能殘留的 userinfo


def build_confirmation_phrase(url: str) -> str:
    return f"AUDIT {_confirmation_target(url)}"


def verify_confirmation(user_input: str | None, url: str) -> bool:
    if not user_input:
        return False
    return user_input.strip().upper() == build_confirmation_phrase(url).strip().upper()


def run_security_audit(
    url: str,
    *,
    passive_only: bool = False,
    confirm_authorized: str | None = None,
    skip_bot_compare: bool = False,
    report_id: str = "security-audit",
    generated_at: str = "",
) -> SecurityReport:
    # 一律拒絕含 username:password@ 的 URL：HTTPConnector 本身不支援任何
    # 認證機制，這種 URL 唯一可能的來源是使用者複製貼上時不慎帶入的憑證，
    # 直接拒絕比「遮蔽後繼續嘗試連線」更安全誠實（CLI 層的 normalize_url
    # 已經會擋下，這裡是繞過 CLI 直接呼叫本函式時的縱深防禦）。
    if "@" in urlparse(url).netloc:
        raise ValueError(
            "網址中不應包含帳號密碼（例如 https://user:pass@example.com），"
            "這類憑證可能被意外記錄到報告中造成外洩，請直接輸入網址本身。"
        )

    if not passive_only and not verify_confirmation(confirm_authorized, url):
        raise AuthorizationRequiredError(
            f"執行暴露檔案/目錄列表檢查前，需要明確確認你有權對此網站進行安全掃描。"
            f'請提供 confirm_authorized="{build_confirmation_phrase(url)}"，'
            "或加上 passive_only=True 只執行完全被動的檢查（不探測任何路徑）。"
        )

    seq_counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        seq_counter[category] += 1
        return f"SEC-{category.upper()}-{seq_counter[category]:03d}"

    findings: list[SecurityFinding] = []
    skipped_checks: list[str] = []
    coverage_notes: list[str] = []

    shared_rate_limiter = RateLimiter(SafetyPolicy().rate_limit_per_second)
    connector = HTTPConnector(
        url,
        policy=SafetyPolicy(allowed_capabilities={"read_urls"}),
        rate_limiter=shared_rate_limiter,
    )
    try:
        snapshot = connector.fetch_url(url, fetched_at=generated_at)
    except Exception as exc:  # noqa: BLE001 - 首頁抓取失敗仍要繼續跑不依賴內容的檢查
        snapshot = None
        coverage_notes.append(f"首頁抓取失敗，部分依賴頁面內容的檢查將被略過：{exc}")

    findings.extend(https_check.check_certificate(url, next_id))

    if snapshot is not None:
        findings.extend(https_check.check_hsts(snapshot.headers, url, next_id))
        findings.extend(https_check.check_mixed_content(snapshot.html, url, next_id))
        findings.extend(spam.check_seo_spam(snapshot.html, url, next_id))
        findings.extend(cms.check_cms_version_exposure(snapshot.html, url, next_id))
    else:
        skipped_checks.extend(["hsts", "mixed_content", "seo_spam", "cms_version"])

    # cloaking 比較會額外發送一次請求（切換 User-Agent），本質上與暴露檔案/
    # 目錄列表一樣是「探測性」行為，因此 passive_only 時也一併跳過，不只
    # 靠 --no-bot-compare 手動關閉。
    if passive_only:
        skipped_checks.append("cloaking")
    elif not skip_bot_compare:
        try:
            findings.extend(cloaking.check_cloaking(url, next_id, rate_limiter=shared_rate_limiter))
        except Exception as exc:  # noqa: BLE001 - cloaking 比較失敗不該讓整份報告失敗
            coverage_notes.append(f"Cloaking 比較檢查失敗，已略過：{exc}")
            skipped_checks.append("cloaking")
    else:
        skipped_checks.append("cloaking")

    if passive_only:
        skipped_checks.extend(["exposed_file", "directory_listing"])
        coverage_notes.append(
            "已啟用 passive_only：只執行完全不發送額外請求的被動檢查"
            "（HTTPS/HSTS/mixed content/SEO spam/CMS 版本提示）；"
            "暴露檔案/目錄列表探測與 cloaking UA 比較需明確授權確認才會執行。"
        )
    else:
        findings.extend(probes.check_exposed_files(connector, next_id))
        findings.extend(probes.check_directory_listing(connector, next_id))

    connector.close()

    return SecurityReport(
        report_id=report_id,
        generated_at=generated_at,
        target_url=url,
        findings=findings,
        passive_only=passive_only,
        skipped_checks=skipped_checks,
        coverage_notes=coverage_notes,
    )
