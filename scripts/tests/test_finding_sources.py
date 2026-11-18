"""Every source ID emitted by the analyzers must resolve in the public registry."""

import ast
from pathlib import Path

import yaml


def test_finding_sources_have_registered_public_references():
    root = Path(__file__).resolve().parents[2]
    entries = yaml.safe_load((root / "config/sources.yaml").read_text(encoding="utf-8"))["sources"]
    ids = {entry["id"] for entry in entries}
    assert len(ids) == len(entries)
    for module in (root / "scripts/seo_advisor/analyzers").glob("*.py"):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "Finding":
                continue
            for keyword in node.keywords:
                if keyword.arg == "sources":
                    missing = set(ast.literal_eval(keyword.value)) - ids
                    assert not missing, f"{module.name}:{node.lineno}: {missing}"
