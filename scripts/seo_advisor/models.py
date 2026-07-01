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
