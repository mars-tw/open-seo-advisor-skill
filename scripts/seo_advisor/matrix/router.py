"""NORA 矩陣路由器：角色選擇（select_roles）與安全升級（apply_safety_gate）。

依任務 user_goal 關鍵字 + industry 選出要啟用的角色；任何含 write/deploy/
spend/publish/send 的高風險任務，會把角色升級為需人工審核且只產計畫。
"""

from __future__ import annotations

from collections import Counter

from seo_advisor.matrix.models import AgentRole, TaskRequest, WritePolicy
from seo_advisor.matrix.registry import all_roles

_ALWAYS_ON = "nora"

# 角色 → 觸發關鍵字（中英文）。命中即為該角色加分。
_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "iris": ("seo", "搜尋", "排名", "關鍵字", "網站健檢", "流量", "收錄", "自然搜尋"),
    "maya": (
        "社群", "貼文", "粉專", "instagram", "facebook", "threads", "短影音", "reels",
        "內容行事曆", "內容排程", "貼文排程", "influencer", "kol", "網紅", "youtube", "影音腳本",
    ),
    "jack": ("廣告", "投放", "meta ads", "ads", "roas", "cpa", "受眾", "廣告預算", "retargeting", "再行銷廣告"),
    "pixel": ("圖", "圖片", "素材", "banner", "橫幅", "配圖", "產圖", "creative", "視覺", "影片"),
    "cody": ("銷售頁", "landing", "轉換頁", "招生頁", "產品頁", "sales page", "cro", "轉換率", "a/b", "ab test"),
    "atlas": ("策略", "定位", "市場", "競爭", "競品", "市場調研", "商業模式", "成長", "新品", "上市", "轉型"),
    "grace": ("財務", "成本", "毛利", "損益", "現金流", "預算表", "報價", "收入"),
    "tara": ("客服", "faq", "常見問題", "客訴", "售後", "客服話術", "評論", "口碑", "review"),
    "rina": ("流程", "營運", "效率", "sop", "作業流程", "內部流程"),
    "otto": ("自動化", "串接", "workflow", "zapier", "make", "n8n", "api", "排程", "行銷自動化"),
    "echo": ("新聞稿", "公關", "媒體", "聲明", "公告", "press release"),
    "lex": ("法務", "合約", "條款", "隱私權", "合規", "法律"),
    "doc": ("文件", "知識庫", "手冊", "操作指南", "教材", "documentation"),
    "orion": ("數據", "報表", "儀表板", "dashboard", "kpi", "指標", "成效分析", "ga4", "歸因", "utm"),
    "nova": ("專案", "時程", "里程碑", "進度", "專案管理", "甘特"),
    "vera": ("品質", "審核", "校對", "檢查", "把關"),
    "luna": ("品牌", "語氣", "標語", "品牌故事", "價值主張", "口吻"),
    "rex": ("業務", "開發客戶", "名單", "陌生開發", "開發信", "bd", "聯盟行銷", "affiliate", "推薦計畫"),
    "sophia": ("客戶成功", "續約", "回購", "留存", "滿意度"),
    "mira": ("crm", "客戶分群", "會員", "再行銷", "流失", "email", "edm", "電子報", "名單分群", "lifecycle"),
    "leon": ("產品設計", "頁面設計", "ux", "ui", "版型", "版面"),
    "kai": ("產品經理", "產品規劃", "需求", "roadmap", "功能規劃", "prd"),
    "finn": ("採購", "供應鏈", "庫存", "供應商", "進貨"),
    "hera": ("人資", "招募", "面試", "訓練", "考核", "職缺"),
    "amy": ("行政", "會議紀錄", "行程", "秘書", "庶務", "待辦"),
}

# 行業 → 額外加權的角色（對應規劃書的四個範例情境）。
_INDUSTRY_BOOSTS: dict[str, tuple[str, ...]] = {
    "製造": ("atlas", "nova", "leon", "cody", "jack", "rex"),
    "工業": ("atlas", "nova", "leon", "cody", "jack", "rex"),
    "b2b": ("atlas", "iris", "rex", "cody", "orion"),
    "餐飲": ("iris", "maya", "jack", "pixel", "tara"),
    "餐廳": ("iris", "maya", "jack", "pixel", "tara"),
    "課程": ("atlas", "cody", "jack", "maya", "iris"),
    "教育": ("atlas", "cody", "jack", "maya", "iris"),
    "電商": ("iris", "maya", "jack", "pixel", "cody", "mira"),
}

# 高風險關鍵字：命中就升級為需人工審核 + 只產計畫。
_RISK_KEYWORDS = (
    "write", "deploy", "spend", "publish", "send", "launch", "activate", "apply",
    "寫入", "部署", "花錢", "投放", "發布", "寄送", "寄出", "發送", "上架", "啟用",
    "套用", "調整預算", "動用預算", "直接執行", "正式送出",
)


def _task_text(task: TaskRequest) -> str:
    parts = [
        task.user_goal or "",
        task.industry or "",
        " ".join(f"{k} {v}" for k, v in (task.business_context or {}).items()),
        " ".join(f"{k} {v}" for k, v in (task.constraints or {}).items()),
    ]
    return " ".join(parts).lower()


def select_roles(task: TaskRequest) -> list[str]:
    """選出要啟用的角色 id 清單。NORA 永遠納入且排在最前。"""
    valid_ids = {role.id for role in all_roles()}

    if task.requested_roles:
        requested = [r.strip().lower() for r in task.requested_roles if r.strip()]
        return _dedupe([_ALWAYS_ON, *requested], valid_ids)

    text = _task_text(task)
    scores: Counter[str] = Counter()
    for role_id, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                scores[role_id] += 2

    industry = (task.industry or "").lower()
    for marker, role_ids in _INDUSTRY_BOOSTS.items():
        if marker in text or marker in industry:
            for role_id in role_ids:
                scores[role_id] += 1

    selected = [_ALWAYS_ON]
    if scores:
        selected.extend(role_id for role_id, _ in scores.most_common(6))
    else:
        selected.extend(_default_roles(text))

    return _dedupe(selected, valid_ids)


def _default_roles(text: str) -> list[str]:
    if any(w in text for w in ("內部", "流程", "sop", "效率")):
        return ["atlas", "rina", "otto", "doc"]
    if any(w in text for w in ("新品", "上市", "產品", "launch")):
        return ["atlas", "nova", "leon", "cody"]
    return ["atlas", "nova", "orion"]


def apply_safety_gate(role: AgentRole, task: TaskRequest) -> tuple[bool, WritePolicy]:
    """回傳 (human_review_required, write_policy)。高風險任務一律升級。"""
    risky = any(kw in _task_text(task) for kw in _RISK_KEYWORDS)
    human_review = role.human_review_required or risky
    write_policy = WritePolicy.PLAN_ONLY if risky else role.write_policy
    return human_review, write_policy


def _dedupe(role_ids: list[str], valid_ids: set[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for role_id in role_ids:
        key = role_id.strip().lower()
        if key in valid_ids and key not in seen:
            output.append(key)
            seen.add(key)
    if _ALWAYS_ON in valid_ids and _ALWAYS_ON not in seen:
        output.insert(0, _ALWAYS_ON)
    return output
