"""WebsiteConnector 抽象介面。

規格詳見 docs/connector_contract.md。核心精神：上層 analyzer 完全不需要
知道資料是從 HTTP 爬來的、SSH 讀檔案讀來的、還是 CMS API 拿到的，一律
透過本介面存取。

所有新增的 Connector 都必須繼承這個類別，並遵守以下規則：
1. 預設 read-only、預設 dry-run（write_file / run_command / deploy_patch
   的 dry_run 參數預設為 True）。
2. 不得在例外訊息、log 或回傳值中包含憑證原文。
3. capabilities() 必須誠實回報這個實例實際支援的能力。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.models import (
    BackupResult,
    CommandResult,
    ConnectorProfile,
    DeployResult,
    FileRecord,
    LogEntry,
    PageSnapshot,
    PatchResult,
    UrlRecord,
)


class ConnectorCapabilityError(NotImplementedError):
    """當呼叫端要求的能力超出該 connector 實際支援範圍時拋出。"""


class WebsiteConnector(ABC):
    """所有網站接入方式的統一介面。"""

    @abstractmethod
    def id(self) -> str:
        """回傳此 connector 實例的識別字串，例如 'http:example.com'。"""

    @abstractmethod
    def capabilities(self) -> set[str]:
        """回傳此 connector 支援的能力集合。

        可能的值：read_urls, read_files, write_files, run_commands,
        read_logs, deploy。呼叫端在使用對應方法前應先檢查此集合。
        """

    @abstractmethod
    def probe(self) -> ConnectorProfile:
        """初次連線時的健康檢查與環境偵測。"""

    @abstractmethod
    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        """取得 URL 清單（透過 sitemap 或爬取）。"""

    @abstractmethod
    def fetch_url(self, url: str, render: bool = False) -> PageSnapshot:
        """取得單一頁面的內容快照。render=True 需 headless browser 支援。"""

    def list_files(self, path: str) -> list[FileRecord]:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 list_files()，請確認 capabilities() 是否包含 'read_files'。"
        )

    def read_file(self, path: str) -> bytes:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 read_file()，請確認 capabilities() 是否包含 'read_files'。"
        )

    def write_file(self, path: str, content: bytes, dry_run: bool = True) -> PatchResult:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 write_file()，請確認 capabilities() 是否包含 'write_files'。"
        )

    def run_command(self, command: list[str], dry_run: bool = True) -> CommandResult:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 run_command()，請確認 capabilities() 是否包含 'run_commands'。"
        )

    def get_logs(self, log_type: str, since: str) -> list[LogEntry]:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 get_logs()，請確認 capabilities() 是否包含 'read_logs'。"
        )

    def deploy_patch(self, patch: dict, dry_run: bool = True) -> DeployResult:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 deploy_patch()，請確認 capabilities() 是否包含 'deploy'。"
        )

    def backup(self, targets: list[str]) -> BackupResult:
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 backup()。"
        )

    def close(self) -> None:
        """釋放連線資源。預設為 no-op，子類別可覆寫。"""
        return None

    def __enter__(self) -> "WebsiteConnector":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
