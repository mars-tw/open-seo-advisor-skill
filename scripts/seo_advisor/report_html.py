"""Report 的 HTML 可視化渲染：在既有 Markdown/JSON 基礎上新增圖表。

跟 `report.py::render_markdown()`/`render_json()` 一樣是純函式，只吃
`Report` 物件，不需要知道爬蟲/連線細節，維持三種渲染函式介面一致。

技術選型（NORA 複審確認）：
- 圖表用純 SVG（Python 手刻座標轉換 + f-string），不引入 matplotlib
  這類重量級繪圖套件——符合專案既有的精簡依賴慣例（`pyproject.toml`
  只有 7 個核心依賴，沒有任何繪圖套件）。
- 這輪只做 HTML，不做 PDF；HTML 內建 `@media print` CSS，使用者可透過
  瀏覽器「列印為 PDF」取得 PDF 版本，不需要額外引入 weasyprint/
  playwright 之類的依賴。
- 所有使用者/爬取來源的文字內容（title、recommendation、URL、evidence
  等）一律 `html.escape()`，避免報告中出現的頁面內容/使用者輸入被解讀
  成 HTML/JS（例如頁面標題剛好含有 `<script>`）。
"""

from __future__ import annotations

from html import escape as _esc

from seo_advisor.models import Finding, Report
from seo_advisor.scoring import group_by_severity

_SEVERITY_ORDER = ["P0", "P1", "P2", "P3"]
_SEVERITY_COLORS = {"P0": "#b91c1c", "P1": "#c2410c", "P2": "#a16207", "P3": "#374151"}
_MAX_AFFECTED_URLS_SHOWN = 10
_MAX_FINDINGS_IN_FULL_LIST = 200


def render_html(report: Report) -> str:
    grouped = group_by_severity(report.findings)
    severity_counts = {sev: len(grouped[sev]) for sev in _SEVERITY_ORDER}

    sections = [
        _render_header(report),
        _render_executive_summary(report),
        _render_kpi_cards(report, severity_counts),
        _render_impact_effort_chart(report.findings),
        _render_status_distribution_chart(report.scan_stats),
        _render_hreflang_matrix(report.scan_stats),
        _render_top_findings_table(report),
        _render_full_findings(grouped),
        _render_appendix(report),
    ]

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SEO 健檢報告：{_esc(report.target.identifier)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="container">
{"".join(sections)}
</div>
</body>
</html>
"""


def _render_header(report: Report) -> str:
    return f"""
<header class="report-header">
  <h1>SEO 健檢報告：{_esc(report.target.identifier)}</h1>
  <dl class="meta-list">
    <dt>報告 ID</dt><dd><code>{_esc(report.report_id)}</code></dd>
    <dt>產生時間</dt><dd>{_esc(report.generated_at)}</dd>
    <dt>模式</dt><dd>{_esc(report.mode.value)}</dd>
    <dt>來源類型</dt><dd>{_esc(report.target.source_type)}</dd>
  </dl>
</header>
"""


def _render_executive_summary(report: Report) -> str:
    notes_html = ""
    if report.coverage_notes:
        items = "".join(f"<li>{_esc(note)}</li>" for note in report.coverage_notes)
        notes_html = f'<h3>檢查範圍說明</h3><ul class="coverage-notes">{items}</ul>'
    return f"""
<section class="card">
  <h2>Executive Summary</h2>
  <p>{_esc(report.executive_summary)}</p>
  {notes_html}
</section>
"""


def _render_kpi_cards(report: Report, severity_counts: dict[str, int]) -> str:
    severity_cards = "".join(
        f'<div class="kpi-card severity-{sev.lower()}"><span class="kpi-value">{count}</span>'
        f'<span class="kpi-label">{sev}</span></div>'
        for sev, count in severity_counts.items()
    )
    return f"""
<section class="kpi-grid">
  <div class="kpi-card"><span class="kpi-value">{report.site_health_score:.0f}</span><span class="kpi-label">健康分數 / 100</span></div>
  <div class="kpi-card"><span class="kpi-value">{len(report.findings)}</span><span class="kpi-label">總發現數</span></div>
  {severity_cards}
</section>
"""


def _render_impact_effort_chart(findings: list[Finding]) -> str:
    if not findings:
        return _empty_section("Impact x Effort Matrix", "本次掃描沒有任何發現，無法產生矩陣圖。")

    width, height, margin = 480, 480, 40
    plot_size = width - 2 * margin

    def _coord(value: int) -> float:
        # impact/effort 定義域是 1-5（見 models.py Finding），映射到繪圖區。
        return margin + (value - 1) / 4 * plot_size

    points = []
    for finding in findings:
        x = _coord(finding.effort)
        y = height - _coord(finding.impact)  # SVG y 軸向下，翻轉讓 impact 高在上方
        color = _SEVERITY_COLORS.get(finding.severity.value, "#374151")
        title = _esc(f"{finding.title}（impact={finding.impact}, effort={finding.effort}）")
        points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}" fill-opacity="0.75"><title>{title}</title></circle>')

    axis = f"""
<line x1="{margin}" y1="{height - margin}" x2="{width - margin}" y2="{height - margin}" stroke="#9ca3af"/>
<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{height - margin}" stroke="#9ca3af"/>
<text x="{width / 2}" y="{height - 5}" class="axis-label" text-anchor="middle">Effort（越右越花力氣）</text>
<text x="12" y="{height / 2}" class="axis-label" text-anchor="middle" transform="rotate(-90, 12, {height / 2})">Impact（越上影響越大）</text>
"""
    legend = "".join(
        f'<span class="legend-item"><span class="legend-swatch" style="background:{color}"></span>{sev}</span>'
        for sev, color in _SEVERITY_COLORS.items()
    )

    svg = f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Impact x Effort matrix">{axis}{"".join(points)}</svg>'
    return f"""
<section class="card">
  <h2>Impact x Effort Matrix</h2>
  <p class="hint">右上角（高 impact、低 effort）是優先處理的甜蜜點；每個點代表一個發現，滑鼠移過可看標題。</p>
  <div class="chart">{svg}</div>
  <div class="legend">{legend}</div>
</section>
"""


def _render_status_distribution_chart(scan_stats: dict) -> str:
    distribution = scan_stats.get("status_code_distribution")
    if not distribution or not isinstance(distribution, dict):
        return _empty_section("URL 狀態分布", "此版本報告未提供狀態碼分布資料。")

    order = ["2xx", "3xx", "4xx", "5xx", "0"]
    labels = {"2xx": "2xx 成功", "3xx": "3xx 重導", "4xx": "4xx 錯誤", "5xx": "5xx 錯誤", "0": "連線失敗"}
    colors = {"2xx": "#15803d", "3xx": "#a16207", "4xx": "#c2410c", "5xx": "#b91c1c", "0": "#374151"}
    counts = [(key, int(distribution.get(key, 0) or 0)) for key in order]
    total = sum(count for _, count in counts) or 1

    width, bar_height, gap, margin = 480, 28, 12, 100
    bars = []
    for index, (key, count) in enumerate(counts):
        y = index * (bar_height + gap)
        bar_width = (count / total) * (width - margin - 20)
        bars.append(
            f'<text x="0" y="{y + bar_height / 2 + 4}" class="bar-label">{_esc(labels[key])}</text>'
            f'<rect x="{margin}" y="{y}" width="{max(bar_width, 1) if count else 0}" height="{bar_height}" '
            f'fill="{colors[key]}" fill-opacity="0.85"/>'
            f'<text x="{margin + bar_width + 6}" y="{y + bar_height / 2 + 4}" class="bar-count">{count}</text>'
        )
    height = len(counts) * (bar_height + gap)
    svg = f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="URL status code distribution">{"".join(bars)}</svg>'
    return f"""
<section class="card">
  <h2>URL 狀態分布</h2>
  <div class="chart">{svg}</div>
</section>
"""


def _render_hreflang_matrix(scan_stats: dict) -> str:
    matrix = scan_stats.get("hreflang_matrix")
    if not matrix or not isinstance(matrix, dict):
        return ""

    all_codes: list[str] = []
    for declarations in matrix.values():
        for code in declarations:
            if code not in all_codes:
                all_codes.append(code)
    all_codes.sort(key=lambda c: (c == "x-default", c))

    header = "".join(f"<th>{_esc(code)}</th>" for code in all_codes)
    rows = []
    for url, declarations in matrix.items():
        cells = "".join(
            f'<td class="hreflang-yes" title="{_esc(declarations[code])}">✓</td>' if code in declarations else '<td class="hreflang-no">—</td>'
            for code in all_codes
        )
        rows.append(f"<tr><td class=\"url-cell\">{_esc(url)}</td>{cells}</tr>")

    return f"""
<section class="card">
  <h2>hreflang 矩陣</h2>
  <p class="hint">✓ 代表該頁面宣告了對應語言的 hreflang，滑鼠移過可看目標網址。</p>
  <div class="table-scroll">
    <table class="hreflang-table">
      <thead><tr><th>頁面</th>{header}</tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def _render_top_findings_table(report: Report) -> str:
    lookup = {f.id: f for f in report.findings}
    rows = []
    for finding_id in report.top_findings:
        finding = lookup.get(finding_id)
        if finding is None:
            continue
        rows.append(
            "<tr>"
            f'<td><span class="badge severity-{finding.severity.value.lower()}">{finding.severity.value}</span></td>'
            f"<td>{_esc(finding.title)}</td>"
            f"<td>{_esc(finding.category)}</td>"
            f"<td>{finding.impact}</td>"
            f"<td>{finding.effort}</td>"
            f"<td>{finding.priority_score:.2f}</td>"
            f"<td>{len(finding.affected_urls)}</td>"
            "</tr>"
        )
    if not rows:
        return _empty_section("Top Findings", "沒有發現需要優先處理的項目。")

    return f"""
<section class="card">
  <h2>Top Findings</h2>
  <div class="table-scroll">
    <table>
      <thead><tr><th>等級</th><th>標題</th><th>分類</th><th>Impact</th><th>Effort</th><th>Priority</th><th>受影響 URL 數</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</section>
"""


def _render_full_findings(grouped: dict[str, list[Finding]]) -> str:
    blocks = []
    shown = 0
    truncated = False
    for severity in _SEVERITY_ORDER:
        items = grouped[severity]
        blocks.append(f'<h3 class="severity-heading severity-{severity.lower()}">{severity}（{len(items)} 項）</h3>')
        if not items:
            blocks.append("<p class=\"hint\">（無）</p>")
            continue
        for finding in items:
            if shown >= _MAX_FINDINGS_IN_FULL_LIST:
                truncated = True
                break
            blocks.append(_render_finding_card(finding))
            shown += 1
        if shown >= _MAX_FINDINGS_IN_FULL_LIST:
            truncated = True

    note = ""
    if truncated:
        note = f'<p class="hint">為避免報告過長，完整清單只顯示前 {_MAX_FINDINGS_IN_FULL_LIST} 項，完整內容請見 report.json。</p>'

    return f"""
<section class="card">
  <h2>完整發現清單（依優先順序分組）</h2>
  {note}
  {"".join(blocks)}
</section>
"""


def _render_finding_card(finding: Finding) -> str:
    urls_html = ""
    if finding.affected_urls:
        shown_urls = finding.affected_urls[:_MAX_AFFECTED_URLS_SHOWN]
        items = "".join(f"<li>{_esc(url)}</li>" for url in shown_urls)
        more = ""
        if len(finding.affected_urls) > _MAX_AFFECTED_URLS_SHOWN:
            more = f'<li class="hint">（等共 {len(finding.affected_urls)} 個）</li>'
        urls_html = f'<details><summary>受影響 URL（{len(finding.affected_urls)}）</summary><ul>{items}{more}</ul></details>'

    validation_html = ""
    if finding.validation:
        items = "".join(f"<li>{_esc(step)}</li>" for step in finding.validation)
        validation_html = f"<p><strong>驗證方式：</strong></p><ul>{items}</ul>"

    return f"""
<article class="finding-card">
  <h4>{_esc(finding.title)} <code>{_esc(finding.id)}</code></h4>
  <p class="finding-meta">分類：{_esc(finding.category)} ｜ Impact: {finding.impact} ｜ Effort: {finding.effort} ｜ Confidence: {finding.confidence:.2f}</p>
  <p>{_esc(finding.recommendation)}</p>
  {urls_html}
  {validation_html}
</article>
"""


def _render_appendix(report: Report) -> str:
    stats_items = "".join(
        f"<li><strong>{_esc(str(key))}</strong>: {_esc(_stringify_stat_value(value))}</li>"
        for key, value in report.scan_stats.items()
        if key not in ("hreflang_matrix",)  # 矩陣已經有專屬圖表區塊，這裡不重複列出整份原始資料
    )
    if not stats_items:
        return ""
    return f"""
<section class="card appendix">
  <h2>掃描統計</h2>
  <ul>{stats_items}</ul>
</section>
"""


def _stringify_stat_value(value: object) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def _empty_section(title: str, message: str) -> str:
    return f"""
<section class="card">
  <h2>{_esc(title)}</h2>
  <p class="hint">{_esc(message)}</p>
</section>
"""


_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", "PingFang TC", "Microsoft JhengHei", sans-serif; margin: 0; background: #f8fafc; color: #1f2937; }
.container { max-width: 960px; margin: 0 auto; padding: 24px 16px 64px; }
.report-header h1 { font-size: 1.5rem; margin-bottom: 8px; }
.meta-list { display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 0.9rem; color: #4b5563; }
.meta-list dt { font-weight: 600; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-top: 16px; }
.card h2 { margin-top: 0; font-size: 1.15rem; }
.hint { color: #6b7280; font-size: 0.85rem; }
.kpi-grid { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; }
.kpi-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 16px; text-align: center; min-width: 110px; flex: 1; }
.kpi-value { display: block; font-size: 1.6rem; font-weight: 700; }
.kpi-label { display: block; font-size: 0.8rem; color: #6b7280; }
.severity-p0 .kpi-value, .severity-heading.severity-p0 { color: #b91c1c; }
.severity-p1 .kpi-value, .severity-heading.severity-p1 { color: #c2410c; }
.severity-p2 .kpi-value, .severity-heading.severity-p2 { color: #a16207; }
.severity-p3 .kpi-value, .severity-heading.severity-p3 { color: #374151; }
.chart { width: 100%; max-width: 520px; }
.chart svg { width: 100%; height: auto; }
.axis-label { font-size: 11px; fill: #6b7280; }
.bar-label { font-size: 11px; fill: #374151; }
.bar-count { font-size: 11px; fill: #374151; }
.legend { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; font-size: 0.8rem; }
.legend-item { display: inline-flex; align-items: center; gap: 4px; }
.legend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
table { border-collapse: collapse; width: 100%; font-size: 0.85rem; }
th, td { border-bottom: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; }
.table-scroll { overflow-x: auto; }
.badge { padding: 2px 8px; border-radius: 999px; color: #fff; font-size: 0.75rem; font-weight: 600; }
.badge.severity-p0 { background: #b91c1c; }
.badge.severity-p1 { background: #c2410c; }
.badge.severity-p2 { background: #a16207; }
.badge.severity-p3 { background: #374151; }
.finding-card { border-top: 1px solid #e5e7eb; padding-top: 12px; margin-top: 12px; }
.finding-card h4 { margin: 0 0 4px; font-size: 1rem; }
.finding-meta { color: #6b7280; font-size: 0.8rem; }
.hreflang-table td, .hreflang-table th { text-align: center; }
.hreflang-table .url-cell { text-align: left; max-width: 320px; overflow-wrap: anywhere; }
.hreflang-yes { color: #15803d; font-weight: 700; }
.hreflang-no { color: #d1d5db; }
.coverage-notes { font-size: 0.85rem; color: #4b5563; }
.appendix ul { font-size: 0.85rem; color: #4b5563; }
@media print {
  body { background: #fff; }
  .card { break-inside: avoid; border: 1px solid #d1d5db; }
}
"""
