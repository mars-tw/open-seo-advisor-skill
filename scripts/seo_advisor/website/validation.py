"""Page-level checks for the offline static website starter."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString
from seo_advisor.url_utils import canonical_destination
from seo_advisor.website.images import responsive_image_status
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


_COMMERCIAL_TYPES = {"Offer", "AggregateOffer", "Review", "AggregateRating"}
_COMMERCIAL_PROPERTIES = {"offers", "review", "aggregateRating"}


def _schema_name(value):
    for prefix in ("https://schema.org/", "http://schema.org/", "schema:"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _has_value(value) -> bool:
    """JSON-LD nulls, empty containers and type-only placeholders carry no value."""
    if isinstance(value, dict):
        return any(_has_value(child) for key, child in value.items()
                   if key not in {"@type", "@context", "@language", "@direction", "@index"})
    if isinstance(value, list):
        return any(_has_value(child) for child in value)
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def commercial_claims(value) -> set[str]:
    """Find substantive offers and reviews at any nesting level."""
    found = set()
    if isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if isinstance(types, list):
            claim_types = _COMMERCIAL_TYPES.intersection(
                _schema_name(kind) for kind in types if isinstance(kind, str)
            )
            if claim_types and _has_value({k: v for k, v in value.items() if k != "@id"}):
                found.update(claim_types)
        for key, child in value.items():
            if key == "@context":
                continue
            name = _schema_name(key)
            if name in _COMMERCIAL_PROPERTIES and _has_value(child):
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


_TEXT_BLOCKS = {
    "address", "article", "aside", "blockquote", "br", "caption", "dd", "div", "dl", "dt", "figcaption",
    "figure", "footer", "h3", "h4", "h5", "h6", "header", "li", "ol", "p", "pre", "section",
    "table", "td", "th", "tr", "ul",
}


def _inline_style(node, prop):
    style = node.get("style", "")
    if not style:
        return ""
    values = re.findall(r"(?:^|;)\s*" + prop + r"\s*:\s*([^;]+)", style, re.I)
    if not values:
        return ""
    important = [v for v in values if re.search(r"!\s*important\s*$", v, re.I)]
    return re.sub(r"!\s*important\s*$", "", (important or values)[-1], flags=re.I).strip().lower()


def _not_rendered(node):
    return (node.name in {"script", "style", "template", "noscript"}
            or node.has_attr("hidden") or _inline_style(node, "display") == "none")


def _copy_tokens(node, visible=True):
    """Yield the heading boundaries and readable text, preserving inline words."""
    if isinstance(node, NavigableString):
        if visible and not isinstance(node, Comment):
            yield "text", str(node)
        return
    if _not_rendered(node):
        return
    # visibility is inherited; a child may explicitly make itself visible again.
    visibility = _inline_style(node, "visibility")
    if visibility in {"visible", "hidden", "collapse"}:
        visible = visibility == "visible"
    if node.name in {"h1", "h2"}:
        title = "".join(value for child in node.children for _, value in _copy_tokens(child, visible))
        if title.strip():
            yield "heading", "" if node.name == "h1" else " ".join(title.split())
        return
    if node.name in _TEXT_BLOCKS:
        yield "text", " "
    for child in node.children:
        yield from _copy_tokens(child, visible)
    if node.name in _TEXT_BLOCKS:
        yield "text", " "


def missing_page_copy(soup: BeautifulSoup, page: ContentPage) -> list[str]:
    """Check approved text under its heading, regardless of the chosen body markup."""
    parts = {}
    for main in soup.find_all("main"):
        if any(_not_rendered(parent) for parent in main.parents):
            continue
        heading = None
        for kind, value in _copy_tokens(main):
            if kind == "heading":
                heading = value
            elif heading is not None:
                parts.setdefault(heading, []).append(value)
    required = [("", page.intro), *((s.title, s.body) for s in page.sections)]
    section_text = {k: " ".join("".join(chunks).split()) for k, chunks in parts.items()}
    return [title or "導言" for title, body in required if
            " ".join(body.split()) not in section_text.get(" ".join(title.split()), "")]


def _label_text(node, include_hidden=False) -> str:
    if isinstance(node, NavigableString):
        return "" if isinstance(node, Comment) else str(node).strip()
    if node.name in {"script", "style", "template"}:
        return ""
    if not include_hidden and (_not_rendered(node) or node.get("aria-hidden") == "true"):
        return ""
    label = node.get("aria-label", "").strip()
    if label:
        return label
    if node.name == "img":
        return node.get("alt", "").strip()
    if node.name == "input":
        kind = node.get("type", "text").casefold()
        if kind in {"button", "submit", "reset"}:
            default = {"submit": "Submit", "reset": "Reset"}.get(kind, "")
            return node.get("value", default).strip() or node.get("title", "").strip()
        if kind == "image":
            return (node.get("alt", "").strip() or node.get("title", "").strip())
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
    decoded_candidates: dict[Path, tuple[str, str]],
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
            if resource not in decoded_candidates:
                decoded_candidates[resource] = responsive_image_status(resource)
            status, message = decoded_candidates[resource]
            candidate.update(status=status, decode=message)
            if status == "invalid":
                errors.append(f"{source}：{message} {value}（{candidate['media']} {candidate['descriptor']}）")
            elif status == "verify_live":
                live_checks.add(target_url)
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
