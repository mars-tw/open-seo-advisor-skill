"""廣告成效診斷：把 InsightsRow 資料轉換成 AdsFinding 清單。

蒸餾數位廣告投手的常見診斷邏輯：
- 高花費低 ROAS：預算浪費候選（P1）
- 素材疲勞：高 frequency + 低 CTR（P2）
- 擴量候選：低花費高 ROAS（P2，正向機會）
- 資料不足：觀察期太短或花費太低，不足以做決策（P3）
- 追蹤設定：缺少關鍵轉換事件（P0，因為會讓整個優化失去依據）
"""

from __future__ import annotations

from seo_advisor.ads.models import (
    AdsAccountProfile,
    AdsActionType,
    AdsFinding,
    InsightsRow,
    AdsSafetyPolicy,
)

_CTR_LOW_THRESHOLD = 0.005  # 0.5%
_FREQUENCY_FATIGUE_THRESHOLD = 6.0
_ROAS_POOR_THRESHOLD = 1.0
_ROAS_SCALING_THRESHOLD = 4.0


def analyze_ads(
    account: AdsAccountProfile,
    insights: list[InsightsRow],
    *,
    policy: AdsSafetyPolicy,
) -> list[AdsFinding]:
    findings: list[AdsFinding] = []
    seq = {"tracking": 0, "performance": 0, "creative_fatigue": 0, "budget": 0, "structure": 0}

    def next_id(category: str) -> str:
        seq[category] += 1
        return f"ADS-{category.upper()}-{seq[category]:03d}"

    findings.extend(_check_tracking(account, next_id))

    for row in insights:
        has_enough_data = (
            row.days_active >= policy.min_observation_days
            and row.spend_minor_units >= policy.min_spend_minor_units_for_decision
        )

        if not has_enough_data:
            findings.append(
                AdsFinding(
                    id=next_id("performance"),
                    title=f"「{row.name}」觀察資料不足，暫不建議調整",
                    category="performance",
                    severity="P3",
                    entity_ids=[row.entity_id],
                    evidence={"days_active": row.days_active, "spend_minor_units": row.spend_minor_units},
                    recommendation="這個實體上線天數或花費還太少，資料量不足以做可靠判斷，"
                    "建議先讓它累積足夠數據（避免根據雜訊做決定）。",
                )
            )
            continue

        # 高花費低 ROAS：預算浪費候選
        if row.spend_minor_units >= policy.min_spend_minor_units_for_decision and row.roas < _ROAS_POOR_THRESHOLD:
            findings.append(
                AdsFinding(
                    id=next_id("performance"),
                    title=f"「{row.name}」花費高但 ROAS 偏低（{row.roas:.2f}）",
                    category="performance",
                    severity="P1",
                    entity_ids=[row.entity_id],
                    evidence={
                        "spend_minor_units": row.spend_minor_units,
                        "roas": round(row.roas, 2),
                        "conversions": row.conversions,
                    },
                    recommendation="這個素材/廣告的投資報酬率低於 1（花的比賺的多），"
                    "建議暫停或大幅縮減預算，把資源移到表現好的素材。",
                    suggested_action_type=AdsActionType.PAUSE_AD,
                )
            )

        # 素材疲勞：高 frequency + 低 CTR
        if row.frequency >= _FREQUENCY_FATIGUE_THRESHOLD and row.ctr < _CTR_LOW_THRESHOLD:
            findings.append(
                AdsFinding(
                    id=next_id("creative_fatigue"),
                    title=f"「{row.name}」出現素材疲勞（頻次 {row.frequency:.1f}、CTR {row.ctr * 100:.2f}%）",
                    category="creative_fatigue",
                    severity="P2",
                    entity_ids=[row.entity_id],
                    evidence={"frequency": row.frequency, "ctr": round(row.ctr, 4)},
                    recommendation="同一群受眾看到這個素材的次數過高、點擊率下滑，是典型的素材疲勞。"
                    "建議更換新素材（可用產圖素材專家產生變體）或擴大受眾。",
                    suggested_action_type=AdsActionType.PAUSE_AD,
                )
            )

        # 擴量候選：低花費高 ROAS（正向機會）
        if row.roas >= _ROAS_SCALING_THRESHOLD:
            findings.append(
                AdsFinding(
                    id=next_id("budget"),
                    title=f"「{row.name}」表現優異（ROAS {row.roas:.1f}），是擴量候選",
                    category="budget",
                    severity="P2",
                    entity_ids=[row.entity_id],
                    evidence={"roas": round(row.roas, 2), "spend_minor_units": row.spend_minor_units},
                    recommendation="這個素材投報率很高但花費還不多，建議「小幅、漸進」提高預算以擴大成效"
                    "（避免一次調太多造成學習重置）。注意：增加預算屬於高風險動作，"
                    "本工具預設不會自動執行，需你確認後手動調整。",
                    suggested_action_type=AdsActionType.INCREASE_DAILY_BUDGET,
                )
            )

    return findings


def _check_tracking(account: AdsAccountProfile, next_id) -> list[AdsFinding]:
    findings: list[AdsFinding] = []
    if not account.has_pixel:
        findings.append(
            AdsFinding(
                id=next_id("tracking"),
                title="廣告帳戶沒有偵測到 Pixel（轉換追蹤）",
                category="tracking",
                severity="P0",
                evidence={},
                recommendation="沒有 Pixel 就無法追蹤轉換，等於「盲投」，所有成效優化都失去依據。"
                "建議優先安裝 Meta Pixel 並設定核心事件（Purchase/Lead 等）。",
            )
        )
        return findings

    core_events = {"Purchase", "Lead", "CompleteRegistration"}
    if not (set(account.tracked_events) & core_events):
        findings.append(
            AdsFinding(
                id=next_id("tracking"),
                title="Pixel 缺少核心轉換事件（Purchase/Lead 等）",
                category="tracking",
                severity="P1",
                evidence={"tracked_events": account.tracked_events},
                recommendation="目前只追蹤到瀏覽類事件，缺少能反映商業成果的核心轉換事件，"
                "建議補齊，否則優化目標會失準。",
            )
        )
    return findings


def compute_account_health_score(findings: list[AdsFinding]) -> float:
    penalty = {"P0": 30.0, "P1": 12.0, "P2": 5.0, "P3": 1.0}
    score = 100.0
    for finding in findings:
        score -= penalty.get(finding.severity, 1.0)
    return max(0.0, round(score, 1))
