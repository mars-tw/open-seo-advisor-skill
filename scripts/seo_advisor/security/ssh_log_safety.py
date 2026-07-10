"""SSHConnector 的 log 讀取安全檢查：獨立於 remote_root 的檔案白名單。

背景（NORA×Grok 雙模型交叉辯論定案，SSHConnector 接進 CLI + read_logs）：
log 檔案天然常在網站 remote_root 之外（例如網站在 `/var/www/site`，
log 在 `/var/log/nginx/access.log`），把兩者塞進同一個 jail 會逼使用者
把 remote_root 開到過寬的共同父目錄，或者根本讀不到 log。因此 log 走
獨立的白名單機制：

1. 只允許「具體檔案」的白名單（不允許目錄白名單 + 動態檔名），
   `allowed_log_paths` 是 `{log_type: 絕對路徑}` 的固定映射。
2. log 路徑本身仍必須用與 `read_file()` 完全相同的 component-wise walk
   驗證整條路徑（從根目錄開始，父鏈上任一層是 symlink 一律拒絕，不因為
   `resolve_remote_path()` 換了一個不同的起點就放鬆檢查）；最終節點必須
   是 regular file（拒絕目錄、拒絕 symlink）。
3. `ensure_log_path_allowed()` 拒絕的是「條目本身等於過寬根目錄」（例如
   把 `/var/log` 當成一個檔案路徑填進白名單），不是「拒絕任何位於
   `/var/...` 之下的檔案」——`/var/log/nginx/access.log` 完全合法。
"""

from __future__ import annotations

import re
import stat

from seo_advisor.security.ssh_path_safety import (
    RemotePathNotFoundError,
    UnsafeRemotePathError,
    ensure_log_path_allowed,
    resolve_remote_path,
)

_LOG_TYPE_PATTERN = re.compile(r"^[a-z0-9_-]+$")


class InvalidLogConfigError(ValueError):
    """`allowed_log_paths` 的設定本身不合法時拋出（在建構子階段，不涉及
    實際的遠端連線）。
    """


def validate_allowed_log_paths(allowed_log_paths: dict[str, str]) -> dict[str, str]:
    """驗證 `allowed_log_paths` 設定的語法合法性（不觸碰遠端檔案系統）：
    key 只能是 `[a-z0-9_-]+`、path 必須是絕對 POSIX 路徑、拒絕 glob/
    wildcard 字元、拒絕過寬的根路徑。
    """
    validated: dict[str, str] = {}
    for log_type, path in allowed_log_paths.items():
        if not _LOG_TYPE_PATTERN.match(log_type):
            raise InvalidLogConfigError(
                f"log_type {log_type!r} 不合法，只能使用小寫英數字、'_'、'-'。"
            )
        if not isinstance(path, str) or not path.startswith("/"):
            raise InvalidLogConfigError(
                f"allowed_log_paths[{log_type!r}] 必須是絕對路徑（以 '/' 開頭），收到：{path!r}"
            )
        if any(ch in path for ch in ("*", "?", "[", "]")):
            raise InvalidLogConfigError(
                f"allowed_log_paths[{log_type!r}] 不可包含萬用字元（*、?、[、]）："
                f"{path!r}。allowed_log_paths 只接受具體檔案路徑，不支援 glob。"
            )
        ensure_log_path_allowed(path)
        validated[log_type] = path
    return validated


def resolve_log_path(sftp, log_path: str) -> str:
    """對 log 的絕對路徑做完整的 component-wise walk（從根目錄開始，
    父鏈上任一層是 symlink 一律拒絕），並確認最終節點是 regular file
    （拒絕目錄、拒絕 symlink，包含 log rotate 用 symlink 切換的情況）。

    回傳值是驗證通過後、可直接交給 sftp.open() 的絕對路徑字串。
    """
    resolved = resolve_remote_path(sftp, "/", log_path.lstrip("/"))
    if resolved.is_dir:
        raise UnsafeRemotePathError(f"log 路徑 {log_path!r} 是目錄，不是檔案，無法讀取。")
    return "/" + resolved.path


def tail_log_content(sftp, resolved_path: str, *, max_tail_bytes: int) -> bytes:
    """從檔案尾端讀取最多 `max_tail_bytes` bytes，而不是從頭讀——使用者
    通常關心最新的 log 內容。若從檔案中段開始讀，會丟棄第一個不完整的行
    （因為讀取起點很可能落在某一行的中間）。

    讀取量固定受 max_tail_bytes 上限，即使遠端 SFTP server 回報異常巨大
    的檔案大小（惡意或故障的 server），實際讀取的位元組數不會超過這個
    上限——size 只用來決定 seek 的起點，不會被拿來一次性配置對應大小的
    buffer 或整檔讀入。

    這個讀取方式存在已知的 race window（檔案在 stat 之後、read 之前持續
    被寫入/rotate），可能讀到略舊或不完整的內容；這是正確性層面的殘餘
    風險，不是安全層面的 jail escape（路徑本身已在呼叫端經過
    resolve_log_path 驗證，這裡只做位元組層級的 I/O）。
    """
    file_stat = sftp.lstat(resolved_path)
    if stat.S_ISLNK(file_stat.st_mode):
        raise UnsafeRemotePathError(f"log 路徑 {resolved_path!r} 是 symlink，拒絕讀取。")

    size = file_stat.st_size or 0
    start = max(0, size - max_tail_bytes)

    try:
        with sftp.open(resolved_path, "rb") as f:
            if start > 0:
                f.seek(start)
            content = f.read(max_tail_bytes + 1)
    except FileNotFoundError as exc:
        raise RemotePathNotFoundError(f"log 檔案讀取時消失：{resolved_path!r}") from exc

    if len(content) > max_tail_bytes:
        content = content[-max_tail_bytes:]

    if start > 0 and content:
        # 讀取起點很可能落在某一行中間，丟棄第一個不完整的片段。
        newline_index = content.find(b"\n")
        if newline_index != -1:
            content = content[newline_index + 1 :]
        else:
            # 整個讀取範圍內都找不到換行字元：代表這個 tail 視窗比單行還短，
            # 內容本身就不足以構成完整一行，回傳空值而非半行亂碼。
            content = b""

    return content
