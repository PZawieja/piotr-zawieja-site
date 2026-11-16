#!/usr/bin/env python3
"""
build.py — static site generator for goldlayer.dev writing section.

Usage:
    python scripts/build.py

Reads:  content/posts/*.md  (status: published only)
Writes: writing/[slug].html, writing/index.html, writing/feed.xml
        Injects writing list into index.html between WRITING_START/END markers.
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from html import escape, unescape
from pathlib import Path

import frontmatter
import markdown
from jinja2 import Environment, FileSystemLoader

from build_rss import build_rss

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
TEMPLATES_DIR = ROOT / "templates"
WRITING_DIR = ROOT / "writing"
INDEX_HTML = ROOT / "index.html"

SITE_URL = "https://goldlayer.dev"

MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

MD_EXTENSIONS = ["extra", "fenced_code", "tables", "nl2br"]


def _image_attributes(content_html: str) -> tuple[str | None, str | None]:
    image = re.search(r"<img\b([^>]*)>", content_html, re.IGNORECASE | re.DOTALL)
    if not image:
        return None, None

    attributes = image.group(1)

    def get_attribute(name: str) -> str | None:
        match = re.search(
            rf"\b{name}\s*=\s*([\"'])(.*?)\1",
            attributes,
            re.IGNORECASE | re.DOTALL,
        )
        return unescape(match.group(2)) if match else None

    return get_attribute("src"), get_attribute("alt")


def _site_image_url(source: str | None) -> str | None:
    if not source:
        return None
    if source.startswith(("https://", "http://", "/", "data:")):
        return source
    return "/" + source.removeprefix("../").removeprefix("./")


def _dedent_html(text: str) -> str:
    """Strip leading whitespace from HTML-tag lines.

    Python-Markdown treats lines with 4+ leading spaces as code blocks.
    Raw HTML extracted from hand-crafted files often carries indentation that
    triggers this — `    <p>text</p>` renders as a literal code block instead
    of a paragraph. Strip the indent only from lines whose first non-space
    character is `<` so markdown content (lists, nested blocks) is unaffected.
    """
    result = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        result.append(stripped if stripped.startswith("<") else line)
    return "\n".join(result)


def _parse_published_at(post) -> datetime:
    raw = post.get("published_at")
    if raw:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    d = post["date"]
    return datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc)


def parse_posts() -> list:
    posts = []
    for md_file in POSTS_DIR.glob("*.md"):
        post = frontmatter.load(md_file)
        if post.get("status") != "published":
            continue

        published_at = _parse_published_at(post)
        date_formatted = f"{published_at.day} {MONTH_ABBR[published_at.month]} {published_at.year}"

        md = markdown.Markdown(extensions=[*MD_EXTENSIONS, "toc"])
        content_html = md.convert(_dedent_html(post.content))
        first_image, first_image_alt = _image_attributes(content_html)
        feature_image = _site_image_url(post.get("feature_image") or first_image)

        posts.append({
            "title": post["title"],
            "published_at": published_at,
            "date_formatted": date_formatted,
            "date_iso": published_at.date().isoformat(),
            "date_rss": published_at.strftime("%a, %d %b %Y %H:%M:%S +0000"),
            "slug": post["slug"],
            "description": post["description"],
            "tags": post["tags"],
            "read_time": post["read_time"],
            "content": content_html,
            "toc": md.toc,
            "feature_image": feature_image,
            "feature_image_alt": post.get("feature_image_alt") or first_image_alt or post["title"],
            "feature_image_caption": post.get("feature_image_caption", ""),
            "og_image": (
                f"{SITE_URL}{feature_image}"
                if feature_image and feature_image.startswith("/")
                else feature_image or f"{SITE_URL}/og-default.png"
            ),
            "url": f"{SITE_URL}/writing/{post['slug']}.html",
        })

    posts.sort(key=lambda p: p["published_at"], reverse=True)
    return posts


def _related_posts(post: dict, all_posts: list, count: int = 3) -> list:
    primary_tag = post["tags"][0] if post["tags"] else None
    if not primary_tag:
        return []
    return [p for p in all_posts if p["slug"] != post["slug"] and primary_tag in p["tags"]][:count]


def build_posts(posts: list, env: Environment) -> None:
    template = env.get_template("post.html")
    WRITING_DIR.mkdir(exist_ok=True)
    for i, post in enumerate(posts):
        prev_post = posts[i + 1] if i + 1 < len(posts) else None
        next_post = posts[i - 1] if i > 0 else None
        html = template.render(
            **post,
            related_posts=_related_posts(post, posts),
            prev_post=prev_post,
            next_post=next_post,
        )
        out = WRITING_DIR / f"{post['slug']}.html"
        out.write_text(html, encoding="utf-8")
        print(f"  ✓ writing/{post['slug']}.html")


def build_writing_index(posts: list, env: Environment) -> None:
    template = env.get_template("writing.html")
    tag_counts = Counter(tag for p in posts for tag in p["tags"])
    all_tags = sorted(tag_counts.keys())
    html = template.render(posts=posts, all_tags=all_tags, tag_counts=tag_counts)
    out = WRITING_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print("  ✓ writing/index.html")


def update_index_html(posts: list) -> None:
    content = INDEX_HTML.read_text(encoding="utf-8")

    marker = re.compile(r"<!-- WRITING_START -->.*?<!-- WRITING_END -->", re.DOTALL)
    if not marker.search(content):
        print("ERROR: writing section markers not found in index.html", file=sys.stderr)
        sys.exit(1)

    featured = posts[0]
    primary_tag = escape(featured["tags"][0] if featured["tags"] else "Field note", quote=True)
    featured_tags = " · ".join(escape(tag) for tag in featured["tags"][:2])
    featured_html = (
        f'        <a class="home-feature" href="/writing/{escape(featured["slug"], quote=True)}.html" data-category="{primary_tag}">\n'
        f'          <div>\n'
        f'            <p class="kicker">Latest field note · {featured_tags}</p>\n'
        f'            <h3>{escape(featured["title"])}</h3>\n'
        f'            <p>{escape(featured["description"])}</p>\n'
        f'          </div>\n'
        f'          <div class="home-feature-meta"><span>{escape(str(featured["read_time"]))} min read</span>'
        f'<span>{escape(featured["date_formatted"])} · Read article →</span></div>\n'
        f'      </a>'
    )

    article_rows = []
    for post in posts[1:3]:
        tags_label = " · ".join(
            "Data quality" if tag == "data-quality" else tag
            for tag in post["tags"][:2]
        )
        article_rows.append(
            f'          <a class="home-note" href="/writing/{escape(post["slug"], quote=True)}.html">\n'
            f'            <p class="kicker">{escape(tags_label)} · {escape(str(post["read_time"]))} min</p>\n'
            f'            <h3>{escape(post["title"])}</h3>\n'
            f'        </a>'
        )

    rows_html = "\n".join(article_rows)
    new_block = (
        f"<!-- WRITING_START -->\n"
        f"      <div class=\"home-writing\">\n"
        f"{featured_html}\n"
        f"        <div class=\"home-note-list\" aria-label=\"More recent articles\">\n"
        f"{rows_html}\n"
        f"        </div>\n"
        f"      </div>\n"
        f"      <!-- WRITING_END -->"
    )

    new_content = marker.sub(new_block, content)

    if new_content == content:
        print("  ~ index.html writing section unchanged")
    else:
        INDEX_HTML.write_text(new_content, encoding="utf-8")
        print("  ✓ index.html (writing section updated)")


def main() -> None:
    print("Building goldlayer.dev...")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    posts = parse_posts()
    if not posts:
        print("No published posts found — nothing to build.")
        return

    print(f"Found {len(posts)} published post(s)")

    build_posts(posts, env)
    build_writing_index(posts, env)
    build_rss(posts, WRITING_DIR)
    update_index_html(posts)

    print("Done.")


if __name__ == "__main__":
    main()
