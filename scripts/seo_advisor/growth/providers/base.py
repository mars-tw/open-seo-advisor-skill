"""成效分析 provider 抽象介面（一律 read-only）。

Google Ads adapter 雖然會讀取花費與成效指標，但**絕不修改**廣告活動、
預算、出價、素材或帳戶設定——廣告的任何變更一律走 Meta Ads 模式的
dry-run 計畫流程並受 AdsSafetyPolicy 約束，這裡只負責讀取分析。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.growth.models import AnalyticsMetricRow


class AnalyticsProviderError(RuntimeError):
    """成效分析 API 呼叫失敗時拋出。"""


class AnalyticsProvider(ABC):
    @abstractmethod
    def id(self) -> str:
        """回傳 provider id，例如 'ga4'、'search_console'、'google_ads'、'mock'。"""

    def capabilities(self) -> set[str]:
        return {"read_metrics"}

    @abstractmethod
    def fetch_metrics(self, property_id: str, since_days: int) -> list[AnalyticsMetricRow]:
        """取得指定時間窗內、正規化後的各渠道/來源成效資料。"""
