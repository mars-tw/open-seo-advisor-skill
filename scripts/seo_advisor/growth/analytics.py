"""統一的跨渠道成效診斷（蒸餾成效分析師 ORION 的判斷邏輯）。

四類診斷：追蹤缺漏、高流量低轉換、高成本低回報、擴量機會。用觀察到的
中位數轉換率做動態門檻，避免用固定值誤判不同產業/帳戶。
"""

from __future__ import annotations

from statistics import median

from seo_advisor.growth.models import AnalyticsFinding, AnalyticsMetricRow
from seo_advisor.models import Severity


def analyze_metrics(rows: list[AnalyticsMetricRow]) -> list[AnalyticsFinding]:
    if not rows:
        return [
            AnalyticsFinding(
                category="tracking",
                severity=Severity.P1,
                title="沒有可分析的成效資料",
                evidence={},
                recommendation="確認 GA4、Search Console 或廣告資料來源是否已授權，或先使用 mock demo。",
            )
        ]

    findings: list[AnalyticsFinding] = []
    conversion_rates = [row.conversion_rate for row in rows if row.sessions >= 50]
    median_cvr = median(conversion_rates) if conversion_rates else 0.0

    findings.extend(_find_tracking_gaps(rows))
    findings.extend(_find_low_conversion_traffic(rows, median_cvr))
    findings.extend(_find_high_cost_low_return(rows))
    findings.extend(_find_scale_opportunities(rows, median_cvr))

    return findings[:10]


def compute_summary(rows: list[AnalyticsMetricRow], findings: list[AnalyticsFinding]) -> str:
    total_sessions = sum(row.sessions for row in rows)
    total_conversions = sum(row.conversions for row in rows)
    total_cost = sum(row.cost_minor_units or 0 for row in rows)
    total_revenue = sum(row.revenue_minor_units or 0 for row in rows)
    overall_cvr = total_conversions / total_sessions if total_sessions else 0.0

    p0_p1_count = sum(1 for finding in findings if finding.severity in {Severity.P0, Severity.P1})
    return (
        f"本次共分析 {len(rows)} 個渠道，總 sessions 為 {total_sessions}，"
        f"總轉換 {total_conversions}，整體轉換率約 {overall_cvr:.2%}。"
        f"已辨識 {len(findings)} 項成效問題，其中 {p0_p1_count} 項屬高優先處理。"
        f"廣告成本合計約 {total_cost} minor units，營收合計約 {total_revenue} minor units；"
        "建議先處理追蹤缺漏與高成本低回報渠道，再評估高轉換率低流量渠道的擴量。"
    )


def _find_tracking_gaps(rows: list[AnalyticsMetricRow]) -> list[AnalyticsFinding]:
    findings: list[AnalyticsFinding] = []
    for row in rows:
        if row.sessions >= 300 and row.conversions == 0:
            findings.append(
                AnalyticsFinding(
                    category="tracking",
                    severity=Severity.P1,
                    title=f"{row.channel} 有流量但沒有任何轉換，疑似追蹤缺漏",
                    evidence={
                        "channel": row.channel,
                        "sessions": row.sessions,
                        "conversions": row.conversions,
                        "clicks": row.clicks,
                    },
                    recommendation=(
                        "檢查 GA4 conversion event、thank-you page、表單送出事件、"
                        "UTM 是否正確帶入，避免把真實成效誤判為零。"
                    ),
                )
            )
    return findings


def _find_low_conversion_traffic(
    rows: list[AnalyticsMetricRow], median_cvr: float
) -> list[AnalyticsFinding]:
    findings: list[AnalyticsFinding] = []
    threshold = max(0.005, median_cvr * 0.4)

    for row in rows:
        if row.sessions >= 500 and 0 < row.conversion_rate <= threshold:
            findings.append(
                AnalyticsFinding(
                    category="conversion",
                    severity=Severity.P2,
                    title=f"{row.channel} 流量高但轉換率偏低",
                    evidence={
                        "channel": row.channel,
                        "sessions": row.sessions,
                        "conversions": row.conversions,
                        "conversion_rate": row.conversion_rate,
                        "median_conversion_rate": median_cvr,
                        # 判斷門檻透明化：低於此轉換率且流量≥500 才會被標記。
                        "flagged_threshold": round(threshold, 4),
                        "threshold_rule": "max(0.5%, 各渠道轉換率中位數 × 0.4)",
                        "threshold_profile": "default",
                        "min_sessions_to_flag": 500,
                    },
                    recommendation=(
                        "檢查落地頁訊息是否承接廣告/貼文承諾、CTA 是否明確、"
                        "表單是否過長，以及受眾意圖是否與頁面一致。"
                        "（此門檻為通用預設值，請依你的產業、客單價與銷售週期調整判斷。）"
                    ),
                )
            )
    return findings


def _find_high_cost_low_return(rows: list[AnalyticsMetricRow]) -> list[AnalyticsFinding]:
    findings: list[AnalyticsFinding] = []
    for row in rows:
        cost = row.cost_minor_units or 0
        revenue = row.revenue_minor_units or 0
        if cost <= 0:
            continue

        roas = revenue / cost if cost else 0.0
        cost_per_conversion = cost / row.conversions if row.conversions else None
        if cost >= 50_000 and (row.conversions <= 3 or roas < 0.8):
            findings.append(
                AnalyticsFinding(
                    category="spend",
                    severity=Severity.P1,
                    title=f"{row.channel} 成本高但回報偏低",
                    evidence={
                        "channel": row.channel,
                        "cost_minor_units": cost,
                        "revenue_minor_units": revenue,
                        "conversions": row.conversions,
                        "roas": round(roas, 2),
                        "cost_per_conversion": cost_per_conversion,
                        # 判斷門檻透明化：花費≥500 元且（轉換≤3 或 ROAS<0.8）才標記。
                        "flagged_rule": "cost ≥ 500 且 (conversions ≤ 3 或 ROAS < 0.8)",
                        "roas_threshold": 0.8,
                        "threshold_profile": "default",
                    },
                    recommendation=(
                        "先不要加碼此渠道；檢查關鍵字/受眾、素材、出價與落地頁，"
                        "必要時只產生 dry-run 預算調整計畫，需人工審核後才套用。"
                        "（ROAS 0.8 為通用預設門檻，實際可接受值依你的毛利率而定。）"
                    ),
                )
            )
    return findings


def _find_scale_opportunities(
    rows: list[AnalyticsMetricRow], median_cvr: float
) -> list[AnalyticsFinding]:
    findings: list[AnalyticsFinding] = []
    if median_cvr <= 0:
        return findings

    for row in rows:
        if 30 <= row.sessions <= 300 and row.conversion_rate >= median_cvr * 1.8:
            findings.append(
                AnalyticsFinding(
                    category="traffic",
                    severity=Severity.P2,
                    title=f"{row.channel} 轉換率高但流量偏低，可能有擴量機會",
                    evidence={
                        "channel": row.channel,
                        "sessions": row.sessions,
                        "conversions": row.conversions,
                        "conversion_rate": row.conversion_rate,
                        "median_conversion_rate": median_cvr,
                    },
                    recommendation=(
                        "檢查此渠道的受眾、內容、offer 或名單來源，規劃小幅擴量測試；"
                        "若涉及廣告預算，只能先產 dry-run 計畫。"
                    ),
                )
            )
    return findings
