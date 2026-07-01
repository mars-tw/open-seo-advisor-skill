"""Connector 抽象層：統一不同網站接入方式的介面。"""

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.connectors.local_archive import LocalArchiveConnector

__all__ = ["WebsiteConnector", "HTTPConnector", "LocalArchiveConnector"]
