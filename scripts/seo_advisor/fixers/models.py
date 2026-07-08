"""Engineer Mode 的資料模型：從 Finding 產出 Patch Plan，經人工確認後才寫入。

安全設計（見 docs/connector_contract.md 與 SafetyPolicy）：
- 預設 dry-run，PatchPlan 只是「計畫」，不代表已寫入。
- 真寫入需要 plan_id 綁定的確認字串（見 fixers/safety.py），避免使用者
  誤把確認字串套用到不同的修復計畫。
- 每個 FixTarget 只允許 Engineer Mode 自己認得的靜態資產副檔名，絕不允許
  修改任何程式邏輯檔案（.py/.php/.js/.ts/.sh 等）。
"""

from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

# 允許 Engineer Mode 寫入的副檔名白名單：只涵蓋靜態 SEO 相關資產，絕不包含
# 任何可執行程式碼的副檔名。新增可修復類型時，若需要新副檔名，必須在這裡
# 明確加入並說明理由，不得繞過此白名單直接寫入。
ALLOWED_WRITE_EXTENSIONS = frozenset({".txt", ".xml", ".html", ".htm"})

# 絕對禁止寫入的檔名/路徑片段，即使副檔名意外符合白名單也要擋下（縱深防禦）。
# ".seo-advisor/" 是 Engineer Mode 自己的備份目錄——絕不允許被當成修復目標，
# 否則可能被誘導覆蓋/汙染備份本身，破壞 rollback 機制的完整性。
FORBIDDEN_PATH_HINTS = (
    ".env",
    ".git/",
    "wp-config.php",
    ".ssh/",
    "id_rsa",
    ".seo-advisor/",
)

# Windows 保留裝置名稱：即使副檔名合法，這些 basename 在 Windows 上會被導向
# 特殊裝置而非一般檔案，拒絕寫入以避免未定義行為。
_WINDOWS_RESERVED_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
})

FixType = Literal["robots_txt", "sitemap", "canonical"]
RiskLevel = Literal["low", "medium", "high"]


class FixTarget(BaseModel):
    """單一檔案的修改內容。"""

    path: str  # 相對於 source root 的路徑
    original_content: str
    fixed_content: str
    diff_preview: str


class PatchPlan(BaseModel):
    """一份修復計畫：可能包含多個檔案的修改，需整體一起確認、一起套用。"""

    plan_id: str
    finding_id: str
    fix_type: FixType
    risk_level: RiskLevel
    targets: list[FixTarget] = Field(default_factory=list)
    summary: str
    validation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FixResult(BaseModel):
    """套用 PatchPlan 後的結果。"""

    plan_id: str
    applied: bool
    backup_id: str | None = None
    written_paths: list[str] = Field(default_factory=list)
    validation_passed: bool = False
    validation_notes: list[str] = Field(default_factory=list)


class RollbackResult(BaseModel):
    """從備份還原的結果。"""

    backup_id: str
    restored: bool
    restored_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)  # 使用者事後又改過的檔案
    notes: list[str] = Field(default_factory=list)


class NotFixableError(ValueError):
    """指定的 finding 目前沒有對應的自動修復邏輯時拋出。"""


class UnsafeWriteTargetError(ValueError):
    """要寫入的路徑不在白名單/禁止清單允許範圍內時拋出。"""


def ensure_write_target_allowed(path: str) -> None:
    """檢查路徑是否符合 Engineer Mode 的寫入白名單與禁止清單。

    這是每個 fixer 產生 FixTarget 前都必須呼叫的縱深防禦檢查，獨立於
    connector 層的 resolve_inside_root（那個防的是路徑穿越，這裡防的是
    「即使路徑合法，也不該是這類檔案」）。

    正規化步驟（NORA 複審指出的繞過手法逐一防禦）：
    - Unicode NFKC 正規化：避免全形字元、組合字元等視覺相似但位元組不同的
      寫法繞過字串比對（例如全形句點 . 看起來像句點但不是）。
    - 統一轉小寫、統一路徑分隔符為 /：避免大小寫或 Windows \\ 分隔符繞過。
    - 拒絕控制字元（含 NUL）：避免 Windows NTFS 特殊語意（如 ADS 的
      "file.html:evil" 雖然本函式用 rsplit 仍會取到 "evil" 副檔名而被擋下，
      但控制字元本身就不該出現在合法檔名裡，一律先拒絕）。
    - 拒絕 Windows 保留裝置名稱（CON/PRN/AUX/NUL/COM1-9/LPT1-9）。
    """
    normalized = unicodedata.normalize("NFKC", path).lower().replace("\\", "/")

    if any(ord(ch) < 0x20 for ch in normalized) or "\x00" in path:
        raise UnsafeWriteTargetError(f"{path!r} 含有控制字元，拒絕寫入。")

    for hint in FORBIDDEN_PATH_HINTS:
        if hint in normalized:
            raise UnsafeWriteTargetError(
                f"{path!r} 屬於敏感檔案/目錄，Engineer Mode 永遠不會寫入這類路徑。"
            )

    basename = normalized.rsplit("/", 1)[-1]
    stem = basename.split(".", 1)[0]
    if stem in _WINDOWS_RESERVED_NAMES:
        raise UnsafeWriteTargetError(f"{path!r} 是 Windows 保留裝置名稱，拒絕寫入。")

    suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
    if suffix not in ALLOWED_WRITE_EXTENSIONS:
        raise UnsafeWriteTargetError(
            f"{path!r} 的副檔名不在 Engineer Mode 允許寫入的範圍內"
            f"（僅允許 {sorted(ALLOWED_WRITE_EXTENSIONS)}）。"
            "Engineer Mode 絕不修改任何程式邏輯檔案。"
        )
