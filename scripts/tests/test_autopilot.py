import json

from seo_advisor.autopilot.estimator import build_cost_estimate
from seo_advisor.autopilot.models import (
    AutoTask,
    CostCategory,
    CostEstimateItem,
    EstimateConfidence,
    RiskLevel,
)
from seo_advisor.autopilot.runner import run_autopilot, select_modules
from seo_advisor.autopilot.safety import (
    build_consent_phrase,
    is_auto_executable,
    verify_consent,
)


# --- 自動路由 ---

def test_url_target_selects_consultant():
    modules = select_modules(AutoTask(target="https://example.com"))
    assert "consultant" in modules


def test_ecommerce_goal_selects_ecommerce():
    modules = select_modules(AutoTask(target="幫我優化 amazon listing"))
    assert "ecommerce" in modules


def test_vague_goal_falls_back_to_matrix():
    modules = select_modules(AutoTask(target="我想成長"))
    assert modules  # 至少有東西
    assert "matrix" in modules


def test_bare_domain_treated_as_url():
    # 新手常直接打 example.com（沒有 https://），要能被當網址、跑顧問類模組
    modules = select_modules(AutoTask(target="example.com"))
    assert "consultant" in modules
    modules2 = select_modules(AutoTask(target="www.shop.com.tw"))
    assert "consultant" in modules2


def test_apply_consent_does_not_rerun_analysis(tmp_path):
    from seo_advisor.autopilot.runner import apply_consent, run_autopilot

    preview = run_autopilot(AutoTask(target="example.com", mock=True), out_dir=str(tmp_path), consented=False)
    before = preview.deliverable.module_results
    final = apply_consent(preview, out_dir=str(tmp_path))
    # 同意後用的是同一份分析結果（沒有重跑），只是狀態改為已同意
    assert final.deliverable.consented is True
    assert final.deliverable.module_results == before


# --- 成本明細誠實性 ---

def test_mock_estimate_is_zero_cost():
    est = build_cost_estimate(
        estimate_id="e1", generated_at="2026-07-02T00:00:00Z",
        plan_image_variants=4, mock=True,
    )
    img = next(i for i in est.items if i.module == "image_material")
    assert img.amount_minor_units == 0
    assert "不會真的" in img.unit_notes


def test_real_image_cost_marked_estimated_not_fake_precise():
    est = build_cost_estimate(
        estimate_id="e2", generated_at="2026-07-02T00:00:00Z",
        plan_image_variants=4, mock=False,
    )
    img = next(i for i in est.items if i.module == "image_material")
    # 真實情境無法精確估 → confidence 為 estimated，且列入 unknown
    assert img.confidence == EstimateConfidence.ESTIMATED
    assert est.unknown_cost_items


def test_ad_budget_increase_not_auto_executable():
    est = build_cost_estimate(
        estimate_id="e3", generated_at="2026-07-02T00:00:00Z",
        plan_ad_budget_delta_minor_units=50000, mock=False,
    )
    ad = next(i for i in est.items if i.category == CostCategory.AD_SPEND)
    # 增加預算屬高風險，不可同意後自動執行
    assert ad.execution_allowed_after_consent is False
    assert ad.risk_level == RiskLevel.HIGH


# --- 同意閘門 ---

def test_consent_phrase_with_amount():
    phrase = build_consent_phrase(50000, "TWD")
    assert "APPROVE AUTO EXECUTION" in phrase
    assert "TWD 500" in phrase


def test_verify_consent_exact_match():
    phrase = build_consent_phrase(None, None)
    assert verify_consent("APPROVE AUTO EXECUTION", phrase) is True
    assert verify_consent("approve auto execution", phrase) is True  # 不分大小寫
    assert verify_consent("y", phrase) is False  # 單純 y 不算同意
    assert verify_consent("好", phrase) is False


# --- 安全白名單/黑名單 ---

def _item(reversible=True, risk=RiskLevel.LOW, allowed=True):
    return CostEstimateItem(
        action_id="x", module="m", action_summary="s", category=CostCategory.WRITE,
        risk_level=risk, reversible=reversible, user_facing_explanation="e",
        execution_allowed_after_consent=allowed,
    )


def test_blocklisted_action_never_auto_executes():
    item = _item()
    assert is_auto_executable(item, "delete_data") is False
    assert is_auto_executable(item, "payment") is False
    assert is_auto_executable(item, "publish_content") is False
    assert is_auto_executable(item, "activate_new_ad") is False


def test_allowlisted_reversible_low_risk_executes():
    item = _item(reversible=True, risk=RiskLevel.LOW, allowed=True)
    assert is_auto_executable(item, "generate_local_report") is True


def test_irreversible_never_executes_even_if_allowlisted():
    item = _item(reversible=False)
    assert is_auto_executable(item, "generate_local_report") is False


def test_critical_risk_never_executes():
    item = _item(risk=RiskLevel.CRITICAL)
    assert is_auto_executable(item, "generate_local_report") is False


# --- MVP 安全開關：真實模式成本不得被誤標成 mock ---

def test_real_mode_cost_not_mislabeled_as_mock(tmp_path, monkeypatch):
    """把 MVP force-plan 開關關掉、且 task 非 mock 時，含產圖的成本明細不得
    被標成『示範、不花錢』——這鎖住已修復的 mock=or True bug 不再回歸。
    """
    import seo_advisor.autopilot.runner as runner_mod

    monkeypatch.setattr(runner_mod, "_MVP_FORCE_PLAN_ONLY", False)
    # 用會觸發 image_plan 的目標，讓成本明細裡有產圖項目
    outcome = runner_mod.run_autopilot(
        AutoTask(target="幫我做廣告圖素材", mock=False), out_dir=str(tmp_path)
    )
    image_items = [i for i in outcome.deliverable.cost_estimate.items if i.module == "image_material"]
    if image_items:
        note = image_items[0].unit_notes
        assert "不會真的" not in note  # 真實模式不得標成示範不花錢


# --- 完整流程 ---

def test_run_autopilot_produces_reports(tmp_path):
    outcome = run_autopilot(AutoTask(target="https://example.com", mock=True), out_dir=str(tmp_path))
    assert outcome.beginner_path.exists()
    assert outcome.report_path.exists()
    assert outcome.cost_estimate_path.exists()


def test_run_autopilot_without_consent_does_not_execute_paid(tmp_path):
    outcome = run_autopilot(AutoTask(target="https://example.com", mock=True), out_dir=str(tmp_path), consented=False)
    paid = next((a for a in outcome.deliverable.executed_actions if a.action_id == "paid-actions"), None)
    assert paid is not None
    assert paid.status != "executed"


def test_run_autopilot_json_round_trips(tmp_path):
    outcome = run_autopilot(AutoTask(target="幫我優化電商", mock=True), out_dir=str(tmp_path))
    data = json.loads(outcome.json_path.read_text(encoding="utf-8"))
    assert data["target"] == "幫我優化電商"
