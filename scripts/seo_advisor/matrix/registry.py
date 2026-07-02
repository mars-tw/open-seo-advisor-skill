"""角色註冊表：從 assets/roles.yaml 載入所有 AgentRole。

用 importlib.resources 讀取套件內資產，確保正式打包成 wheel 後仍可載入
（與 demo_assets / config_assets 相同做法）。
"""

from __future__ import annotations

import functools
import importlib.resources

import yaml

from seo_advisor.matrix.models import AgentRole

_ROLES_ASSET_PACKAGE = "seo_advisor.matrix.assets"
_ROLES_FILENAME = "roles.yaml"


@functools.lru_cache(maxsize=1)
def load_roles() -> dict[str, AgentRole]:
    """載入所有角色，回傳 {role_id: AgentRole}。結果快取（單次執行不變）。"""
    traversable = importlib.resources.files(_ROLES_ASSET_PACKAGE) / _ROLES_FILENAME
    with importlib.resources.as_file(traversable) as path:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    roles: dict[str, AgentRole] = {}
    for entry in data.get("roles", []):
        role = AgentRole.model_validate(entry)
        roles[role.id] = role
    return roles


def get_role(role_id: str) -> AgentRole | None:
    return load_roles().get(role_id.lower())


def all_roles() -> list[AgentRole]:
    return list(load_roles().values())
