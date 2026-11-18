"""Match Googlebot's applicable robots.txt allow/disallow groups."""

import re
from urllib.parse import quote


def _octets(path: str) -> str:
    # Unreserved percent-encoded ASCII is equivalent to its literal spelling.
    def normalize(match):
        char = chr(int(match[0][1:], 16))
        return char if re.fullmatch(r"[a-zA-Z0-9_.~-]", char) else match[0].upper()

    escaped = quote(path, safe="/:?[]@!$&'()*+,;=%#")
    return re.sub(r"%[0-9a-fA-F]{2}", normalize, escaped)


def robots_fields(content: str):
    for line in content.lstrip("\ufeff").splitlines():
        name, separator, value = line.split("#", 1)[0].partition(":")
        if separator:
            yield name.strip().casefold(), value.strip()


def googlebot_blocks(content: str, paths: list[str]) -> dict[str, tuple[str, str]]:
    """Return blocked paths mapped to the declared agent and winning rule."""
    groups = {"googlebot": [], "*": []}
    specific = False
    agents = {}
    has_rules = False
    for name, value in robots_fields(content):
        if name == "user-agent":
            if has_rules:
                agents.clear()
                has_rules = False
            user_agent = value.casefold()
            token = re.match(r"[a-z_-]+", user_agent)
            if token and token[0] == "googlebot":
                agents["googlebot"] = user_agent
                specific = True
            elif user_agent == "*":
                agents["*"] = user_agent
        elif name in {"allow", "disallow"}:
            has_rules = True
            if value.startswith("/"):
                pattern = _octets(value)
                end = pattern.endswith("$")
                regex = ".*".join(re.escape(part) for part in pattern.removesuffix("$").split("*"))
                matcher = re.compile(regex + (r"\Z" if end else ""))
                for key, agent in agents.items():
                    groups[key].append((matcher, len(pattern), name == "allow", agent, value))

    selected = groups["googlebot" if specific else "*"]
    blocked = {}
    for path in paths:
        normalized = _octets(path)
        matches = [(length, allow, agent, rule) for matcher, length, allow, agent, rule in selected
                   if matcher.match(normalized)]
        if matches:
            _, allowed, agent, rule = max(matches)
            if not allowed:
                blocked[path] = agent, rule
    return blocked


def googlebot_blocked_paths(content: str, paths: list[str]) -> list[str]:
    return [f"{path} (User-agent: {agent}, Disallow: {rule})"
            for path, (agent, rule) in googlebot_blocks(content, paths).items()]
