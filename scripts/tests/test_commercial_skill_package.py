"""Verify that the commercial SEO instructions work as a standalone skill."""

import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "skills" / "commercial-seo"


def local_targets(document):
    for block in MarkdownIt().parse(document.read_text(encoding="utf-8")):
        for token in block.children or ():
            if token.type not in {"link_open", "image"}:
                continue
            url = urlsplit(token.attrGet("href" if token.type == "link_open" else "src"))
            if not url.scheme and not url.netloc and url.path:
                yield (document.parent / unquote(url.path)).resolve()


def test_root_skill_routes_to_commercial_skill():
    assert PACKAGE / "SKILL.md" in local_targets(ROOT / "SKILL.md")


def test_commercial_skill_is_portable(tmp_path):
    installed = shutil.copytree(PACKAGE, tmp_path / "offline host" / "skills" / PACKAGE.name)
    entry = installed / "SKILL.md"
    before, metadata, _ = entry.read_text(encoding="utf-8").split("---\n", maxsplit=2)
    assert before == ""
    assert yaml.safe_load(metadata)["name"] == installed.name

    for name in ("workflow.md", "setup.md", "markets.md"):
        assert (installed / "references" / name).is_file()

    for document in installed.rglob("*.md"):
        for target in local_targets(document):
            assert target.is_relative_to(
                installed
            ), f"{document.name} links outside skill: {target}"
            assert target.is_file(), f"Missing target in {document.name}: {target}"
