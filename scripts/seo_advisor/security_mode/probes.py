"""暴露檔案與目錄列表偵測：對固定內建的常見敏感路徑各發送一次 GET，
只看狀態碼/內容類型/長度判斷是否公開可存取，不下載完整內容、不利用內容。

刻意使用內建 allowlist、不接受使用者自訂路徑清單：這是為了讓 Security Mode
維持在「檢查自己網站常見誤設定」的範圍內，不變成可以被拿去對任意網站做
大規模路徑爆破的通用掃描工具。

僅憑 200 狀態碼判斷「檔案存在」誤報率偏高：許多網站（尤其 SPA）對任何
路徑都回 200 並附上自訂錯誤頁或首頁內容。因此對每個敏感路徑額外提供
signature_check（見 HTTPConnector.probe_path），在 connector 內部比對內容
是否真的符合該路徑該有的特徵，內容本身不會外流，只有布林結果會被使用。
"""

from __future__ import annotations

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import ProbeResult
from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact


def _looks_like_env_file(body: bytes) -> bool:
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return False
    key_value_lines = sum(1 for line in lines[:20] if "=" in line and " " not in line.split("=", 1)[0])
    return key_value_lines >= max(1, len(lines[:20]) // 2)


def _looks_like_git_head(body: bytes) -> bool:
    text = body.decode("utf-8", errors="replace").strip()
    return text.startswith("ref:") or len(text) == 40 and all(c in "0123456789abcdef" for c in text.lower())


def _looks_like_git_config(body: bytes) -> bool:
    text = body.decode("utf-8", errors="replace")
    return "[core]" in text or "[remote" in text


def _looks_like_sql_dump(body: bytes) -> bool:
    text = body.decode("utf-8", errors="replace").lower()
    return any(kw in text[:2000] for kw in ("insert into", "create table", "-- mysql dump", "drop table"))


def _looks_like_htpasswd(body: bytes) -> bool:
    text = body.decode("utf-8", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    return bool(lines) and all(":" in line for line in lines[:5])


def _looks_like_zip(body: bytes) -> bool:
    return body[:2] == b"PK"  # ZIP 檔案 magic number


# 路徑、是否視為含憑證等高敏感內容（redact_preview）、簽章判斷函式（None 代表
# 無法可靠判斷內容特徵，僅能依 200 狀態碼推測，confidence 需相應降低）、說明。
_EXPOSED_FILE_PROBES: tuple[tuple[str, bool, object, str], ...] = (
    (".env", True, _looks_like_env_file, "環境變數檔，通常含資料庫密碼/API 金鑰等憑證"),
    (".env.local", True, _looks_like_env_file, "本地環境變數檔，通常含資料庫密碼/API 金鑰等憑證"),
    (".env.production", True, _looks_like_env_file, "正式環境變數檔，通常含資料庫密碼/API 金鑰等憑證"),
    (".git/HEAD", True, _looks_like_git_head, "Git 版本控制目錄外洩，可能可還原完整原始碼與歷史"),
    (".git/config", True, _looks_like_git_config, "Git 設定檔，可能含遠端倉庫憑證資訊"),
    (".svn/entries", True, None, "SVN 版本控制目錄外洩，可能可還原原始碼歷史"),
    ("wp-config.php.bak", True, None, "WordPress 設定檔備份，含資料庫密碼"),
    ("wp-config.php~", True, None, "WordPress 設定檔編輯器殘留備份"),
    ("backup.zip", True, _looks_like_zip, "常見的整站備份檔命名"),
    ("backup.tar.gz", True, None, "常見的整站備份檔命名"),
    ("backup.sql", True, _looks_like_sql_dump, "常見的資料庫備份檔命名"),
    ("db.sql", True, _looks_like_sql_dump, "常見的資料庫匯出檔命名"),
    ("dump.sql", True, _looks_like_sql_dump, "常見的資料庫匯出檔命名"),
    (".DS_Store", False, None, "macOS 目錄中繼資料，可能洩漏檔案結構"),
    ("debug.log", False, None, "除錯日誌，可能含路徑/查詢等內部資訊"),
    ("error.log", False, None, "錯誤日誌，可能含路徑/查詢等內部資訊"),
    ("storage/logs/laravel.log", False, None, "Laravel 框架日誌，可能含路徑/查詢等內部資訊"),
    ("phpinfo.php", True, None, "PHP 環境資訊頁，會洩漏伺服器版本/路徑/已安裝模組等詳細資訊"),
    (".htpasswd", True, _looks_like_htpasswd, "Apache Basic Auth 密碼檔"),
)

_DIRECTORY_LISTING_PROBES: tuple[str, ...] = (
    "uploads/",
    "backup/",
    "backups/",
    "assets/",
    "files/",
    "wp-content/uploads/",
)

_DIRECTORY_INDEX_MARKERS = ("index of /", "<title>index of", "parent directory")


def check_exposed_files(connector: HTTPConnector, next_id) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for path, is_sensitive, signature_check, description in _EXPOSED_FILE_PROBES:
        result = connector.probe_path(path, redact_preview=is_sensitive, signature_check=signature_check)
        if result.status_code != 200:
            # 403/404/其他一律視為「未公開可讀」，不構成發現——403 代表被
            # 伺服器擋下，不能斷言檔案存在或內容外洩。
            continue

        if result.content_matches_signature is False:
            # 有簽章判斷、但內容不符合該路徑該有的特徵——極可能是 SPA/WAF
            # 對任何路徑都回 200 的自訂錯誤頁，不是真的洩漏，不產生發現。
            continue

        # content_matches_signature 為 True（有驗證且符合）給高信心；
        # None（該路徑沒有簽章判斷函式，只能看狀態碼）給中等信心。
        confidence = 0.85 if result.content_matches_signature else 0.5

        findings.append(
            SecurityFinding(
                id=next_id("exposed_file"),
                title=f"可公開存取的敏感路徑：/{path}",
                category="exposed_file",
                severity=SecuritySeverity.S0_CRITICAL if is_sensitive else SecuritySeverity.S2_MEDIUM,
                seo_impact=SeoImpact.TRUST,
                confidence=confidence,
                affected_urls=[f"/{path}"],
                evidence=_probe_evidence(result),
                recommendation=(
                    f"{description}。請立即從公開網站移除或封鎖此路徑的存取"
                    + ("，並更換其中可能外洩的所有憑證/金鑰。" if is_sensitive else "。")
                ),
                needs_credential_rotation=is_sensitive,
            )
        )
    return findings


def check_directory_listing(connector: HTTPConnector, next_id) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    for path in _DIRECTORY_LISTING_PROBES:
        result = connector.probe_path(path)
        if result.status_code != 200:
            continue
        preview_lower = result.body_preview.lower()
        if not any(marker in preview_lower for marker in _DIRECTORY_INDEX_MARKERS):
            continue
        findings.append(
            SecurityFinding(
                id=next_id("directory_listing"),
                title=f"目錄列表對外開放：/{path}",
                category="directory_listing",
                severity=SecuritySeverity.S1_HIGH,
                seo_impact=SeoImpact.TRUST,
                confidence=0.6,
                affected_urls=[f"/{path}"],
                evidence=_probe_evidence(result),
                recommendation="請在伺服器設定中關閉此目錄的自動列表功能（例如 Apache 的 Options -Indexes）。",
            )
        )
    return findings


def _probe_evidence(result: ProbeResult) -> dict:
    return {
        "status_code": result.status_code,
        "content_type": result.content_type,
        "content_length": result.content_length,
        "truncated": result.truncated,
        "content_matches_signature": result.content_matches_signature,
    }
