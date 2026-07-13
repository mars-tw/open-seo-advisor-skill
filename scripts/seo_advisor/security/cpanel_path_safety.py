"""CPanelConnector 的遠端路徑安全檢查：component-wise walk，防止透過
cPanel UAPI Fileman 讀寫 remote_root 之外的檔案。

背景：與 SSHConnector（security/ssh_path_safety.py）同樣的核心風險——
如果只組合完整路徑後呼叫一次 API 檢查，中間某一段若本身是 symlink（例如
`public_html/blog` 其實是指向 `/etc` 的 symlink），直接查詢組合後的完整
路徑會看到 symlink *目標* 的資訊，不會被偵測為 symlink 本身，導致讀寫到
remote_root 之外的內容。

跟 SFTP 的 `lstat()` 不同，cPanel UAPI 沒有「對單一路徑做一次 lstat」的
對應操作，只有 `Fileman::list_files`（列出目錄內容，每個項目回傳
`type`/`file`/`dir`/`fullpath` 等欄位）。因此這裡的 component-wise walk
是「逐層呼叫 list_files 列出目前目錄，比對下一個路徑分量是否存在、其
type 是否為 symlink」，而不是逐層 lstat——邏輯目的相同（每一步都要看到
「這一步本身」的真實類型，不能被中途 follow 過去），只是實作方式因 API
形狀而不同。

語法層驗證（split_and_validate_components）與 SSHConnector 完全共用同一套
規則：拒絕 NUL/控制字元/反斜線/".."，不依賴 normpath 事後消解。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from seo_advisor.security.ssh_path_safety import (
    UnsafeRemotePathError,
    split_and_validate_components,
)

__all__ = [
    "UnsafeRemotePathError",
    "RemoteFileEntry",
    "RemoteFileNotFoundError",
    "resolve_remote_path",
    "ensure_remote_root_allowed",
    "split_and_validate_components",
]


class RemoteFileNotFoundError(FileNotFoundError):
    """遠端路徑（或其中間目錄）不存在時拋出。"""


@dataclass
class RemoteFileEntry:
    """對呼叫端而言足夠使用的遠端檔案 metadata，不暴露 cPanel UAPI 的
    原始回應格式。"""

    path: str  # 相對於 remote_root 的路徑（一律用 / 分隔）
    is_dir: bool
    is_link: bool
    size: int


# ListDirFn 簽名：(directory_path) -> list[RemoteFileEntry]，由呼叫端
# （CPanelConnector）提供，把 UAPI 的原始回應轉成 RemoteFileEntry 清單。
# 這裡刻意不直接依賴 httpx/UAPI 回應格式，讓路徑安全邏輯可以獨立測試
# （用假的 list_dir 函式模擬各種目錄結構），也讓 connector 本身可以決定
# 要不要做額外的快取。
ListDirFn = Callable[[str], list[RemoteFileEntry]]


def resolve_remote_path(list_dir: ListDirFn, remote_root: str, user_path: str) -> RemoteFileEntry:
    """把使用者提供的相對路徑安全地解析到 remote_root 之內。

    逐層呼叫 list_dir() 列出目前路徑下的項目，比對下一個路徑分量：
    - 找不到對應項目：拋出 RemoteFileNotFoundError。
    - 對應項目是 symlink（任一層，含最終目標）：拒絕。
    - 中間層存在但不是目錄：拒絕（無法再往下走）。

    絕不對 user_path 做「先組合完整路徑再一次查詢」——那樣會讓中間層的
    symlink 被 API 自己 resolve 掉，看不到真實類型。

    user_path 不可為空字串（split_and_validate_components 會直接拒絕）；
    呼叫端若要表示「remote_root 本身」，應在呼叫這個函式之前自行判斷並
    跳過（比照 SSHConnector.list_files 對空字串 path 的既有處理方式）。
    """
    components = split_and_validate_components(user_path)

    current_dir = remote_root
    current_entry: RemoteFileEntry = None  # type: ignore[assignment]

    for index, component in enumerate(components):
        entries = list_dir(current_dir)
        matched = next((e for e in entries if e.path.rsplit("/", 1)[-1] == component), None)
        if matched is None:
            raise RemoteFileNotFoundError(f"路徑不存在：{user_path!r}")

        if matched.is_link:
            raise UnsafeRemotePathError(
                f"路徑 {user_path!r} 的中間或最終節點是 symlink，"
                "為避免跳出授權範圍讀取其他位置的內容，一律拒絕存取。"
            )

        is_last = index == len(components) - 1
        if not is_last and not matched.is_dir:
            raise RemoteFileNotFoundError(f"路徑 {user_path!r} 的中間節點不是目錄，無法繼續解析。")

        current_entry = matched
        current_dir = current_dir.rstrip("/") + "/" + component

    return RemoteFileEntry(
        path="/".join(components), is_dir=current_entry.is_dir, is_link=False, size=current_entry.size
    )


# 過寬的 remote_root：等同「整個帳戶可讀」或系統層級目錄，一律拒絕。
_FORBIDDEN_ROOTS = frozenset({"", "/", ".", "home", "/home", "/etc", "/var", "/usr", "/root"})


def ensure_remote_root_allowed(remote_root: str) -> None:
    """拒絕過寬的 remote_root。cPanel 的 remote_root 通常是帳戶家目錄下的
    相對路徑（例如 `public_html`），這裡拒絕明顯過寬或指向帳戶根目錄本身
    的設定，避免使用者不小心把整個帳戶家目錄當成授權範圍。
    """
    normalized = remote_root.strip().rstrip("/")
    if normalized.lower() in _FORBIDDEN_ROOTS:
        raise UnsafeRemotePathError(
            f"remote_root={remote_root!r} 是過寬的根目錄，CPanelConnector 拒絕以此作為"
            "授權範圍。請指定實際的網站目錄，例如 public_html 或 public_html/subsite。"
        )
