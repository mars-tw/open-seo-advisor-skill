"""redirect chain 修復建議：只產出 plan_only=True 的建議方案，不自動寫入
任何檔案。

對應 analyzers/technical.py 的 `_check_redirect_chains`（category:
indexability，id 前綴 redirect_chain）產出的 Finding。

刻意不做自動修復：修復多層重導鏈實務上代表要修改伺服器端設定（Apache
.htaccess、Nginx conf、應用程式路由邏輯），這些檔案格式差異很大，且往往
含有其他不相關的邏輯（.htaccess 可能同時管理快取規則、URL rewrite），
跟 Engineer Mode 其他 fixer「整份靜態 SEO 資產讀寫」的安全模型完全不同
——貿然自動修改可能造成全站 500 或路由錯亂，且正確修法需要知道業務意圖
（保留舊 URL？合併規則？避免循環？），crawler 單靠爬取結果無法安全判斷。
因此這裡只產出「建議的重導規則文字」，交由使用者自行判斷並套用到自己的
伺服器設定。
"""

from __future__ import annotations

from seo_advisor.fixers.models import NotFixableError, PatchPlan
from seo_advisor.models import Finding


def can_fix(finding: Finding) -> bool:
    return "REDIRECT_CHAIN" in finding.id


def plan_fix(finding: Finding) -> PatchPlan:
    """產出重導鏈的建議方案（plan_only=True，不會實際寫入任何檔案）。"""
    example_chain = finding.evidence.get("example_chain") if finding.evidence else None
    if not isinstance(example_chain, list) or len(example_chain) < 2:
        raise NotFixableError(
            f"{finding.id} 沒有足夠的重導鏈資訊（evidence.example_chain），無法產出建議。"
        )

    origin, *_middle, destination = example_chain
    suggested_actions = [
        f"確認完整重導鏈：{' -> '.join(example_chain)}",
        f"將起點直接導向最終目標，避免中間跳轉：{origin} -> {destination}",
        "Apache (.htaccess) 範例：Redirect 301 " + origin + " " + destination,
        "Nginx 範例：在對應 location block 加入 return 301 " + destination + ";",
        "套用後請重新執行本次掃描，確認該路徑只剩一次跳轉（或直接 200）。",
    ]

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="redirect_chain",
        risk_level="medium",
        targets=[],
        summary=(
            f"發現多層重導鏈（{' -> '.join(example_chain)}），建議直接將起點導向最終"
            "目標。這類修改需要調整伺服器端設定（.htaccess/nginx conf/應用程式路由），"
            "超出 Engineer Mode 可以安全自動寫入的範圍，因此只產出建議，不會自動套用。"
        ),
        validation_steps=["套用建議後重新執行掃描，確認重導鏈已縮短為單一 301"],
        warnings=[
            "這是建議方案，不是可自動套用的修復計畫；請自行確認伺服器設定格式與"
            "現有規則是否衝突後再套用。",
        ],
        plan_only=True,
        suggested_actions=suggested_actions,
    )
