"""Page-level checks for the offline static website starter."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString
from seo_advisor.url_utils import canonical_destination
from seo_advisor.website.models import ContentPage


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


def commercial_claims(value) -> set[str]:
    """Return commercial properties, including nested Product and Offer nodes."""
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "@context":
                continue
            name = key.rsplit("/", 1)[-1].removeprefix("schema:")
            if name in {"aggregateRating", "review", "offers"}:
                found.add(name)
            found.update(commercial_claims(child))
    elif isinstance(value, list):
        for child in value:
            found.update(commercial_claims(child))
    return found


def canonical_targets(soup: BeautifulSoup, page_url: str) -> set[str]:
    base = soup.find("base", href=True)
    base_url = urljoin(page_url, base["href"]) if base else page_url
    targets = set()
    for link in soup.select("head link[rel]"):
        if "canonical" in (rel.casefold() for rel in link["rel"]):
            href = link.get("href", "").strip()
            targets.add(canonical_destination(base_url, href))
    return targets


def missing_page_copy(soup: BeautifulSoup, page: ContentPage) -> list[str]:
    """Check the approved intro and the body under each actual section heading."""
    parts = {}
    heading = None
    for tag in soup.select("main h1, main h2, main p"):
        if tag.find_parent(attrs={"hidden": True}) or tag.has_attr("hidden"):
            continue
        text = " ".join(tag.get_text().split())
        if tag.name == "h1":
            heading = ""
        elif tag.name == "h2":
            heading = text
        elif heading is not None:
            parts.setdefault(heading, []).append(text)
    required = [("", page.intro), *((s.title, s.body) for s in page.sections)]
    return [title or "導言" for title, body in required
            if " ".join(body.split()) not in " ".join(parts.get(" ".join(title.split()), []))]


def _label_text(node, include_hidden=False) -> str:
    if isinstance(node, NavigableString):
        return "" if isinstance(node, Comment) else str(node).strip()
    if node.name in {"script", "style", "template"}:
        return ""
    if not include_hidden and (node.has_attr("hidden") or node.get("aria-hidden") == "true"):
        return ""
    label = node.get("aria-label", "").strip()
    if label:
        return label
    if node.name == "img":
        return node.get("alt", "").strip()
    text = " ".join(filter(None, (_label_text(child, include_hidden) for child in node.children)))
    return text or node.get("title", "").strip()


def _link_name(link, soup) -> str:
    refs = [soup.find(id=target) for target in link.get("aria-labelledby", "").split()]
    refs = [ref for ref in refs if ref is not None]
    if refs:
        return " ".join(filter(None, (_label_text(ref, include_hidden=ref.has_attr("hidden")
                                                  or ref.get("aria-hidden") == "true") for ref in refs)))
    return _label_text(link)


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
        if link and not _link_name(link, soup):
            return False
    return True


def _srcset_urls(srcset):
    # URL tokens may contain commas. A trailing comma ends a descriptorless
    # candidate; after whitespace the descriptor list ends at the next comma.
    rest = srcset.lstrip(" \t\n\r\f,")
    while rest:
        match = re.match(r"[^ \t\n\r\f]+", rest)
        url = match[0]
        rest = rest[match.end():]
        descriptor = ""
        if url.endswith(","):
            url = url.rstrip(",")
        else:
            descriptor, _, rest = rest.partition(",")
        if url:
            yield url, descriptor.strip()
        rest = rest.lstrip(" \t\n\r\f,")


def _resource_urls(soup):
    for tag in soup.find_all(["a", "link", "script", "img", "source"]):
        picture = tag.find_parent("picture") if tag.name in {"img", "source"} else None
        if tag.name == "source" and picture is None:
            continue
        value = tag.get("href") or tag.get("src")
        if value:
            fallback = tag.name == "img" and (picture is not None or tag.has_attr("srcset"))
            yield tag, value, ("fallback", "") if fallback else None
        if tag.name in {"img", "source"}:
            for value, descriptor in _srcset_urls(tag.get("srcset", "")):
                yield tag, value, (tag.get("media", "all"), descriptor)


def check_page_resources(
    document: Path,
    soup: BeautifulSoup,
    public: Path,
    origin: str,
    remote_actions: set[str],
    live_checks: set[str],
    documents: dict[Path, BeautifulSoup],
    responsive_images: list[dict],
) -> tuple[list[str], set[Path]]:
    errors = []
    linked_files = set()
    source = "/" + document.relative_to(public).as_posix()
    page_url = urljoin(origin, source.removesuffix("index.html"))
    base = soup.find("base", href=True)
    base_url = urljoin(page_url, base["href"]) if base else page_url
    expected_origin = urlsplit(origin)
    for tag, value, responsive in _resource_urls(soup):
        target_url = urljoin(base_url, value)
        target = urlsplit(target_url)
        candidate = None
        if responsive is not None:
            media, descriptor = responsive
            candidate = {"page": source, "media": media, "descriptor": descriptor,
                         "url": target_url, "status": "invalid"}
            responsive_images.append(candidate)
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
            if candidate is not None:
                candidate["status"] = "verify_live"
                live_checks.add(target_url)
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
        if candidate is not None:
            candidate["status"] = "present"
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
