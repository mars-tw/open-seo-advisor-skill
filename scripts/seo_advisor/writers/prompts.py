"""Content Writer Mode 各階段的 prompt 產生器。

核心 system prompt 精神來自 docs/content_writer_guide.md 與
prompts/content_writer.md，這裡把它拆成 brief/outline/draft/qa 四個
階段各自的 system prompt 與 user prompt 組裝邏輯。
"""

from __future__ import annotations

from seo_advisor.writers.models import ContentBrief, ContentOutline, ContentRequest

_CORE_PRINCIPLES = """\
核心原則：
1. 先判斷搜尋意圖，並讓內容結構對應該意圖。
2. 內容必須回答讀者真正要完成的任務，不為字數而寫。
3. 展示 E-E-A-T：第一手經驗、專業解釋、可信來源、真實資訊。
4. Trust 優先：不得捏造數據、案例、引用或專業建議；不確定處請用
   「[需要查證: 具體說明]」標示，不要假裝知道。
5. YMYL 主題（健康/財務/法律/人身安全）必須標示需要合格專家審查。
6. 避免低品質 AI 內容特徵：空泛開場、重複、關鍵字堆砌、無來源統計。
7. 結構清楚：單一 H1，H2/H3 對應子意圖，適時使用表格/步驟/FAQ。
8. 內部連結需有語境與目的。
9. 結構化資料只標記頁面實際存在的內容。
10. 多語言內容需在地化，不得逐字直譯。
"""


def brief_system_prompt() -> str:
    return (
        "你是資深 SEO 內容策略顧問，任務是為一篇即將撰寫的文章產出內容簡報"
        "（content brief），不是寫文章本體。\n\n" + _CORE_PRINCIPLES
    )


def brief_user_prompt(request: ContentRequest) -> str:
    lines = [
        f"主題：{request.topic}",
        f"語言／地區：{request.lang}" + (f"（{request.locale}）" if request.locale else ""),
    ]
    if request.audience:
        lines.append(f"目標受眾：{request.audience}")
    if request.industry:
        lines.append(f"產業：{request.industry}")
    if request.intent:
        lines.append(f"預期搜尋意圖：{request.intent.value}")
    if request.brand_context:
        lines.append(f"品牌/產品背景：{request.brand_context}")
    if request.source_notes:
        lines.append(f"可參考的既有資料：{request.source_notes}")
    lines.append(
        "\n請產出：主要搜尋意圖、次要意圖、讀者想完成的具體任務清單、"
        "必須回答的關鍵問題、內容缺口、E-E-A-T 需要補強的地方、"
        "是否屬於 YMYL 主題、有哪些事實需要查證。"
    )
    return "\n".join(lines)


def outline_system_prompt() -> str:
    return (
        "你是資深 SEO 內容編輯，根據提供的內容簡報，產出文章大綱與 SEO 中繼資料"
        "建議，不需要撰寫正文內容。\n\n" + _CORE_PRINCIPLES
    )


def outline_user_prompt(request: ContentRequest, brief: ContentBrief) -> str:
    lines = [
        f"主題：{request.topic}",
        f"主要搜尋意圖：{brief.primary_intent.value}",
        f"讀者任務：{'; '.join(brief.reader_tasks) or '（無）'}",
        f"必須回答的問題：{'; '.join(brief.must_cover_questions) or '（無）'}",
    ]
    if request.internal_links:
        lines.append(f"可用的內部連結：{'; '.join(request.internal_links)}")
    lines.append(
        "\n請產出：H1/H2/H3 大綱結構（每個標題附上這段要達成的目的）、"
        "3-5 個 title 選項、2-3 個 meta description 選項、"
        "建議使用的結構化資料類型、內部連結安排建議。"
    )
    return "\n".join(lines)


def draft_system_prompt() -> str:
    return (
        "你是資深 SEO 內容編輯，根據提供的內容簡報與大綱，撰寫完整的文章草稿"
        "（Markdown 格式）。\n\n" + _CORE_PRINCIPLES
    )


def draft_user_prompt(request: ContentRequest, brief: ContentBrief, outline: ContentOutline) -> str:
    section_lines = [f"- {s.heading}（{s.goal}）" if s.goal else f"- {s.heading}" for s in outline.sections]
    lines = [
        f"主題：{request.topic}",
        f"語言：{request.lang}",
        "大綱：",
        *section_lines,
    ]
    if brief.is_ymyl:
        lines.append("\n注意：這是 YMYL 主題，請在文末加上需要專家審核的提醒。")
    lines.append("\n請直接輸出完整的 Markdown 文章草稿。")
    return "\n".join(lines)


def qa_system_prompt() -> str:
    return (
        "你是嚴格的 SEO 編輯審稿人，任務是對照 10 條核心寫作原則檢查草稿，"
        "找出真正的問題，而不是照本宣科打高分。\n\n" + _CORE_PRINCIPLES
    )


def qa_user_prompt(request: ContentRequest, draft_markdown: str) -> str:
    return (
        f"主題：{request.topic}\n\n"
        f"草稿內容：\n{draft_markdown}\n\n"
        "請評估這份草稿是否符合 10 條核心原則，特別留意：搜尋意圖對齊、"
        "是否有空泛灌水、E-E-A-T 訊號是否充分、是否有疑似捏造的內容、"
        "結構是否清楚。給出 0-100 的品質分數與具體問題清單。"
    )
