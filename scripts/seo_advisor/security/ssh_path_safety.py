"""SSHConnector 的遠端路徑安全檢查：component-wise walk，逐層 lstat 拒絕
symlink，防止 jail escape。

背景（來自 NORA 與 Grok 交叉審查的定案）：最初設計「組合完整路徑後做一次
lstat，再用 startswith 檢查前綴」有一個經典漏洞——如果路徑中間某一段本身
就是 symlink（例如 remote_root 底下的 `blog` 目錄其實是指向 `/etc` 的
symlink），組合後的完整路徑 lstat 會直接看到 symlink *目標* 的資訊，不會
被偵測為 symlink 本身，導致可以讀到 remote_root 之外的內容。

正確做法：從 remote_root 開始，把使用者路徑拆成一個個 component，每累加
一個 component 就對「這一步的中間路徑」做一次 lstat，任何一層（不只是
最終目標）是 symlink 就立刻拒絕。同時：
- 使用者輸入的路徑絕不可呼叫 sftp 的 normalize()/realpath（那會直接
  follow symlink 到 root 外再回傳絕對路徑）；normalize() 只能用於一次性
  固定 remote_root 本身。
- 路徑分量裡出現 ".." 直接拒絕，不依賴 os.path.normpath 事後處理再用
  startswith 補救（那是常見的 jail 漏洞來源）。
- startswith 只能當最後的 sanity check，不能是主要防線。
"""

from __future__ import annotations

import stat
from dataclasses import dataclass

# 反斜線在更早的整體檢查（split_and_validate_components 開頭）就會被拒絕，
# 這裡只需要擋控制字元（0x00-0x1F；NUL 本身也已在更早被單獨檢查過，這裡
# 保留完整範圍是縱深防禦，不依賴呼叫順序）。
_FORBIDDEN_COMPONENT_CHARS = set(range(0x20))


class UnsafeRemotePathError(ValueError):
    """遠端路徑不安全（symlink、路徑穿越、控制字元等）時拋出。"""


class RemotePathNotFoundError(FileNotFoundError):
    """遠端路徑（或其中間目錄）不存在時拋出。"""


@dataclass
class RemoteStat:
    """對呼叫端而言足夠使用的遠端檔案 metadata，不暴露 paramiko 的內部型別。"""

    path: str  # 相對於 remote_root 的路徑（一律用 / 分隔）
    is_dir: bool
    size: int


def split_and_validate_components(user_path: str) -> list[str]:
    """把使用者輸入的路徑拆成分量並做語法層驗證，不觸碰檔案系統。

    拒絕：空分量以外的控制字元、反斜線、"."（多餘但不視為錯誤，直接忽略）、
    ".."（路徑穿越，直接拒絕，不嘗試用 normpath 消解）。
    """
    if not user_path or not isinstance(user_path, str):
        raise UnsafeRemotePathError("路徑不可為空。")

    if "\x00" in user_path:
        raise UnsafeRemotePathError("路徑含有 NUL 字元，拒絕存取。")

    # 刻意不把反斜線當分隔符自動轉換：遠端是 Unix 系統，路徑分隔符只會是
    # "/"，反斜線不應該出現在合法的路徑輸入裡（自動轉換等於替使用者猜測
    # 意圖，也可能被用來混淆路徑分隔語意），直接視為不允許的字元拒絕。
    if "\\" in user_path:
        raise UnsafeRemotePathError(
            f"路徑 {user_path!r} 含有反斜線，遠端是 Unix 系統路徑分隔符只會是 '/'，已拒絕存取。"
        )

    raw_components = user_path.split("/")

    components: list[str] = []
    for component in raw_components:
        if component in ("", "."):
            continue
        if component == "..":
            raise UnsafeRemotePathError(
                f"路徑 {user_path!r} 含有 '..'，可能是路徑穿越嘗試，已拒絕存取。"
            )
        if any(ord(ch) in _FORBIDDEN_COMPONENT_CHARS for ch in component):
            raise UnsafeRemotePathError(f"路徑 {user_path!r} 含有不允許的字元，已拒絕存取。")
        components.append(component)

    return components


def resolve_remote_path(sftp, remote_root_real: str, user_path: str) -> RemoteStat:
    """把使用者提供的相對路徑安全地解析到 remote_root_real 之內。

    sftp：已連線的 paramiko SFTPClient（或相容介面，測試時可用假物件）。
    remote_root_real：呼叫端在連線時已經對 remote_root 做過一次
    sftp.normalize() 得到的絕對路徑（只在連線建立時做一次，這裡不重複做）。

    逐層累加 component 並對「這一步的中間路徑」做 lstat：
    - 任一層（含最終目標）是 symlink：拒絕。
    - 任一中間層存在但不是目錄：拒絕（無法再往下走）。
    - 任一層不存在：拋出 RemotePathNotFoundError（不是安全錯誤，只是找不到）。

    絕不對 user_path 呼叫 normalize()/realpath——那個語意是「解析並 follow
    所有 symlink」，用在使用者輸入上等於完全繞過這裡的逐層檢查。
    """
    components = split_and_validate_components(user_path)

    current = remote_root_real
    for index, component in enumerate(components):
        current = current.rstrip("/") + "/" + component
        try:
            st = sftp.lstat(current)
        except FileNotFoundError as exc:
            raise RemotePathNotFoundError(f"路徑不存在：{user_path!r}") from exc

        if stat.S_ISLNK(st.st_mode):
            raise UnsafeRemotePathError(
                f"路徑 {user_path!r} 的中間或最終節點是 symlink，"
                "為避免跳出授權範圍讀取其他位置的內容，一律拒絕存取。"
            )

        is_last = index == len(components) - 1
        if not is_last and not stat.S_ISDIR(st.st_mode):
            raise RemotePathNotFoundError(
                f"路徑 {user_path!r} 的中間節點不是目錄，無法繼續解析。"
            )

    final_stat = sftp.lstat(current) if components else sftp.lstat(remote_root_real)
    rel_path = "/".join(components) if components else ""
    return RemoteStat(
        path=rel_path,
        is_dir=stat.S_ISDIR(final_stat.st_mode),
        size=final_stat.st_size if not stat.S_ISDIR(final_stat.st_mode) else 0,
    )


# 過寬的 remote_root：等同「整台機器可讀」或極淺層的系統目錄，一律拒絕。
# 這不是完整的系統目錄清單，而是「常見到會被誤用」的一組防呆規則——真正的
# 授權邊界仍然是使用者自己選擇的 remote_root，這裡只擋最容易誤設的情況。
_FORBIDDEN_ROOTS = frozenset({"/", "/var", "/home", "/etc", "/usr", "/opt", "/root", "/bin", "/sbin"})


def ensure_remote_root_allowed(remote_root_real: str) -> None:
    """拒絕過寬的 remote_root（例如整個檔案系統根目錄，或常見的系統層級
    目錄）。這不能防止使用者刻意選擇危險的 remote_root，但能擋下最常見的
    誤設情況（例如忘記加上子目錄、複製貼上時漏了路徑片段）。
    """
    normalized = remote_root_real.rstrip("/") or "/"
    if normalized in _FORBIDDEN_ROOTS:
        raise UnsafeRemotePathError(
            f"remote_root={remote_root_real!r} 是系統層級目錄或過寬的根目錄，"
            "SSHConnector 拒絕以此作為授權範圍（風險：等同整台機器可讀）。"
            "請指定實際的網站目錄，例如 /var/www/your-site。"
        )
