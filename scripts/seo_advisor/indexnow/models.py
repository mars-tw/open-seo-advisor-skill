"""IndexNow 的資料模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IndexNowUrlValidation(BaseModel):
    """單一 URL 是否通過提交前的語法/scope 驗證。"""

    url: str
    accepted: bool
    reason: str = ""


class IndexNowBatchResult(BaseModel):
    """單一批次的送出結果。"""

    batch_index: int
    url_count: int
    status_code: int | None = None
    response_status: str
    detail: str = ""


class IndexNowSubmissionResult(BaseModel):
    """一次完整提交（可能包含多個批次）的結果，供 CLI 輸出報告使用。"""

    dry_run: bool
    site: str
    key_location: str
    key_verified: bool
    endpoint: str
    submitted_count: int
    skipped_count: int
    url_validations: list[IndexNowUrlValidation] = Field(default_factory=list)
    batches: list[IndexNowBatchResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
