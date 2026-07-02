"""MetaAdsProvider：接入 Meta Marketing API 的廣告 provider。

需要環境變數 META_ACCESS_TOKEN（read-only audit 至少需 `ads_read` 權限），
以及選配相依套件 `facebook-business`
（`pip install "open-seo-advisor[ads-meta]"` 或 `pip install facebook-business`）。

實作範圍與安全策略（對應 docs/roadmap.md 的分階段）：
- 目前：read-only audit（probe / fetch_insights），只讀不寫。
- apply_actions / rollback：尚未開放實際寫入 Meta 帳戶。動用真實預算的
  代操屬於最高風險操作，需在 read-only 流程與 AdsSafetyPolicy 防護經過
  充分驗證後，於後續版本才逐步開放（且高風險動作預設仍鎖住）。
"""

from __future__ import annotations

import os

from seo_advisor.ads.models import AdsAccountProfile, AdsActionPlan, InsightsRow
from seo_advisor.ads.providers.base import AdsProvider, AdsProviderError

_TOKEN_ENV_VAR = "META_ACCESS_TOKEN"


class MetaAdsProvider(AdsProvider):
    def __init__(self) -> None:
        token = os.environ.get(_TOKEN_ENV_VAR)
        if not token:
            raise AdsProviderError(
                f"找不到環境變數 {_TOKEN_ENV_VAR}，無法連接 Meta Marketing API。"
                f"請先設定：export {_TOKEN_ENV_VAR}=your-access-token"
            )

        try:
            from facebook_business.api import FacebookAdsApi
        except ImportError as exc:
            raise AdsProviderError(
                "尚未安裝 facebook-business 套件，請執行：pip install facebook-business"
            ) from exc

        app_id = os.environ.get("META_APP_ID")
        app_secret = os.environ.get("META_APP_SECRET")
        # 有 app id/secret 時啟用 appsecret proof，強化 token 使用安全性
        FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=token)

    def id(self) -> str:
        return "meta"

    def capabilities(self) -> set[str]:
        # 目前僅提供讀取能力；寫入能力待後續版本經充分驗證後開放
        return {"ads_read"}

    def probe(self, account_id: str) -> AdsAccountProfile:
        from facebook_business.adobjects.adaccount import AdAccount

        try:
            account = AdAccount(account_id)
            data = account.api_get(
                fields=["name", "currency", "timezone_name", "account_status"]
            )
        except Exception as exc:  # noqa: BLE001 - SDK 例外型別多樣，統一轉為本專案錯誤
            raise AdsProviderError(f"讀取廣告帳戶資訊失敗：{exc}") from exc

        return AdsAccountProfile(
            account_id=account_id,
            name=data.get("name", ""),
            currency=data.get("currency", ""),
            timezone=data.get("timezone_name", ""),
            notes=["Pixel / CAPI 事件檢查將於後續版本補上。"],
        )

    def fetch_insights(self, account_id: str, *, since_days: int) -> list[InsightsRow]:
        from facebook_business.adobjects.adaccount import AdAccount

        try:
            account = AdAccount(account_id)
            insights = account.get_insights(
                params={"date_preset": _date_preset(since_days), "level": "ad"},
                fields=[
                    "ad_id",
                    "ad_name",
                    "spend",
                    "impressions",
                    "clicks",
                    "frequency",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise AdsProviderError(f"讀取廣告成效資料失敗：{exc}") from exc

        rows: list[InsightsRow] = []
        for item in insights:
            rows.append(
                InsightsRow(
                    entity_id=item.get("ad_id", ""),
                    entity_type="ad",
                    name=item.get("ad_name", ""),
                    spend_minor_units=_to_minor_units(item.get("spend")),
                    impressions=int(item.get("impressions", 0) or 0),
                    clicks=int(item.get("clicks", 0) or 0),
                    frequency=float(item.get("frequency", 0) or 0),
                )
            )
        return rows

    def apply_actions(self, plan: AdsActionPlan, *, confirmation: str) -> dict:
        raise AdsProviderError(
            "Meta 廣告的實際代操（動用真實預算）尚未在此版本開放。"
            "目前僅支援 read-only audit 與 dry-run 行動計畫產出（action-plan.json），"
            "你可以檢視計畫後手動到 Meta 廣告管理員套用。"
            "自動化代操將於後續版本、且 AdsSafetyPolicy 防護經充分驗證後才逐步開放。"
        )


def _date_preset(since_days: int) -> str:
    if since_days <= 7:
        return "last_7d"
    if since_days <= 14:
        return "last_14d"
    if since_days <= 30:
        return "last_30d"
    return "last_90d"


def _to_minor_units(value) -> int:
    """把 Meta 回傳的金額字串（主要貨幣單位，例如 "80.00"）轉成最小單位整數。"""
    if value is None:
        return 0
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0
