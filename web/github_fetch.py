"""Turn a GitHub repository or pull-request URL into reviewable source files.

Uses the public GitHub REST API via httpx. A ``GITHUB_TOKEN`` env var is used
automatically if present (raises rate limits and enables private repos), but is
not required for public targets.

Caps keep a review bounded and fast — we are visualizing a pipeline, not
indexing a monorepo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import httpx

# Extensions we know how to review (matches the reviewer's language set).
SOURCE_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go",
    ".rb", ".php", ".cs", ".sh",
}
_EXT_TO_LANG = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".go": "go", ".rb": "ruby", ".php": "php", ".cs": "csharp", ".sh": "bash",
}

# Paths we never want to spend a review on.
_SKIP_DIRS = ("node_modules/", "vendor/", "dist/", "build/", ".venv/",
              "site-packages/", "third_party/", "migrations/")
_SKIP_HINTS = ("test", "spec", "mock", "fixture", "__pycache__", ".min.")

MAX_FILES = 6
MAX_FILE_LINES = 1200
GITHUB_API = "https://api.github.com"


@dataclass
class SourceFile:
    path: str
    content: str
    language: str

    @property
    def lines(self) -> int:
        return self.content.count("\n") + 1


@dataclass
class Target:
    kind: str          # "repo" or "pr"
    owner: str
    repo: str
    number: int | None  # PR number, when kind == "pr"
    label: str          # human-readable, e.g. "owner/repo#42"
    url: str


def parse_target(raw: str) -> Target:
    """Parse a GitHub URL (or ``owner/repo`` shorthand) into a Target."""
    url = raw.strip().rstrip("/")

    pr = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if pr:
        owner, repo, num = pr.group(1), pr.group(2), int(pr.group(3))
        return Target("pr", owner, repo, num, f"{owner}/{repo}#{num}", url)

    repo_m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if repo_m:
        owner, repo = repo_m.group(1), repo_m.group(2)
        return Target("repo", owner, repo, None, f"{owner}/{repo}",
                      f"https://github.com/{owner}/{repo}")

    short = re.match(r"^([\w.-]+)/([\w.-]+)$", url)
    if short:
        owner, repo = short.group(1), short.group(2)
        return Target("repo", owner, repo, None, f"{owner}/{repo}",
                      f"https://github.com/{owner}/{repo}")

    raise ValueError(
        "Could not parse target. Use a GitHub repo URL, a /pull/<n> URL, "
        "or 'owner/repo'."
    )


def _client() -> httpx.Client:
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "langgraph-security-reviewer"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(headers=headers, timeout=30, follow_redirects=True)


def _is_reviewable(path: str) -> bool:
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if ext.lower() not in SOURCE_EXT:
        return False
    low = path.lower()
    if any(low.startswith(d) or f"/{d}" in low for d in _SKIP_DIRS):
        return False
    if any(h in low for h in _SKIP_HINTS):
        return False
    return True


def _lang(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    return _EXT_TO_LANG.get(ext.lower(), "unknown")


def _clip(content: str) -> str:
    lines = content.splitlines()
    if len(lines) > MAX_FILE_LINES:
        lines = lines[:MAX_FILE_LINES] + ["", f"# ... truncated at {MAX_FILE_LINES} lines ..."]
    return "\n".join(lines)


def fetch_files(target: Target) -> list[SourceFile]:
    """Fetch up to MAX_FILES reviewable source files for the target."""
    with _client() as client:
        if target.kind == "pr":
            return _fetch_pr_files(client, target)
        return _fetch_repo_files(client, target)


def _fetch_repo_files(client: httpx.Client, t: Target) -> list[SourceFile]:
    meta = client.get(f"{GITHUB_API}/repos/{t.owner}/{t.repo}")
    meta.raise_for_status()
    branch = meta.json().get("default_branch", "main")

    tree = client.get(
        f"{GITHUB_API}/repos/{t.owner}/{t.repo}/git/trees/{branch}",
        params={"recursive": "1"},
    )
    tree.raise_for_status()
    blobs = [
        node for node in tree.json().get("tree", [])
        if node.get("type") == "blob" and _is_reviewable(node["path"])
    ]
    # Prefer smaller, top-level-ish files; they review fast and read clearly.
    blobs.sort(key=lambda n: (n["path"].count("/"), n.get("size", 0)))

    files: list[SourceFile] = []
    for node in blobs[: MAX_FILES * 2]:
        raw = client.get(
            f"https://raw.githubusercontent.com/{t.owner}/{t.repo}/{branch}/{node['path']}"
        )
        if raw.status_code != 200 or not raw.text.strip():
            continue
        files.append(SourceFile(node["path"], _clip(raw.text), _lang(node["path"])))
        if len(files) >= MAX_FILES:
            break
    if not files:
        raise ValueError("No reviewable source files found in this repository.")
    return files


def _fetch_pr_files(client: httpx.Client, t: Target) -> list[SourceFile]:
    resp = client.get(
        f"{GITHUB_API}/repos/{t.owner}/{t.repo}/pulls/{t.number}/files",
        params={"per_page": 100},
    )
    resp.raise_for_status()
    changed = [
        f for f in resp.json()
        if f.get("status") != "removed" and _is_reviewable(f["filename"])
    ]
    # Biggest changes first — that's where the risk usually concentrates.
    changed.sort(key=lambda f: f.get("changes", 0), reverse=True)

    files: list[SourceFile] = []
    for f in changed[:MAX_FILES]:
        raw = client.get(f["raw_url"])
        if raw.status_code != 200 or not raw.text.strip():
            continue
        files.append(SourceFile(f["filename"], _clip(raw.text), _lang(f["filename"])))
    if not files:
        raise ValueError("No reviewable changed source files found in this PR.")
    return files
