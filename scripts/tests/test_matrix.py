import json

from seo_advisor.matrix.models import TaskRequest, WritePolicy
from seo_advisor.matrix.planner import build_assignments
from seo_advisor.matrix.registry import all_roles, get_role
from seo_advisor.matrix.router import apply_safety_gate, select_roles
from seo_advisor.matrix.runner import run_matrix


# --- registry ---

def test_registry_loads_all_roles():
    roles = all_roles()
    assert len(roles) >= 26
    # 抽查幾個角色職能對齊規劃書
    assert get_role("orion").title == "數據分析師"
    assert get_role("grace").title == "財務分析助理"
    assert get_role("cody").title == "銷售頁專家"
    assert get_role("leon").title == "產品與頁面設計總監"


def test_high_risk_roles_flagged_in_registry():
    assert get_role("jack").human_review_required is True
    assert get_role("lex").human_review_required is True
    assert get_role("grace").human_review_required is True


# --- router role selection ---

def test_nora_always_included():
    task = TaskRequest(user_goal="隨便一個目標")
    assert "nora" in select_roles(task)


def test_seo_goal_selects_iris():
    task = TaskRequest(user_goal="幫我做網站 SEO 健檢，提升搜尋排名")
    assert "iris" in select_roles(task)


def test_ads_goal_selects_jack():
    task = TaskRequest(user_goal="優化我的 Meta 廣告投放，降低 CPA")
    assert "jack" in select_roles(task)


def test_internal_process_goal_selects_ops_roles():
    task = TaskRequest(user_goal="公司內部文件很亂，想建立標準流程 SOP")
    roles = select_roles(task)
    assert "rina" in roles or "doc" in roles


def test_email_goal_selects_mira():
    assert "mira" in select_roles(TaskRequest(user_goal="幫我規劃 Email 電子報分眾與再行銷"))


def test_competitor_analysis_selects_atlas():
    assert "atlas" in select_roles(TaskRequest(user_goal="做競品分析與市場調研"))


def test_content_calendar_selects_maya():
    assert "maya" in select_roles(TaskRequest(user_goal="規劃跨平台內容行事曆與短影音腳本"))


def test_requested_roles_are_honored():
    task = TaskRequest(user_goal="任意", requested_roles=["iris", "maya"])
    roles = select_roles(task)
    assert "iris" in roles and "maya" in roles and "nora" in roles


def test_no_match_falls_back_to_defaults():
    task = TaskRequest(user_goal="asdfqwerty 完全無關的字")
    roles = select_roles(task)
    assert "nora" in roles
    assert len(roles) > 1  # 應該有 fallback 角色


# --- safety gate ---

def test_safety_gate_upgrades_on_risky_task():
    role = get_role("maya")  # 平常不需人工審核
    risky_task = TaskRequest(user_goal="幫我把貼文直接發布到粉專")
    human_review, write_policy = apply_safety_gate(role, risky_task)
    assert human_review is True
    assert write_policy == WritePolicy.PLAN_ONLY


def test_safety_gate_normal_task_keeps_role_default():
    role = get_role("maya")
    normal_task = TaskRequest(user_goal="幫我規劃社群內容主題")
    human_review, _ = apply_safety_gate(role, normal_task)
    assert human_review is False


def test_high_risk_role_always_needs_review():
    role = get_role("jack")
    normal_task = TaskRequest(user_goal="看一下廣告成效")
    human_review, _ = apply_safety_gate(role, normal_task)
    assert human_review is True


# --- planner ---

def test_planner_builds_assignment_per_role():
    task = TaskRequest(task_id="t1", user_goal="SEO 與社群成長")
    role_ids = select_roles(task)
    assignments = build_assignments(task, role_ids)
    assert len(assignments) == len(role_ids)
    assert all(a.task_id == "t1" for a in assignments)


def test_planner_jack_assignment_is_plan_only():
    task = TaskRequest(user_goal="優化廣告投放並調整預算")
    role_ids = select_roles(task)
    assignments = build_assignments(task, role_ids)
    jack = next((a for a in assignments if a.role_id == "jack"), None)
    if jack is not None:
        assert jack.human_review_required is True
        assert jack.inputs["write_policy"] == WritePolicy.PLAN_ONLY.value


# --- full runner (mock) ---

def test_run_matrix_produces_deliverable(tmp_path):
    task = TaskRequest(task_id="demo", user_goal="推廣新產品增加詢價", industry="製造業")
    outcome = run_matrix(task, out_dir=str(tmp_path), provider_name="mock")

    assert outcome.deliverable.selected_roles
    assert outcome.deliverable.integrated_plan
    assert outcome.report_md_path.exists()
    assert outcome.report_json_path.exists()


def test_run_matrix_json_round_trips(tmp_path):
    task = TaskRequest(task_id="demo", user_goal="廣告優化與預算調整")
    outcome = run_matrix(task, out_dir=str(tmp_path), provider_name="mock")
    data = json.loads(outcome.report_json_path.read_text(encoding="utf-8"))
    assert data["task_id"] == "demo"
    # 含廣告預算調整 → 應標記需人工審核
    assert data["human_review_required"] is True


def test_run_matrix_marks_human_review_for_publish_task(tmp_path):
    task = TaskRequest(task_id="pub", user_goal="幫我寫新聞稿並直接發布到媒體")
    outcome = run_matrix(task, out_dir=str(tmp_path), provider_name="mock")
    assert outcome.deliverable.human_review_required is True
