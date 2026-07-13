"""hreflang 語言對照表（language map）的資料模型與驗證。

跟 v0.2.6 `fixers/hreflang.py`（plan_only 建議）的差異：那裡是「掃描發現
hreflang 問題 → crawler 無法安全推斷語言/網址對應關係 → 只給文字建議」；
這裡是「使用者主動提供完整、權威的語言對照表 → 直接產生 hreflang 標記」。
兩者互補，不衝突：語言對照表是業務層面的資訊，crawler 自己爬不出來，
必須由使用者明確輸入，一旦輸入完整就不再需要靠猜測，可以安全地自動產生。

一份語言對照表由多個「cluster」組成：一個 cluster 代表「同一個頁面的所有
語言版本」，例如首頁的 zh-TW/en/x-default 三個版本是一個 cluster，關於我們
頁面的三個語言版本是另一個 cluster。同一個 cluster 內的所有語言版本互相
建立 hreflang alternate 關係。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

_LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
_X_DEFAULT = "x-default"


class InvalidLanguageMapError(ValueError):
    """語言對照表格式或內容不合法時拋出。"""


@dataclass(frozen=True)
class HreflangCluster:
    """一組互相參照的語言版本頁面。

    alternates：{語言代碼: 公開網址}，用來產生 hreflang 標籤的 href。
    targets：{語言代碼: 本地/connector 相對路徑}，HTML generator 要修改
        哪個檔案；可省略某個語言代碼的 target（那個語言版本只出現在
        其他頁面的 hreflang 宣告裡，但這次不會去改它自己的檔案）。
    """

    cluster_id: str
    alternates: dict[str, str]
    targets: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HreflangMap:
    clusters: list[HreflangCluster]


def _validate_language_code(code: str, *, context: str) -> None:
    if code == _X_DEFAULT:
        return
    if not _LANGUAGE_CODE_PATTERN.match(code):
        raise InvalidLanguageMapError(
            f"{context}：語言代碼 {code!r} 格式不正確，必須是 ISO 639-1（如 'en'）、"
            f"ISO 639-1-ISO 3166-1（如 'zh-TW'），或 {_X_DEFAULT!r}。"
        )


def _normalized_url_key(url: str) -> str:
    """把 URL 正規化成用來偵測「同一個網址」的比較鍵：host 轉小寫、去掉
    結尾的點（DNS 根點，`example.com.` 與 `example.com` 是同一台主機）。
    只用來偵測 language map 內部的重複宣告，不用於實際輸出——輸出一律
    保留使用者原始輸入的字串。
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return f"{parsed.scheme}://{host}:{parsed.port or ''}{parsed.path}?{parsed.query}"


def _validate_alternate_url(url: str, *, context: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidLanguageMapError(f"{context}：alternate 網址必須是 http(s)，收到 {url!r}。")
    if not parsed.hostname:
        raise InvalidLanguageMapError(f"{context}：alternate 網址缺少主機名稱，收到 {url!r}。")
    if parsed.username or parsed.password:
        raise InvalidLanguageMapError(f"{context}：alternate 網址不應包含帳號密碼資訊，收到 {url!r}。")
    if parsed.fragment:
        raise InvalidLanguageMapError(f"{context}：alternate 網址不應包含 fragment，收到 {url!r}。")
    try:
        decoded = unquote(parsed.path, errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidLanguageMapError(f"{context}：alternate 網址路徑編碼不正確，收到 {url!r}。") from exc
    segments = [seg for seg in decoded.split("/") if seg != "."]
    if any(seg == ".." for seg in segments):
        raise InvalidLanguageMapError(f"{context}：alternate 網址不得包含路徑穿越（..），收到 {url!r}。")


def parse_language_map(raw: dict) -> HreflangMap:
    """解析並驗證使用者提供的語言對照表（已載入的 JSON dict）。

    格式：
        {
          "clusters": [
            {
              "id": "home",
              "alternates": {"zh-TW": "https://example.com/zh/", "en": "https://example.com/en/"},
              "targets": {"zh-TW": "zh/index.html", "en": "en/index.html"}
            }
          ]
        }
    """
    if not isinstance(raw, dict) or "clusters" not in raw:
        raise InvalidLanguageMapError("語言對照表必須是包含 'clusters' 陣列的物件。")

    raw_clusters = raw["clusters"]
    if not isinstance(raw_clusters, list) or not raw_clusters:
        raise InvalidLanguageMapError("'clusters' 必須是至少包含一筆資料的陣列。")

    clusters: list[HreflangCluster] = []
    seen_cluster_ids: set[str] = set()
    seen_urls: dict[str, str] = {}  # 正規化後的 url key -> 所屬 cluster_id，偵測跨 cluster 重複

    for index, raw_cluster in enumerate(raw_clusters):
        context = f"clusters[{index}]"
        if not isinstance(raw_cluster, dict):
            raise InvalidLanguageMapError(f"{context}：必須是物件。")

        cluster_id = raw_cluster.get("id")
        if not cluster_id or not isinstance(cluster_id, str):
            raise InvalidLanguageMapError(f"{context}：缺少非空字串的 'id'。")
        if cluster_id in seen_cluster_ids:
            raise InvalidLanguageMapError(f"{context}：cluster id {cluster_id!r} 重複出現。")
        seen_cluster_ids.add(cluster_id)

        alternates = raw_cluster.get("alternates")
        if not isinstance(alternates, dict) or len(alternates) < 2:
            raise InvalidLanguageMapError(
                f"{context}（id={cluster_id!r}）：'alternates' 必須是至少包含兩個語言版本的物件"
                "（hreflang 的意義是「這幾個語言版本互相對應」，只有一個版本沒有意義）。"
            )

        normalized_alternates: dict[str, str] = {}
        for code, url in alternates.items():
            if not isinstance(code, str) or not isinstance(url, str):
                raise InvalidLanguageMapError(f"{context}（id={cluster_id!r}）：alternates 的鍵值必須都是字串。")
            _validate_language_code(code, context=f"{context}（id={cluster_id!r}）")
            _validate_alternate_url(url, context=f"{context}（id={cluster_id!r}）")
            normalized_alternates[code] = url

            url_key = _normalized_url_key(url)
            if url_key in seen_urls and seen_urls[url_key] != cluster_id:
                raise InvalidLanguageMapError(
                    f"{context}（id={cluster_id!r}）：網址 {url!r} 同時出現在 cluster "
                    f"{seen_urls[url_key]!r} 與 {cluster_id!r}，一個網址只能屬於一組 hreflang 對照關係。"
                )
            seen_urls[url_key] = cluster_id

        raw_targets = raw_cluster.get("targets", {})
        if not isinstance(raw_targets, dict):
            raise InvalidLanguageMapError(f"{context}（id={cluster_id!r}）：'targets' 必須是物件。")
        normalized_targets: dict[str, str] = {}
        for code, path in raw_targets.items():
            if code not in normalized_alternates:
                raise InvalidLanguageMapError(
                    f"{context}（id={cluster_id!r}）：targets 裡的語言代碼 {code!r} "
                    "沒有出現在 alternates 裡，targets 只能對應已宣告的語言版本。"
                )
            if not isinstance(path, str) or not path:
                raise InvalidLanguageMapError(f"{context}（id={cluster_id!r}）：targets[{code!r}] 必須是非空字串路徑。")
            normalized_targets[code] = path

        clusters.append(
            HreflangCluster(cluster_id=cluster_id, alternates=normalized_alternates, targets=normalized_targets)
        )

    return HreflangMap(clusters=clusters)


def load_language_map(path: str) -> HreflangMap:
    try:
        raw_text = _read_text(path)
    except OSError as exc:
        raise InvalidLanguageMapError(f"無法讀取語言對照表 {path!r}：{exc}") from exc
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InvalidLanguageMapError(f"語言對照表 {path!r} 不是合法的 JSON：{exc}") from exc
    return parse_language_map(raw)


def _read_text(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")


def render_hreflang_tags(alternates: dict[str, str]) -> list[str]:
    """依 language code 穩定排序（非 x-default 依字母排序、x-default 最後）
    產生一組 `<link rel="alternate" hreflang="...">` HTML 字串。
    """
    from xml.sax.saxutils import quoteattr

    non_default = sorted(code for code in alternates if code != _X_DEFAULT)
    ordered_codes = non_default + ([_X_DEFAULT] if _X_DEFAULT in alternates else [])
    return [
        f'<link rel="alternate" hreflang={quoteattr(code)} href={quoteattr(alternates[code])}/>'
        for code in ordered_codes
    ]
