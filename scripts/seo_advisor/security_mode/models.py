"""Security Mode 的資料模型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SecuritySeverity(str, Enum):
    S0_CRITICAL = "S0"
    S1_HIGH = "S1"
    S2_MEDIUM = "S2"
    S3_LOW = "S3"


class SeoImpact(str, Enum):
    INDEXING = "indexing"
    RANKING = "ranking"
    TRUST = "trust"
    USER_SAFETY = "user_safety"


class SecurityFinding(BaseModel):
    id: str
    title: str
    category: str
    severity: SecuritySeverity
    seo_impact: SeoImpact
    confidence: float = Field(ge=0, le=1)
    affected_urls: list[str] = Field(default_factory=list)
    # 只放狀態碼/長度/header 摘要等中性資訊，絕不含推測為敏感檔案的原始內容。
    evidence: dict = Field(default_factory=dict)
    recommendation: str
    needs_credential_rotation: bool = False


class SecurityReport(BaseModel):
    report_id: str
    generated_at: str
    target_url: str
    findings: list[SecurityFinding] = Field(default_factory=list)
    passive_only: bool = False
    skipped_checks: list[str] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
