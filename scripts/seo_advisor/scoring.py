"""Finding 排序與 Site Health Score 計算。

規則見 config/scoring.yaml 與 docs/architecture.md：
- 先依 severity（P0 > P1 > P2 > P3）分組
- 同組內依 priority_score = impact * confidence / effort 由高到低排序
- 健康分數扣分會依 category_weights 加權，讓「資安」「索引性」等較關鍵的
  分類問題比同等 severity 的其他分類問題扣更多分。
"""

from __future__ import annotations

import functools
import importlib.resources

import yaml

from seo_advisor.models import Finding, Severity

_SEVERITY_ORDER = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}

_SEVERITY_PENALTY = {
    Severity.P0: 25.0,
    Severity.P1: 10.0,
    Severity.P2: 4.0,
    Severity.P3: 1.0,
}

_DEFAULT_CATEGORY_WEIGHT = 1.0
_CONFIG_ASSET_PACKAGE = "seo_advisor.config_assets"
_SCORING_CONFIG_FILENAME = "scoring.yaml"


@functools.lru_cache(maxsize=1)
def _load_default_category_weights() -> dict[str, float]:
    """讀取隨套件打包的預設 scoring.yaml，取得各分類的扣分權重。

    用 lru_cache 快取，因為這份設定在單次程式執行期間不會改變，
    避免每次計算健康分數都重新讀檔與解析 YAML。
    """
    try:
        traversable = importlib.resources.files(_CONFIG_ASSET_PACKAGE) / _SCORING_CONFIG_FILENAME
        with importlib.resources.as_file(traversable) as path:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        return {}

    weights = data.get("category_weights", {})
    if not isinstance(weights, dict):
        return {}
    return {str(k): float(v) for k, v in weights.items()}


def _category_weight(category: str) -> float:
    return _load_default_category_weights().get(category, _DEFAULT_CATEGORY_WEIGHT)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """依 severity 分組，組內依 priority_score 由高到低排序。"""
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER[f.severity], -f.priority_score),
    )


def top_findings(findings: list[Finding], limit: int = 10) -> list[Finding]:
    return sort_findings(findings)[:limit]


def compute_site_health_score(findings: list[Finding]) -> float:
    """依嚴重度與分類權重加權扣分計算 0-100 的健康分數，下限為 0。

    penalty = base_severity_penalty * confidence * category_weight

    例如同樣是 P1、confidence=1.0 的問題，屬於 security 分類
    （權重 1.3）會比屬於 internal_linking 分類（權重 0.8）扣更多分，
    反映不同分類對整體 SEO 健康的影響程度不同。
    """
    score = 100.0
    for finding in findings:
        base_penalty = _SEVERITY_PENALTY[finding.severity] * finding.confidence
        weighted_penalty = base_penalty * _category_weight(finding.category)
        score -= weighted_penalty
    return max(0.0, round(score, 1))


def group_by_severity(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {level.value: [] for level in Severity}
    for finding in sort_findings(findings):
        grouped[finding.severity.value].append(finding)
    return grouped
