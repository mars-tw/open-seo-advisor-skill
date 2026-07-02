"""核心資料模型。

這些 Pydantic 模型是 schemas/*.schema.json 的 Python 對應實作。
修改欄位時請同步更新對應的 JSON Schema，兩者必須保持一致。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mode(str, Enum):
    CONSULTANT = "consultant"
    ENGINEER = "engineer"
    SECURITY = "security"
    CONTENT_WRITER = "content_writer"
    PLUGIN_DEV = "plugin_dev"
    META_ADS = "meta_ads"
    IMAGE_MATERIAL = "image_material"
    ECOMMERCE = "ecommerce"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Finding(BaseModel):
    id: str
    title: str
    mode: Mode
    category: str
    severity: Severity
    impact: int = Field(ge=1, le=5)
    effort: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    affected_urls: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    recommendation: str
    validation: list[str] = Field(default_factory=list)
    owner: Mode | None = None
    sources: list[str] = Field(default_factory=list)

    @property
    def priority_score(self) -> float:
        return (self.impact * self.confidence) / self.effort


class ReportTarget(BaseModel):
    source_type: str
    identifier: str
    industry_profile: str | None = None
    locale: str | None = None


class Report(BaseModel):
    report_id: str
    generated_at: str
    target: ReportTarget
    mode: Mode
    executive_summary: str
    site_health_score: float = Field(ge=0, le=100)
    findings: list[Finding] = Field(default_factory=list)
    top_findings: list[str] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    scan_stats: dict = Field(default_factory=dict)


class SafetyPolicy(BaseModel):
    """所有 Connector 共用的資安約束，由呼叫端（CLI/router）建立並傳入 connector。

    這是把 docs/connector_contract.md 定義的資安原則（預設 read-only、
    預設 dry-run、最小權限）從「文件規範」變成「建構子強制要求的參數」，
    避免未來新增 SSH/WordPress/Cloudflare connector 時，資安考量只停留在
    文件而沒有真的被程式碼約束。
    """

    dry_run: bool = True
    allowed_capabilities: set[str] = Field(default_factory=lambda: {"read_urls"})
    allow_private_network: bool = False
    respect_robots_txt: bool = True
    rate_limit_per_second: float = 3.0

    model_config = {"arbitrary_types_allowed": True}

    def require_capability(self, capability: str, *, connector_id: str) -> None:
        if capability not in self.allowed_capabilities:
            raise PermissionError(
                f"{connector_id} 嘗試執行需要 '{capability}' 能力的操作，"
                f"但目前的 SafetyPolicy 只允許：{sorted(self.allowed_capabilities)}。"
                "如果這是預期中的操作，請在建立 connector 時於 "
                "allowed_capabilities 明確加入這個能力。"
            )

    def require_write(self, *, connector_id: str) -> None:
        if self.dry_run:
            raise PermissionError(
                f"{connector_id} 目前處於 dry_run 模式，拒絕實際寫入。"
                "如果要真的執行寫入，需由使用者明確關閉 dry_run。"
            )


class ConnectorProfile(BaseModel):
    source_type: str
    detected_stack: str | None = None
    has_sitemap: bool = False
    has_robots_txt: bool = False
    notes: list[str] = Field(default_factory=list)


class UrlRecord(BaseModel):
    url: str
    source: str  # "sitemap" | "crawl" | "seed"
    discovered_depth: int = 0


class PageSnapshot(BaseModel):
    url: str
    status_code: int
    final_url: str
    redirect_chain: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    html: str = ""
    fetched_at: str
    fetch_error_type: str | None = None
    fetch_error_message: str | None = None
    elapsed_ms: int | None = None
    encoding: str | None = None


class FileRecord(BaseModel):
    path: str
    size_bytes: int
    is_dir: bool = False


class PatchResult(BaseModel):
    path: str
    dry_run: bool
    diff: str = ""
    applied: bool = False


class CommandResult(BaseModel):
    command: list[str]
    dry_run: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""


class LogEntry(BaseModel):
    timestamp: str
    source: str
    message: str


class DeployResult(BaseModel):
    dry_run: bool
    success: bool
    details: str = ""


class BackupResult(BaseModel):
    targets: list[str]
    backup_path: str | None = None
