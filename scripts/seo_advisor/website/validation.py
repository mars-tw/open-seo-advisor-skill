"""Page-level checks for the offline static website starter."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup


def jsonld_nodes(soup: BeautifulSoup) -> list[dict]:
    """Read every JSON-LD block, including node arrays and @graph documents."""
    nodes = []

    def collect(value):
        if isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, dict):
            nodes.append(value)
            if "@graph" in value:
                collect(value["@graph"])
        else:
            raise ValueError("JSON-LD 需使用物件或物件陣列")

    for script in soup.find_all("script", type=True):
        if script["type"].partition(";")[0].strip().casefold() == "application/ld+json":
            collect(json.loads(script.get_text()))
    return nodes


def node_types(nodes: list[dict]) -> set[str]:
    result = set()
    for node in nodes:
        kinds = node.get("@type", [])
        for kind in kinds if isinstance(kinds, list) else [kinds]:
            if isinstance(kind, str):
                result.add(kind.removeprefix("https://schema.org/"))
    return result


def images_have_alt(soup: BeautifulSoup) -> bool:
    for image in soup.find_all("img"):
        if not image.has_attr("alt"):
            return False
        if image["alt"].strip():
            continue
        # A null alt is an explicit decorative alternative. The starter's hero,
        # an explicitly informative image, and an image-only link need a name.
        if image.get("role") == "img" or image.find_parent(class_="hero-image"):
            return False
        link = image.find_parent("a", href=True)
        if link and not (
            link.get_text(strip=True)
            or link.get("aria-label")
            or link.get("aria-labelledby")
            or any(other.get("alt", "").strip() for other in link.find_all("img"))
        ):
            return False
    return True


def check_page_resources(
    document: Path,
    soup: BeautifulSoup,
    public: Path,
    origin: str,
    remote_actions: set[str],
    live_checks: set[str],
    documents: dict[Path, BeautifulSoup],
) -> tuple[list[str], set[Path]]:
    errors = []
    linked_files = set()
    source = "/" + document.relative_to(public).as_posix()
    page_url = urljoin(origin, source.removesuffix("index.html"))
    base = soup.find("base", href=True)
    base_url = urljoin(page_url, base["href"]) if base else page_url
    expected_origin = urlsplit(origin)
    for tag in soup.find_all(["a", "link", "script", "img"]):
        value = tag.get("href") or tag.get("src")
        if not value:
            continue
        target_url = urljoin(base_url, value)
        target = urlsplit(target_url)
        if tag.name == "a" and target.scheme in {"mailto", "tel"}:
            if target.scheme == "tel":
                valid = re.fullmatch(r"\+?[0-9(][0-9().-]*(?:;[^\s]+)*", target.path)
            else:
                valid = ("@" in unquote(target.path) or bool(target.query)) and not target.netloc
            if not valid:
                errors.append(f"{source}：聯絡連結格式錯誤 {value}")
            continue
        if target.scheme != "https":
            errors.append(f"{source}：資源網址須使用 HTTPS {value}")
            continue
        if (target.hostname, target.port or 443) != (
            expected_origin.hostname,
            expected_origin.port or 443,
        ):
            continue
        resource = (public / unquote(target.path).lstrip("/")).resolve()
        if not resource.is_relative_to(public):
            errors.append(f"{source}：資源超出 public {value}")
            continue
        if resource.is_dir():
            resource = (resource / "index.html").resolve()
        if not resource.is_relative_to(public):
            errors.append(f"{source}：資源超出 public {value}")
            continue
        if not resource.is_file():
            if tag.name == "a" and target_url in remote_actions:
                live_checks.add(target_url)
            else:
                errors.append(f"{source}：找不到本機資源 {value}")
            continue
        if tag.name == "a":
            linked_files.add(resource)
        fragment = unquote(target.fragment.split(":~:", 1)[0])
        if not fragment or resource.suffix.casefold() not in {".htm", ".html"}:
            continue
        if resource not in documents:
            documents[resource] = BeautifulSoup(resource.read_text(encoding="utf-8"), "html.parser")
        dest = documents[resource]
        if fragment.casefold() != "top" and not (
            dest.find(id=fragment) or dest.find("a", attrs={"name": fragment})
        ):
            errors.append(f"{source}：找不到連結目標 {value}")
    return errors, linked_files
