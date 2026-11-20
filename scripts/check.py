#!/usr/bin/env python3
"""
check.py — pre-publish validation for goldlayer.dev.

Run after build.py (or via publish.py --check) to catch formatting
and consistency issues before pushing. Exits non-zero if any check fails.

Usage:
    python scripts/check.py            # check all published posts
    python scripts/check.py <slug>     # check a single post by slug
"""
import re
import sys
from datetime import datetime
from pathlib import Path

import frontmatter

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
WRITING_DIR = ROOT / "writing"
TEMPLATE = ROOT / "templates" / "post.html"
INDEX_HTML = ROOT / "index.html"

REQUIRED_FIELDS = ["title", "date", "published_at", "slug", "description", "tags", "read_time", "status"]

CANONICAL_TAGS = {"dbt", "AI", "Snowflake", "data-quality"}

errors: list[str] = []
warnings: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  WARN  {msg}")


def ok(msg: str) -> None:
    print(f"  ok    {msg}")


# ── checks ───────────────────────────────────────────────────────────

def check_tags(post) -> None:
    slug = post.get("slug", "?")
    tags = post.get("tags") or []
    if not tags:
        fail(f"{slug}: no tags — every post needs at least one canonical tag")
        return
    primary = tags[0]
    if primary not in CANONICAL_TAGS:
        fail(f"{slug}: primary tag '{primary}' is not canonical — must be one of {sorted(CANONICAL_TAGS)}")
    for tag in tags[1:]:
        if tag not in CANONICAL_TAGS:
            fail(f"{slug}: tag '{tag}' is not canonical — consolidate into {sorted(CANONICAL_TAGS)}")
    if primary in CANONICAL_TAGS and all(t in CANONICAL_TAGS for t in tags):
        ok(f"{slug}: tags valid — {tags}")


def check_read_time(md_file: Path, post) -> None:
    slug = post.get("slug", "?")
    raw = md_file.read_text(encoding="utf-8")
    body = raw.split("---", 2)[2] if raw.startswith("---") and raw.count("---") >= 2 else raw
    words = len(body.split())
    estimated = max(1, round(words / 200))
    declared = int(post.get("read_time") or 0)
    if abs(estimated - declared) > 2:
        warn(f"{slug}: read_time {declared} min but ~{estimated} min estimated ({words} words) — update frontmatter")
    else:
        ok(f"{slug}: read_time {declared} min ({words} words, ~{estimated} min)")


def check_takeaways(slug: str) -> None:
    html_file = WRITING_DIR / f"{slug}.html"
    if not html_file.exists():
        return
    if 'class="takeaways"' not in html_file.read_text(encoding="utf-8"):
        warn(f"{slug}.html: no takeaways block found — add <div class=\"takeaways\"> at end of article")
    else:
        ok(f"{slug}.html: takeaways block present")


def check_duplicate_slugs() -> None:
    slugs: dict[str, list[str]] = {}
    for md_file in POSTS_DIR.glob("*.md"):
        post = frontmatter.load(md_file)
        slug = post.get("slug")
        if slug:
            slugs.setdefault(slug, []).append(md_file.name)
    dupes = {s: fs for s, fs in slugs.items() if len(fs) > 1}
    if dupes:
        for slug, files in dupes.items():
            fail(f"duplicate slug '{slug}' in: {files}")
    else:
        ok(f"no duplicate slugs ({len(slugs)} posts)")


def check_description_length(post) -> None:
    slug = post.get("slug", "?")
    desc = post.get("description", "") or ""
    if len(desc) > 160:
        warn(f"{slug}: description {len(desc)} chars — OG tags truncate at ~160")
    else:
        ok(f"{slug}: description length {len(desc)} chars")


# ── helpers ──────────────────────────────────────────────────────────

def _css_classes_in_template() -> set[str]:
    text = TEMPLATE.read_text(encoding="utf-8")
    classes = set()
    for selector_list in re.findall(r"([^{}]+)\{", text):
        classes.update(re.findall(r"\.([\w-]+)", selector_list))
    return classes


def _body_html(article_html: str) -> str:
    m = re.search(r'class="article-body">(.*?)</div>', article_html, re.DOTALL)
    return m.group(1) if m else article_html


def _classes_in_body(body: str) -> set[str]:
    return set(re.findall(r'class="([\w-]+)"', body))

# ── checks ────────────────────────────────────────────────────────────

def check_frontmatter(md_file: Path) -> dict | None:
    post = frontmatter.load(md_file)
    missing = [f for f in REQUIRED_FIELDS if post.get(f) is None]
    if missing:
        fail(f"{md_file.name}: missing frontmatter fields: {missing}")
        return None
    if post["status"] != "published":
        return None
    raw_ts = post["published_at"]
    if not isinstance(raw_ts, datetime):
        iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z?$")
        if not iso_re.match(str(raw_ts).strip()):
            fail(f"{md_file.name}: published_at is not ISO format: {raw_ts!r}")
    return post


def check_rendered_html(slug: str, template_classes: set[str]) -> None:
    html_file = WRITING_DIR / f"{slug}.html"
    if not html_file.exists():
        fail(f"{slug}.html: rendered file missing — did you run build.py?")
        return

    html = html_file.read_text(encoding="utf-8")
    body = _body_html(html)

    # escaped tags mean markdown treated HTML lines as code blocks
    escaped = re.findall(r"&lt;(p|h[1-6]|ul|ol|li|div|pre|code|hr|table|tr|td|th)\b", body)
    if escaped:
        fail(f"{slug}.html: {len(escaped)} escaped HTML tag(s) in body: {sorted(set(escaped))}")
    else:
        ok(f"{slug}.html: no escaped HTML tags")

    # custom classes in body that have no CSS in template
    body_classes = _classes_in_body(body)
    # ignore classes that are inherently structural or come from code highlighting
    ignored = {
        "article-body", "article-wrap", "article-meta", "article-title",
        "article-lede", "article-footer", "meta-tag", "meta-date",
        "byline", "back-link", "nav-brand", "nav-back",
        "codehilite", "highlight",
        "language-sql", "language-python", "language-yaml",
        "language-bash", "language-shell", "language-markdown",
        "language-text", "language-jinja2", "language-dbt",
        "hll", "c", "err", "g", "k", "l", "n", "o", "p", "cm", "cp",
        "cpf", "c1", "cs", "gd", "ge", "gr", "gh", "gi", "go", "gp",
        "gs", "gu", "gt", "kc", "kd", "kn", "kp", "kr", "kt", "ld",
        "m", "s", "na", "nb", "nc", "no", "nd", "ni", "ne", "nf",
        "nl", "nn", "nx", "py", "nt", "nv", "ow", "pm", "w", "mb",
        "mf", "mh", "mi", "mo", "sa", "sb", "sc", "dl", "sd", "s2",
        "se", "sh", "si", "sx", "sr", "ss", "bp", "fm", "vc", "vg",
        "vi", "vm", "il",
    }
    unstyled = body_classes - template_classes - ignored
    if unstyled:
        fail(f"{slug}.html: classes used in body with no CSS in post.html: {sorted(unstyled)}")
    else:
        ok(f"{slug}.html: all body CSS classes are defined")


def check_index_html() -> None:
    text = INDEX_HTML.read_text(encoding="utf-8")

    writing_block = re.search(
        r"<!-- WRITING_START -->(.*?)<!-- WRITING_END -->", text, re.DOTALL
    )
    if not writing_block:
        fail("index.html: WRITING_START/END markers missing")
        return

    if not re.search(r'<a href="/writing/">Blog</a>', text):
        fail("index.html: Blog navigation link missing")
    else:
        ok("index.html: Blog navigation link present")

    block = writing_block.group(1)
    lead_count = len(re.findall(r'class="home-lead"', block))
    if lead_count != 1:
        fail(f"index.html: {lead_count} lead blog post(s) in writing block (expected 1)")
    else:
        ok("index.html: one lead blog post present")

    recent_count = len(re.findall(r'class="home-recent-item"', block))
    if recent_count == 0:
        fail("index.html: no recent blog posts in writing block")
    else:
        ok(f"index.html: {recent_count} recent blog post(s) present")

    tile_count = len(re.findall(r'class="home-project-tile[ "]', text))
    if 'class="home-project-tile is-flagship"' not in text:
        fail("index.html: flagship project missing from project shelf")
    else:
        ok(f"index.html: project shelf present ({tile_count} projects)")


def check_orphans() -> None:
    """Every writing/*.html (except index) should have a markdown source."""
    html_slugs = {f.stem for f in WRITING_DIR.glob("*.html") if f.stem != "index"}
    md_slugs = set()
    for md_file in POSTS_DIR.glob("*.md"):
        post = frontmatter.load(md_file)
        if post.get("status") == "published":
            md_slugs.add(post.get("slug", ""))

    orphans = html_slugs - md_slugs
    if orphans:
        fail(f"orphan HTML file(s) with no markdown source: {sorted(orphans)}")
    else:
        ok(f"no orphan HTML files ({len(html_slugs)} article(s) all have sources)")


def check_writing_index(published_slugs: list[str]) -> None:
    wi = WRITING_DIR / "index.html"
    if not wi.exists():
        fail("writing/index.html missing — run build.py")
        return
    text = wi.read_text(encoding="utf-8")
    count = len(re.findall(r'class="featured-post"', text))
    count += len(re.findall(r'class="post-card"', text))
    if count != len(published_slugs):
        fail(
            f"writing/index.html lists {count} articles but {len(published_slugs)} "
            f"published posts exist — run build.py"
        )
    else:
        ok(f"writing/index.html: {count} articles listed (matches published count)")


# ── main ──────────────────────────────────────────────────────────────

def main() -> None:
    slug_filter = sys.argv[1] if len(sys.argv) > 1 else None
    template_classes = _css_classes_in_template()

    published: list[tuple[Path, dict]] = []
    md_files = sorted(POSTS_DIR.glob("*.md"))
    if slug_filter:
        md_files = [f for f in md_files if slug_filter in f.name]
        if not md_files:
            print(f"No post found matching: {slug_filter}")
            sys.exit(1)

    print("Checking goldlayer.dev...\n")

    print("── Frontmatter ──")
    for md_file in md_files:
        result = check_frontmatter(md_file)
        if result and result["status"] == "published":
            check_tags(result)
            check_description_length(result)
            published.append((md_file, result))

    print("\n── Content ──")
    for md_file, post in published:
        check_read_time(md_file, post)

    print("\n── Rendered HTML ──")
    for _, post in published:
        check_rendered_html(post["slug"], template_classes)
        check_takeaways(post["slug"])

    if not slug_filter:
        print("\n── Site structure ──")
        check_index_html()
        check_orphans()
        check_duplicate_slugs()
        check_writing_index([p["slug"] for _, p in published])

    print()
    if errors:
        print(f"{'─'*50}")
        print(f"FAILED — {len(errors)} error(s), {len(warnings)} warning(s)")
        sys.exit(1)
    elif warnings:
        print(f"PASSED with {len(warnings)} warning(s)")
    else:
        print(f"All checks passed ({len(published)} post(s) verified)")


if __name__ == "__main__":
    main()
