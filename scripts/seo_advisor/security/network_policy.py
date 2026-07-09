"""SSRF 基本防護：判斷主機名稱是否指向私有網段、loopback 或雲端 metadata IP。

背景：HTTPConnector 允許使用者輸入任意網址掃描，如果日後這個工具被包裝成
常駐服務（例如 Web Demo、hosted API），使用者輸入的網址若指向
`169.254.169.254`（AWS/GCP/Azure 的 metadata endpoint）或內網服務，可能被
利用做 SSRF 攻擊探測內部網路。CLI 情境下使用者只會拿來掃描「自己的電腦」
或「自己的網站」，風險較低，但仍預設關閉私有網段存取，需要時可由使用者
明確用 SafetyPolicy.allow_private_network=True 開啟（例如本機開發環境掃描
localhost）。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class PrivateNetworkBlockedError(ValueError):
    """目標主機解析為私有網段/loopback/metadata IP，且政策不允許時拋出。"""


# 各大雲端服務商的 metadata endpoint，即使不落在標準私有網段也要擋。這組
# IP 永遠拒絕、不提供任何 allow_private_network 之類的 override（見
# is_cloud_metadata_host），跟「私有網段可在使用者明確同意後允許」是
# 不同等級的封鎖。
_CLOUD_METADATA_IPS = frozenset({"169.254.169.254", "fd00:ec2::254"})


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    if str(ip) in _CLOUD_METADATA_IPS:
        return True
    return False


def is_cloud_metadata_host(hostname: str) -> bool:
    """判斷主機名稱是否直接是雲端 metadata IP（不含 DNS 解析，只判斷字面
    IP）。這組位址任何情境下都不該被允許連線，呼叫端不應該提供任何開關
    讓使用者覆寫這個判斷——跟「私有網段可在明確同意後允許」是不同等級的
    封鎖，因此獨立成公開函式，不與 is_private_or_blocked_host 混用同一組
    override 語意。
    """
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return str(ip) in _CLOUD_METADATA_IPS


def is_private_or_blocked_host(hostname: str) -> bool:
    """判斷主機名稱（可能是 IP 或需要 DNS 解析的網域）是否指向被封鎖的網段。

    無法解析時（DNS 查詢失敗）視為不封鎖，交由後續實際連線嘗試自然失敗，
    避免這裡的判斷邏輯本身變成阻斷合法網站的來源。
    """
    if not hostname:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        return _is_blocked_ip(ip)
    except ValueError:
        pass

    if hostname.lower() == "localhost":
        return True

    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return True
    return False


def ensure_host_allowed(url: str, *, allow_private_network: bool) -> None:
    """檢查 URL 的主機名稱，若指向私有/內部網段且未明確允許，拋出例外。"""
    if allow_private_network:
        return
    hostname = urlparse(url).hostname or ""
    if is_private_or_blocked_host(hostname):
        raise PrivateNetworkBlockedError(
            f"目標網址 {url!r} 指向私有網段、本機或雲端 metadata IP，"
            "預設政策不允許存取這類位址（避免 SSRF 風險）。"
            "如果你確實要掃描自己的內網或本機網站，"
            "請在建立 connector 時將 SafetyPolicy.allow_private_network 設為 True。"
        )
