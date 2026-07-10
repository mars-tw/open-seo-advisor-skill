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

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> "PageSnapshot":
        """取得單一頁面的內容快照，render=True 時使用 headless browser。
        fetched_at 由呼叫端傳入時間戳記，connector 本身不產生時間。"""

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
| `SSHConnector` | v0.2.5 已實作（MVP：唯讀，已接進 CLI） | `read_files`, `read_urls`, 選配 `read_logs` | 透過 SFTP 讀取遠端網站靜態檔案；`list_urls`/`fetch_url` 把遠端檔案系統包裝成 URL 爬取介面供 `seo-advisor audit consultant --source ssh` 使用；`read_logs` 需明確提供 `allowed_log_paths` 白名單，與 `read_file` 共用 component-wise walk 防 symlink；`write_files`/`run_commands` 刻意不做（見 docs/roadmap.md），避免半套實作；DNS rebinding 防護 + component-wise symlink jail 防護 |
| `GitRepoConnector` | v0.2.2 已實作 | `read_files`, `write_files`（走 branch+commit） | 繼承 `LocalArchiveConnector`，操作本機已存在的 git repo，產出可開 PR 的分支+commit；不涉及遠端連線 |
| `WordPressAPIConnector` | v0.2.4 已實作（MVP：唯讀） | `read_urls` | 透過 REST API 盤點 posts/pages + 無認證公開頁面 fetch；只支援 Application Password（可選匿名唯讀）；REST 回傳的 `link` 視為 attacker-controlled，經 scope allowlist 過濾；`write_files`（未來改用獨立的 `write_content` capability）刻意未做 |
| `CloudflareConnector` | v0.3.0 規劃 | `read_urls`, 選配 `deploy`（redirect/cache rules） | 需 API Token，最小權限範圍 |
| `CPanelConnector` | v0.3.0 規劃 | `read_files`, 選配 `write_files` | 有限度的部署能力 |

## SafetyPolicy：把資安原則變成程式碼約束

`seo_advisor.models.SafetyPolicy` 是所有 Connector 建構子都應該接受的參數
（`policy: SafetyPolicy | None = None`），目的是讓下面這份資安要求清單**不只
是文件**，而是真的被程式碼檢查：

```python
class SafetyPolicy(BaseModel):
    dry_run: bool = True
    allowed_capabilities: set[str] = {"read_urls"}
    allow_private_network: bool = False
    respect_robots_txt: bool = True
    rate_limit_per_second: float = 3.0

    def require_capability(self, capability: str, *, connector_id: str) -> None: ...
    def require_write(self, *, connector_id: str) -> None: ...
```

任何實作 `write_file` / `run_command` / `deploy_patch` 的 Connector 子類別，
方法內第一步都應該呼叫 `self.policy.require_capability(...)` 與（若非
dry-run）`self.policy.require_write(...)`，讓「使用者是否真的授權這個操作」
的判斷收斂到單一位置，而不是每個 Connector 各自實作、容易遺漏。

## 資安要求（所有 Connector 必須遵守）

1. **預設 read-only、預設 dry-run**：`write_file` / `run_command` /
   `deploy_patch` 的 `dry_run` 參數預設為 `True`，並由 `SafetyPolicy.dry_run`
   統一約束。
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
6. **速率限制與 robots.txt 遵循**：`HTTPConnector` 遵守 `robots.txt`
   （`security/robots_policy.py`），且有 `rate_limit_per_second` 限制
   （`security/rate_limiter.py`），避免造成對方主機負擔。被 robots.txt
   擋下的 URL，`fetch_url()` 會回傳 `fetch_error_type="blocked_by_robots_txt"`
   而非嘗試繞過。
7. **不得繞過驗證或做攻擊性測試**：對第三方網站的存取僅限公開頁面讀取；
   `SecurityMode` 的檢查一律是被動式（觀察公開可得的回應），不嘗試利用
   任何漏洞。
8. **SSRF 防護**：`HTTPConnector` 建構時與每次 `fetch_url()` 都會透過
   `security/network_policy.py` 檢查目標主機，預設不對 localhost、私有
   網段（RFC1918）、雲端 metadata IP（如 `169.254.169.254`）發送請求，
   除非 `SafetyPolicy.allow_private_network` 明確開啟。
9. **爬取範圍不含外部網域**：sitemap 內若包含指向其他網域的 URL，
   `HTTPConnector.list_urls()` 會略過並記錄下來，而不是照單全收爬取，
   避免掃描範圍意外擴散到使用者未授權的第三方網站。頁面內部連結若因
   redirect（例如 `example.com` → `www.example.com`）換到新 host，
   該 host 會自動加入允許範圍，避免正常網站的內部連結被誤判為外部連結
   而漏爬。

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
