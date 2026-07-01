# Connector 契約規格

## 為什麼需要抽象層

Open SEO Advisor 需要支援多種網站接入方式：純 HTTP 爬取、SSH 遠端伺服器、
本地原始碼包、Git repo、WordPress REST API、Cloudflare API、cPanel。
如果每個 analyzer 都要知道「這次的資料是怎麼來的」，程式碼會迅速變得無法
維護。因此所有接入方式都必須實作同一個 `WebsiteConnector` 介面。

## 介面定義

```python
class WebsiteConnector(Protocol):
    def id(self) -> str:
        """回傳這個 connector 實例的識別字串，例如 'http:example.com'。"""

    def capabilities(self) -> set[str]:
        """回傳這個 connector 支援的能力集合，例如
        {'read_urls'} 或 {'read_urls', 'read_files', 'write_files', 'run_commands'}。
        上層邏輯必須先檢查 capabilities() 再呼叫對應方法。"""

    def probe(self) -> "ConnectorProfile":
        """初次連線時的健康檢查與環境偵測（例如偵測 CMS 類型、伺服器軟體）。"""

    def list_urls(self, seed: str, limit: int) -> list["UrlRecord"]:
        """從 sitemap 或爬取取得 URL 清單。"""

    def fetch_url(self, url: str, render: bool = False) -> "PageSnapshot":
        """取得單一頁面的內容快照，render=True 時使用 headless browser。"""

    def list_files(self, path: str) -> list["FileRecord"]:
        """列出指定路徑下的檔案（需要 'read_files' capability）。"""

    def read_file(self, path: str) -> bytes:
        """讀取單一檔案內容（需要 'read_files' capability）。"""

    def write_file(self, path: str, content: bytes, dry_run: bool = True) -> "PatchResult":
        """寫入檔案（需要 'write_files' capability）。dry_run=True 時只回傳
        預期變更，不實際寫入。"""

    def run_command(self, command: list[str], dry_run: bool = True) -> "CommandResult":
        """執行指定指令（需要 'run_commands' capability），必須走 allowlist。"""

    def get_logs(self, log_type: str, since: str) -> list["LogEntry"]:
        """取得伺服器 log（需要 'read_logs' capability）。"""

    def deploy_patch(self, patch: "PatchPlan", dry_run: bool = True) -> "DeployResult":
        """部署一組修改（需要 'deploy' capability）。"""

    def backup(self, targets: list[str]) -> "BackupResult":
        """在寫入前建立備份。"""

    def close(self) -> None:
        """釋放連線資源（關閉 SSH session、清除暫存檔等）。"""
```

v0.1.0 只要求實作 `id()`、`capabilities()`、`probe()`、`list_urls()`、
`fetch_url()`（`HTTPConnector`），以及額外的 `list_files()` / `read_file()`
（`LocalArchiveConnector`）。其餘方法在 v0.1.0 的 `base.py` 中定義好簽名，
未實作時應丟出 `NotImplementedError` 並附上清楚訊息。

## 已規劃的 Connector 實作

| Connector | 狀態 | Capabilities | 說明 |
|---|---|---|---|
| `HTTPConnector` | v0.1.0 已實作 | `read_urls` | 純公開 HTTP 爬取，任何網站都可用，不需帳密 |
| `LocalArchiveConnector` | v0.1.0 已實作 | `read_urls`, `read_files` | 本地原始碼包（zip/目錄），掃描但不執行任何程式 |
| `SSHConnector` | v0.2.0 規劃 | `read_files`, `read_logs`, 選配 `write_files`/`run_commands` | 需使用者提供 host/key，預設唯讀 |
| `GitRepoConnector` | v0.2.0 規劃 | `read_files`, `write_files`（走 branch+diff） | 產出可直接開 PR 的 patch |
| `WordPressAPIConnector` | v0.2.0 規劃 | `read_urls`, 選配 `write_files`（透過 REST） | 需 Application Password 或 OAuth |
| `CloudflareConnector` | v0.3.0 規劃 | `read_urls`, 選配 `deploy`（redirect/cache rules） | 需 API Token，最小權限範圍 |
| `CPanelConnector` | v0.3.0 規劃 | `read_files`, 選配 `write_files` | 有限度的部署能力 |

## 資安要求（所有 Connector 必須遵守）

1. **預設 read-only、預設 dry-run**：`write_file` / `run_command` /
   `deploy_patch` 的 `dry_run` 參數預設為 `True`。
2. **憑證只存在於記憶體中**：憑證只能從環境變數、OS keychain、secret
   manager 或當下輸入取得，禁止寫死在程式碼、設定檔範例、或落地到報告、
   log、例外訊息中。
3. **Command allowlist**：`run_command` 不得執行任意 shell 字串，必須有
   固定的可執行指令清單（例如 `['wp', 'plugin', 'list']`），拒絕
   shell metacharacter（`;`, `|`, `&&`, backtick 等）注入。
4. **寫入前自動備份**：任何 `write_file` / `deploy_patch` 在
   `dry_run=False` 執行前，應盡可能先呼叫 `backup()`。
5. **對 production 的操作要求二次確認**：由呼叫端（CLI / router）負責在
   偵測到目標為正式環境時，強制要求使用者輸入確認字串。
6. **速率限制與 robots.txt 遵循**：`HTTPConnector` 預設遵守
   `robots.txt`，且有 `rate_limit_per_second` 限制，避免造成對方主機負擔。
7. **不得繞過驗證或做攻擊性測試**：對第三方網站的存取僅限公開頁面讀取；
   `SecurityMode` 的檢查一律是被動式（觀察公開可得的回應），不嘗試利用
   任何漏洞。

## ConnectorProfile / 資料結構（v0.1.0 範圍）

```python
@dataclass
class ConnectorProfile:
    source_type: str            # "http" | "local_archive" | ...
    detected_stack: str | None  # 例如 "wordpress", "nextjs", "static", None
    has_sitemap: bool
    has_robots_txt: bool
    notes: list[str]

@dataclass
class UrlRecord:
    url: str
    source: str                 # "sitemap" | "crawl" | "seed"
    discovered_depth: int

@dataclass
class PageSnapshot:
    url: str
    status_code: int
    final_url: str
    redirect_chain: list[str]
    headers: dict[str, str]
    html: str
    fetched_at: str             # ISO8601，由呼叫端傳入，不在 connector 內產生
```

## 貢獻新 Connector 的檢查清單

- [ ] 繼承 `WebsiteConnector`，明確宣告 `capabilities()`
- [ ] 所有寫入類方法預設 `dry_run=True`
- [ ] 不在例外訊息、log、回傳值中包含憑證原文
- [ ] 有對應的單元測試（可用 mock，不需要真實外部主機）
- [ ] 在本文件的表格中新增一列，註明狀態與 capabilities
- [ ] 在 `docs/roadmap.md` 中更新對應版本的完成狀態
