"""友善錯誤處理：把預期內的錯誤轉成人話說明，而不是印出 Python traceback。

只有加上 --debug 旗標時，CLI 才會顯示完整技術細節（exception + traceback）。
這個模組不負責「捕捉所有例外」，只負責把已知的、常見的新手會遇到的錯誤，
轉換成清楚、附下一步建議的訊息。未預期的例外仍應該讓 --debug 模式看得到細節，
避免真正的程式錯誤被靜默吞掉。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from seo_advisor.ads.providers.base import AdsProviderError
from seo_advisor.growth.providers.base import AnalyticsProviderError
from seo_advisor.images.providers.base import ImageProviderError
from seo_advisor.scan_runner import SiteUnreachableError
from seo_advisor.security.network_policy import PrivateNetworkBlockedError
from seo_advisor.security.safe_archive import UnsafeArchiveError
from seo_advisor.url_utils import InvalidUrlError
from seo_advisor.writers.providers.base import LLMProviderError

# 遮蔽敏感片段：避免錯誤訊息意外洩漏 token、URL 內帳密、或本機使用者路徑。
_USERINFO_RE = re.compile(r"(https?://)[^/@\s:]+(?::[^/@\s]+)?@")
_TOKEN_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|access[_-]?token|authorization|bearer)"
    r"\s*[=:]\s*[^\s,;'\"]+"
)
_WIN_HOME_RE = re.compile(r"[Cc]:\\Users\\[^\\/\s]+")
_NIX_HOME_RE = re.compile(r"/(?:home|Users)/[^/\s]+")
# OpenAI / Anthropic 風格的金鑰前綴，即使沒有 key= 也能被抓到。
_KEY_PREFIX_RE = re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{6,}|sk-[A-Za-z0-9_-]{6,})")
# SSHConnector 相關：SSH 私鑰的 PEM 區塊、密碼/passphrase 欄位、known_hosts 裡的
# IdentityFile 設定，這些即使不小心被印進例外訊息也絕不能外洩內容本身。
_PRIVATE_KEY_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
)
_PASSWORD_FIELD_RE = re.compile(r"(?i)\b(password|passphrase)\s*[=:]\s*[^\s,;'\"]+")
_SSH_USERINFO_RE = re.compile(r"(ssh://)[^/@\s:]+(?::[^/@\s]+)?@")
# WordPressAPIConnector 相關：HTTP Basic Auth header、WordPress Application
# Password 格式（"xxxx xxxx xxxx xxxx xxxx xxxx"，六組四字元）即使不小心被印進
# 例外訊息或 httpx 的 request repr 裡也不能外洩。
_BASIC_AUTH_HEADER_RE = re.compile(r"(?i)\bAuthorization\s*[=:]\s*Basic\s+[A-Za-z0-9+/=]+")
_WP_APP_PASSWORD_RE = re.compile(r"\b[a-zA-Z0-9]{4}(?: [a-zA-Z0-9]{4}){5}\b")
# CloudflareConnector 相關：Authorization: Bearer <token> 這種「兩層」格式
# 沒有被上面的 _TOKEN_RE 完整涵蓋（那個規則只吃 "Authorization" 後面接的
# 第一個詞，Bearer 後面實際的 token 值會漏網）；環境變數名稱型態的
# "..._API_TOKEN=value"/"..._TOKEN=value" 也因為 _TOKEN_RE 的 \b word
# boundary 在底線前不成立而完全匹配不到（例如 CLOUDFLARE_API_TOKEN，
# TOKEN 前面是底線，\btoken 抓不到）。
_BEARER_TOKEN_RE = re.compile(r"(?i)\bBearer\s+[^\s,;'\"]+")
_ENV_VAR_TOKEN_RE = re.compile(r"(?i)\b[A-Z][A-Z0-9_]*(?:TOKEN|API_KEY|SECRET)\s*=\s*[^\s,;'\"]+")
# CPanelConnector 相關：cPanel UAPI 的 Authorization header 格式是
# "cpanel <username>:<api_token>"，同樣是 _TOKEN_RE 抓不到的兩層格式
# （只吃 Authorization 後面第一個詞，username:token 這段會漏網）。
_CPANEL_AUTH_HEADER_RE = re.compile(r"(?i)\bcpanel\s+[^\s,;'\"]+:[^\s,;'\"]+")


def redact_secrets(text: str) -> str:
    """把可能的敏感片段遮蔽掉，用於任何要顯示給使用者或寫入報告的錯誤訊息。"""
    text = _USERINFO_RE.sub(r"\1[已遮蔽]@", text)
    text = _SSH_USERINFO_RE.sub(r"\1[已遮蔽]@", text)
    text = _PRIVATE_KEY_PEM_RE.sub("[已遮蔽的私鑰內容]", text)
    text = _PASSWORD_FIELD_RE.sub(lambda m: f"{m.group(1)}=[已遮蔽]", text)
    text = _BASIC_AUTH_HEADER_RE.sub("Authorization: Basic [已遮蔽]", text)
    text = _WP_APP_PASSWORD_RE.sub("[已遮蔽的應用程式密碼]", text)
    text = _BEARER_TOKEN_RE.sub("Bearer [已遮蔽]", text)
    text = _CPANEL_AUTH_HEADER_RE.sub("cpanel [已遮蔽]", text)
    text = _ENV_VAR_TOKEN_RE.sub(lambda m: f"{m.group(0).split('=')[0]}=[已遮蔽]", text)
    text = _TOKEN_RE.sub(lambda m: f"{m.group(1)}=[已遮蔽]", text)
    text = _KEY_PREFIX_RE.sub("[已遮蔽]", text)
    text = _WIN_HOME_RE.sub(r"C:\\Users\\[使用者]", text)
    text = _NIX_HOME_RE.sub("/home/[使用者]", text)
    return text


@dataclass
class FriendlyError:
    """給終端機使用者看的錯誤說明：標題 + 可能原因 + 具體下一步。"""

    title: str
    reasons: list[str]
    next_steps: list[str]

    def render(self) -> str:
        # 所有輸出統一經過遮蔽，避免任何 reason/title 意外帶出敏感資訊。
        title = redact_secrets(self.title)
        reasons = [redact_secrets(r) for r in self.reasons]
        lines = [f"[問題] {title}", ""]
        if reasons:
            lines.append("可能原因：")
            lines.extend(f"  - {r}" for r in reasons)
            lines.append("")
        if self.next_steps:
            lines.append("建議下一步：")
            lines.extend(f"  {i + 1}. {s}" for i, s in enumerate(self.next_steps))
        return "\n".join(lines)


def translate_exception(exc: Exception, *, url: str | None = None) -> FriendlyError:
    """把已知例外類型轉換成 FriendlyError；未知類型則回傳通用說明。"""

    if isinstance(exc, InvalidUrlError):
        return FriendlyError(
            title="這個網址看起來怪怪的",
            reasons=[str(exc)],
            next_steps=[
                "打開瀏覽器，把網址列的完整網址複製貼上",
                "確認網址沒有多餘的空格或錯字",
                "重新執行一次",
            ],
        )

    if isinstance(exc, PrivateNetworkBlockedError):
        return FriendlyError(
            title="這個網址指向內部網路，預設不允許掃描",
            reasons=[str(exc)],
            next_steps=[
                "如果你要掃描的是公開網站，請確認網址是否正確",
                "如果你確實要掃描自己的內網或本機網站（例如 localhost），"
                "請參考文件開啟 allow_private_network 選項",
            ],
        )

    if isinstance(exc, UnsafeArchiveError):
        return FriendlyError(
            title="這個壓縮檔的內容不安全，已拒絕處理",
            reasons=[str(exc)],
            next_steps=[
                "確認這個壓縮檔的來源是否可信",
                "如果是你自己產生的壓縮檔，嘗試重新打包後再試一次",
            ],
        )

    if isinstance(exc, SiteUnreachableError):
        return FriendlyError(
            title=str(exc),
            reasons=["網站可能暫時離線、網址打錯、或網站封鎖了自動化工具"],
            next_steps=[
                "先在瀏覽器打開這個網址，確認網站本身是否正常",
                "確認網址拼字正確",
                "稍後再試一次",
            ],
        )

    if isinstance(exc, httpx.ConnectTimeout):
        return FriendlyError(
            title=f"連線逾時，無法連上 {url or '這個網站'}",
            reasons=["網站暫時離線或反應太慢", "網路連線不穩定", "網站可能封鎖了自動化工具"],
            next_steps=[
                "先在瀏覽器打開這個網址，確認網站本身是否正常",
                "稍後再試一次",
                "如果問題持續，加上 --debug 查看詳細技術資訊",
            ],
        )

    if isinstance(exc, httpx.ConnectError):
        return FriendlyError(
            title=f"無法連線到 {url or '這個網站'}",
            reasons=["網址可能打錯了", "網站可能已經關閉或搬家", "本機網路連線有問題"],
            next_steps=[
                "確認網址拼字正確",
                "在瀏覽器中確認這個網站可以正常打開",
                "確認你的電腦目前可以正常上網",
            ],
        )

    if isinstance(exc, httpx.HTTPError):
        return FriendlyError(
            title=f"連線到 {url or '這個網站'} 時發生問題",
            reasons=[str(exc)],
            next_steps=[
                "稍後再試一次",
                "如果問題持續，加上 --debug 查看詳細技術資訊",
            ],
        )

    if isinstance(exc, FileNotFoundError):
        return FriendlyError(
            title="找不到指定的檔案或資料夾",
            reasons=[str(exc)],
            next_steps=[
                "確認路徑有沒有打錯字",
                "確認檔案或資料夾確實存在於這個位置",
            ],
        )

    if isinstance(exc, PermissionError):
        return FriendlyError(
            title="沒有足夠的權限存取檔案",
            reasons=[str(exc)],
            next_steps=[
                "確認你有這個資料夾的讀寫權限",
                "換一個你有權限的資料夾作為報告輸出位置（--out）",
            ],
        )

    if isinstance(exc, (LLMProviderError, ImageProviderError, AdsProviderError, AnalyticsProviderError)):
        # 這類例外的訊息本身已經是為終端機使用者寫的人話（缺金鑰/缺選配套件
        # 等），不需要再包一層「未預期的問題」，直接原樣呈現即可。
        return FriendlyError(
            title=str(exc),
            reasons=[],
            next_steps=[
                "設定好之後，用同一個指令重新執行一次即可",
                "不想申請 API 金鑰？大多數指令都有 --provider mock（或 --llm-provider mock）可以免金鑰試玩",
            ],
        )

    return FriendlyError(
        title="執行過程中發生未預期的問題",
        reasons=[f"{type(exc).__name__}: {exc}"],
        next_steps=[
            "加上 --debug 重新執行一次，查看詳細技術資訊",
            "如果問題持續，歡迎到專案的 GitHub Issues 回報",
        ],
    )
