"""廣告優化專家的執行協調：audit（診斷）與 plan（產出 dry-run 行動計畫）。

安全底線：這裡不提供任何會實際寫入 Meta 帳戶的路徑。audit 只讀取與分析，
plan 只產出計畫檔案。真實 apply 需要另外經過 AdsSafetyPolicy 的多重確認，
且會擴大花費的動作預設全部鎖住（見 models.AdsSafetyPolicy）。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from seo_advisor.ads.analyzer import analyze_ads, compute_account_health_score
from seo_advisor.ads.models import AdsActionPlan, AdsReport, AdsSafetyPolicy
from seo_advisor.ads.planner import build_action_plan
from seo_advisor.ads.providers.base import AdsProvider
from seo_advisor.ads.report import (
    render_action_plan_json,
    render_ads_report_json,
    render_ads_report_markdown,
)

ProgressCallback = Callable[[str], None]


@dataclass
class AdsAuditOutcome:
    report: AdsReport
    report_md_path: Path
    report_json_path: Path


@dataclass
class AdsPlanOutcome:
    report: AdsReport
    plan: AdsActionPlan
    report_md_path: Path
    plan_json_path: Path


def _noop(_: str) -> None:
    return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _build_report(provider: AdsProvider, account_id: str, since_days: int, policy: AdsSafetyPolicy):
    policy.require_account_allowed(account_id)
    policy.require_capability("ads_read")

    profile = provider.probe(account_id)
    insights = provider.fetch_insights(account_id, since_days=since_days)
    findings = analyze_ads(profile, insights, policy=policy)
    score = compute_account_health_score(findings)

    p0 = sum(1 for f in findings if f.severity == "P0")
    p1 = sum(1 for f in findings if f.severity == "P1")
    summary_parts = [f"帳戶 {account_id} 的廣告健康分數為 {score:.0f}/100。"]
    if p0:
        summary_parts.append(f"有 {p0} 個阻斷級（P0）問題需要立即處理。")
    if p1:
        summary_parts.append(f"另有 {p1} 個高影響（P1）問題建議優先處理。")
    summary_parts.append(f"本次共產出 {len(findings)} 項發現。")

    report = AdsReport(
        report_id=f"ads-report-{account_id}",
        generated_at=_now_iso(),
        account=profile,
        account_health_score=score,
        executive_summary=" ".join(summary_parts),
        findings=findings,
        observation_days=since_days,
    )
    return report, insights


def run_ads_audit(
    provider: AdsProvider,
    *,
    account_id: str,
    since_days: int,
    out_dir: str,
    policy: AdsSafetyPolicy,
    on_progress: ProgressCallback = _noop,
) -> AdsAuditOutcome:
    on_progress("讀取廣告帳戶資訊與成效資料")
    report, _ = _build_report(provider, account_id, since_days, policy)

    on_progress("整理診斷報告")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / "ads-report.md"
    json_path = out_path / "ads-report.json"
    md_path.write_text(render_ads_report_markdown(report), encoding="utf-8")
    json_path.write_text(render_ads_report_json(report), encoding="utf-8")

    return AdsAuditOutcome(report=report, report_md_path=md_path, report_json_path=json_path)


def run_ads_plan(
    provider: AdsProvider,
    *,
    account_id: str,
    since_days: int,
    out_dir: str,
    policy: AdsSafetyPolicy,
    on_progress: ProgressCallback = _noop,
) -> AdsPlanOutcome:
    on_progress("讀取廣告帳戶資訊與成效資料")
    report, insights = _build_report(provider, account_id, since_days, policy)

    on_progress("產出 dry-run 行動計畫（不會實際修改廣告帳戶）")
    plan = build_action_plan(
        report.account,
        report.findings,
        insights,
        policy=policy,
        plan_id=f"ads-plan-{account_id}",
        generated_at=_now_iso(),
    )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / "ads-report.md"
    plan_path = out_path / "action-plan.json"
    md_path.write_text(render_ads_report_markdown(report), encoding="utf-8")
    plan_path.write_text(render_action_plan_json(plan), encoding="utf-8")

    return AdsPlanOutcome(
        report=report, plan=plan, report_md_path=md_path, plan_json_path=plan_path
    )
