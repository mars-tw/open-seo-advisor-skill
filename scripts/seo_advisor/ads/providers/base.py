"""AdsProvider 抽象介面：讓廣告優化專家不綁定單一廣告平台。

與 WebsiteConnector 平行的設計（都共用 SafetyPolicy 精神），但因為廣告帳戶
的資料模型（campaign/adset/ad/insights）與網站爬取完全不同，故獨立成一套
介面而非硬塞進 WebsiteConnector。

資安要求：憑證只從環境變數讀取，例外訊息不得包含 token 內容。所有 apply/
rollback 都必須先經過 AdsSafetyPolicy 檢查（在 planner/runner 層強制），
provider 本身也應在 dry_run 時拒絕實際寫入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.ads.models import (
    AdsAccountProfile,
    AdsActionPlan,
    InsightsRow,
)


class AdsProviderError(RuntimeError):
    """廣告平台 API 呼叫失敗時拋出。"""


class AdsProvider(ABC):
    @abstractmethod
    def id(self) -> str:
        """回傳 provider 識別字串，例如 'meta'、'mock'。"""

    @abstractmethod
    def capabilities(self) -> set[str]:
        """回傳支援的能力，例如 {'ads_read'} 或 {'ads_read', 'ads_write'}。"""

    @abstractmethod
    def probe(self, account_id: str) -> AdsAccountProfile:
        """取得廣告帳戶基本資訊與追蹤設定狀態。"""

    @abstractmethod
    def fetch_insights(self, account_id: str, *, since_days: int) -> list[InsightsRow]:
        """取得帳戶內各實體在觀察期間的成效資料。"""

    def apply_actions(self, plan: AdsActionPlan, *, confirmation: str) -> dict:
        """套用行動計畫（實際寫入廣告帳戶）。

        預設實作拒絕（read-only provider）。支援寫入的子類別必須：
        1. 先檢查 plan.dry_run（dry_run 時不得實際寫入）
        2. 驗證 confirmation 與 plan.required_confirmation 完全一致
        3. 對每個動作記錄 rollback_snapshot
        """
        raise AdsProviderError(
            f"{self.id()} 不支援 apply_actions()（read-only），"
            "無法實際套用變更到廣告帳戶。"
        )

    def rollback(self, change_log: dict, *, confirmation: str) -> dict:
        raise AdsProviderError(f"{self.id()} 不支援 rollback()。")
