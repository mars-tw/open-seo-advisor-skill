"""測試新增的 plan_only fixer：redirect（重導鏈建議）、hreflang（建議）、
cwv（decoding="async" 真修復 + blocking script 建議），以及
PatchPlan.plan_only / PlanOnlyError 的行為。
"""

from __future__ import annotations

import pytest

from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.crawler import CrawlResult
from seo_advisor.fixers import cwv, hreflang, redirect, runner
from seo_advisor.fixers.models import NotFixableError, PatchPlan, PlanOnlyError
from seo_advisor.models import Finding, Mode, SafetyPolicy, Severity


def _finding(finding_id: str, affected_urls=None, evidence=None) -> Finding:
    return Finding(
        id=finding_id,
        title="test finding",
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=Severity.P2,
        impact=3,
        effort=1,
        confidence=0.9,
        affected_urls=affected_urls or [],
        evidence=evidence or {},
        recommendation="test",
        validation=[],
        owner=Mode.ENGINEER,
    )


def _write_connector(root: str) -> LocalArchiveConnector:
    return LocalArchiveConnector(
        root, policy=SafetyPolicy(dry_run=False, allowed_capabilities={"read_urls", "read_files", "write_files"})
    )


# --- PatchPlan.plan_only 模型驗證 ---


class TestPatchPlanOnlyModel:
    def test_plan_only_with_targets_rejected(self):
        with pytest.raises(ValueError, match="targets"):
            PatchPlan(
                plan_id="p1", finding_id="f1", fix_type="redirect_chain", risk_level="medium",
                targets=[{"path": "x.html", "original_content": "a", "fixed_content": "b", "diff_preview": ""}],
                summary="s", plan_only=True, suggested_actions=["do something"],
            )

    def test_plan_only_without_suggested_actions_rejected(self):
        with pytest.raises(ValueError, match="suggested_actions"):
            PatchPlan(
                plan_id="p1", finding_id="f1", fix_type="redirect_chain", risk_level="medium",
                targets=[], summary="s", plan_only=True, suggested_actions=[],
            )

    def test_plan_only_with_no_targets_and_actions_accepted(self):
        plan = PatchPlan(
            plan_id="p1", finding_id="f1", fix_type="redirect_chain", risk_level="medium",
            targets=[], summary="s", plan_only=True, suggested_actions=["do something"],
        )
        assert plan.plan_only is True

    def test_default_plan_only_is_false(self):
        plan = PatchPlan(
            plan_id="p1", finding_id="f1", fix_type="robots_txt", risk_level="low",
            targets=[], summary="s",
        )
        assert plan.plan_only is False


# --- redirect fixer ---


class TestRedirectFixer:
    def test_can_fix_redirect_chain(self):
        finding = _finding("SEO-REDIRECT_CHAIN-001")
        assert redirect.can_fix(finding)

    def test_plan_fix_is_plan_only(self):
        finding = _finding(
            "SEO-REDIRECT_CHAIN-001",
            affected_urls=["https://example.com/old"],
            evidence={"example_chain": ["https://example.com/old", "https://example.com/mid", "https://example.com/new"]},
        )
        plan = redirect.plan_fix(finding)
        assert plan.plan_only is True
        assert plan.targets == []
        assert len(plan.suggested_actions) > 0
        assert "example.com/old" in plan.suggested_actions[0]
        assert "example.com/new" in " ".join(plan.suggested_actions)

    def test_plan_fix_raises_without_chain_evidence(self):
        finding = _finding("SEO-REDIRECT_CHAIN-001", evidence={})
        with pytest.raises(NotFixableError):
            redirect.plan_fix(finding)

    def test_runner_build_plan_routes_to_redirect(self, tmp_path):
        finding = _finding(
            "SEO-REDIRECT_CHAIN-001",
            evidence={"example_chain": ["https://example.com/a", "https://example.com/b", "https://example.com/c"]},
        )
        connector = _write_connector(str(tmp_path))
        plan = runner.build_plan(
            finding, connector=connector, crawl_result=CrawlResult(), seed_url="https://example.com"
        )
        assert plan.plan_only is True
        assert plan.fix_type == "redirect_chain"


# --- hreflang fixer ---


class TestHreflangFixer:
    @pytest.mark.parametrize(
        "finding_id",
        [
            "SEO-HREFLANG_MISSING_SELF_REFERENCE-001",
            "SEO-HREFLANG_DUPLICATE_LANGUAGE-001",
            "SEO-HREFLANG_INVALID_CODE-001",
            "SEO-HREFLANG_NON_RECIPROCAL-001",
            "SEO-HREFLANG_OUT_OF_SCOPE-001",
            "SEO-HREFLANG_MIXED_IMPLEMENTATION-001",
        ],
    )
    def test_can_fix_all_hreflang_findings(self, finding_id):
        finding = _finding(finding_id)
        assert hreflang.can_fix(finding)

    def test_plan_fix_is_plan_only(self):
        finding = _finding("SEO-HREFLANG_MISSING_SELF_REFERENCE-001")
        plan = hreflang.plan_fix(finding)
        assert plan.plan_only is True
        assert plan.targets == []
        assert len(plan.suggested_actions) > 0

    def test_unrelated_finding_not_fixable(self):
        finding = _finding("SEO-ROBOTS_MISSING-001")
        assert not hreflang.can_fix(finding)


# --- cwv fixer ---


class TestCwvDecodingAsyncFixer:
    def test_can_fix_image_missing_dimensions(self):
        finding = _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001")
        assert cwv.can_fix(finding)

    def test_adds_decoding_async_to_img_without_it(self):
        html = '<html><body><img src="a.jpg"></body></html>'
        finding = _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001", affected_urls=["https://example.com/x"])
        plan = cwv.plan_fix(finding, pages={"https://example.com/x": html})
        assert plan.plan_only is False
        assert len(plan.targets) == 1
        assert 'decoding="async"' in plan.targets[0].fixed_content

    def test_does_not_override_existing_decoding_value(self):
        html = '<html><body><img src="a.jpg" decoding="sync"></body></html>'
        finding = _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001", affected_urls=["https://example.com/x"])
        with pytest.raises(NotFixableError):
            cwv.plan_fix(finding, pages={"https://example.com/x": html})

    def test_switches_to_plan_only_when_too_many_images_on_one_page(self):
        """單頁缺 decoding 的 <img> 數量超過門檻時，改為 plan_only 建議，
        避免一次性自動修改產生難以 review 的巨大 diff。"""
        many_images_html = "<html><body>" + "".join(
            f'<img src="{i}.jpg">' for i in range(60)
        ) + "</body></html>"
        finding = _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001", affected_urls=["https://example.com/x"])
        plan = cwv.plan_fix(finding, pages={"https://example.com/x": many_images_html})
        assert plan.plan_only is True
        assert plan.targets == []
        assert any("60" in action for action in plan.suggested_actions)

    def test_raises_when_page_not_found(self):
        finding = _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001", affected_urls=["https://example.com/missing"])
        with pytest.raises(NotFixableError):
            cwv.plan_fix(finding, pages={})


class TestCwvBlockingScriptsSuggestion:
    def test_can_fix_blocking_scripts(self):
        finding = _finding("SEO-BLOCKING_SCRIPTS_HINT-001")
        assert cwv.can_fix(finding)

    def test_plan_fix_is_plan_only(self):
        finding = _finding("SEO-BLOCKING_SCRIPTS_HINT-001")
        plan = cwv.plan_fix(finding)
        assert plan.plan_only is True
        assert plan.targets == []
        assert plan.fix_type == "cwv_blocking_scripts"


# --- apply_plan() 拒絕 plan_only 計畫 ---


class TestApplyPlanRejectsPlanOnly:
    def test_apply_plan_raises_plan_only_error(self, tmp_path):
        connector = _write_connector(str(tmp_path))
        plan = PatchPlan(
            plan_id="p1", finding_id="f1", fix_type="redirect_chain", risk_level="medium",
            targets=[], summary="s", plan_only=True, suggested_actions=["do something"],
        )
        with pytest.raises(PlanOnlyError):
            runner.apply_plan(plan, connector=connector)

    def test_apply_plan_does_not_touch_connector_when_plan_only(self, tmp_path, monkeypatch):
        """plan_only 計畫應該在任何 connector 操作（backup/write_file）之前
        就被拒絕，不應該有副作用。"""
        connector = _write_connector(str(tmp_path))

        called = []
        original_backup = connector.backup

        def _tracking_backup(targets):
            called.append(targets)
            return original_backup(targets)

        monkeypatch.setattr(connector, "backup", _tracking_backup)

        plan = PatchPlan(
            plan_id="p1", finding_id="f1", fix_type="redirect_chain", risk_level="medium",
            targets=[], summary="s", plan_only=True, suggested_actions=["do something"],
        )
        with pytest.raises(PlanOnlyError):
            runner.apply_plan(plan, connector=connector)
        assert called == []


# --- list_fixable_findings 涵蓋新 fixer ---


def test_list_fixable_findings_includes_new_fixers():
    findings = [
        _finding("SEO-REDIRECT_CHAIN-001", evidence={"example_chain": ["a", "b", "c"]}),
        _finding("SEO-HREFLANG_MISSING_SELF_REFERENCE-001"),
        _finding("SEO-IMAGE_MISSING_DIMENSIONS_HINT-001"),
        _finding("SEO-BLOCKING_SCRIPTS_HINT-001"),
        _finding("SEO-H1_MISSING-001"),  # 沒有對應 fixer
    ]
    fixable = runner.list_fixable_findings(findings)
    assert len(fixable) == 4
