"""UTM 產生器與歸因衛生檢查。

讓行銷團隊有一致的 campaign 命名規範與 UTM 標記，避免流量在報表中被拆成
多組來源、或歸因不清。純邏輯，不需要外部 API。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from seo_advisor.growth.models import UtmAuditItem, UtmParams, UtmPlan
from seo_advisor.models import Severity

_CHANNEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "google": ("google", "cpc"),
    "google_ads": ("google", "cpc"),
    "facebook": ("facebook", "paid_social"),
    "meta": ("facebook", "paid_social"),
    "instagram": ("instagram", "paid_social"),
    "email": ("newsletter", "email"),
    "edm": ("newsletter", "email"),
    "line": ("line", "social"),
    "linkedin": ("linkedin", "paid_social"),
    "youtube": ("youtube", "video"),
    "tiktok": ("tiktok", "paid_social"),
}

_REQUIRED_FIELDS = ("utm_source", "utm_medium", "utm_campaign")
_UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
_INVALID_NAMING_PATTERN = re.compile(r"[\s一-鿿]")


def build_utm_url(base_url: str, params: UtmParams) -> str:
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(_params_to_query(params))
    return urlunparse(parsed._replace(query=urlencode(query, doseq=False)))


def audit_utm_urls(urls: list[str]) -> list[UtmAuditItem]:
    items: list[UtmAuditItem] = []
    campaign_to_urls: dict[str, list[str]] = defaultdict(list)

    for url in urls:
        parsed = urlparse(url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))

        for field in _REQUIRED_FIELDS:
            if not query.get(field, "").strip():
                items.append(
                    UtmAuditItem(
                        url=url,
                        severity=Severity.P1,
                        issue_code="utm_required_missing",
                        field=field,
                        message=f"缺少必要 UTM 欄位：{field}",
                        recommendation=f"補上 {field}，避免流量被歸到 unknown 或 referral。",
                    )
                )

        for field in _UTM_FIELDS:
            value = query.get(field)
            if not value:
                continue
            if value != value.lower():
                items.append(
                    UtmAuditItem(
                        url=url,
                        severity=Severity.P2,
                        issue_code="utm_mixed_case",
                        field=field,
                        message=f"{field} 使用大小寫混用：{value}",
                        recommendation="UTM 命名建議一律使用小寫，避免報表被拆成多組來源。",
                    )
                )
            if _INVALID_NAMING_PATTERN.search(value):
                items.append(
                    UtmAuditItem(
                        url=url,
                        severity=Severity.P2,
                        issue_code="utm_unsafe_characters",
                        field=field,
                        message=f"{field} 含空格或中文：{value}",
                        recommendation="UTM 建議使用小寫英文、數字、底線或連字號。",
                    )
                )

        campaign = query.get("utm_campaign", "").strip()
        if campaign:
            campaign_to_urls[campaign.lower()].append(url)

    duplicate_campaigns = {
        campaign: campaign_urls
        for campaign, campaign_urls in campaign_to_urls.items()
        if len(campaign_urls) > 1
    }
    for campaign, campaign_urls in duplicate_campaigns.items():
        if _has_conflicting_sources_or_mediums(campaign_urls):
            for url in campaign_urls:
                items.append(
                    UtmAuditItem(
                        url=url,
                        severity=Severity.P2,
                        issue_code="utm_campaign_reused_across_channels",
                        field="utm_campaign",
                        message=f"campaign 名稱重複且跨來源/媒介混用：{campaign}",
                        recommendation=(
                            "同一 campaign 可跨渠道使用，但 source/medium 必須一致可讀；"
                            "若活動目的不同，請拆成不同 campaign 名稱。"
                        ),
                    )
                )

    return items


def build_utm_plan(base_url: str, channels: list[str]) -> UtmPlan:
    normalized_channels = [_normalize_token(channel) for channel in channels if channel.strip()]
    params_by_channel: dict[str, UtmParams] = {}
    tagged_urls: list[str] = []

    campaign = _derive_campaign_name(base_url)
    for channel in normalized_channels:
        source, medium = _CHANNEL_DEFAULTS.get(channel, (channel, "referral"))
        params = UtmParams(source=source, medium=medium, campaign=campaign, content=channel)
        params_by_channel[channel] = params
        tagged_urls.append(build_utm_url(base_url, params))

    recommendations = [
        "utm_source 使用平台或來源名稱，例如 google、facebook、instagram、newsletter。",
        "utm_medium 使用渠道類型，例如 cpc、paid_social、email、social、referral。",
        "utm_campaign 使用同一活動名稱，建議小寫英文與連字號，例如 summer_launch_2026。",
        "utm_content 用來區分素材、版位或受眾，例如 feed_a、story_b、button_top。",
        "避免空格、中文、大小寫混用；報表會把不同寫法視為不同來源。",
    ]

    return UtmPlan(
        base_url=base_url,
        channels=normalized_channels,
        tagged_urls=tagged_urls,
        params_by_channel=params_by_channel,
        naming_recommendations=recommendations,
        audit_items=audit_utm_urls(tagged_urls),
    )


def _params_to_query(params: UtmParams) -> dict[str, str]:
    query = {
        "utm_source": params.source,
        "utm_medium": params.medium,
        "utm_campaign": params.campaign,
    }
    if params.term:
        query["utm_term"] = params.term
    if params.content:
        query["utm_content"] = params.content
    return query


def _normalize_token(value: str) -> str:
    token = value.strip().lower()
    token = re.sub(r"[\s_]+", "-", token)
    token = re.sub(r"[^a-z0-9-]+", "", token)
    return token.strip("-") or "channel"


def _derive_campaign_name(base_url: str) -> str:
    parsed = urlparse(base_url)
    host = parsed.netloc.replace("www.", "") or "campaign"
    path = parsed.path.strip("/").replace("/", "-")
    raw = f"{host}-{path}" if path else f"{host}-campaign"
    return _normalize_token(raw).replace("-", "_")


def _has_conflicting_sources_or_mediums(urls: list[str]) -> bool:
    pairs: Counter[tuple[str, str]] = Counter()
    for url in urls:
        query = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
        pairs[(query.get("utm_source", ""), query.get("utm_medium", ""))] += 1
    return len(pairs) > 1
