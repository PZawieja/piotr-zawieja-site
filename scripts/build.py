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

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

MD_EXTENSIONS = ["extra", "fenced_code", "tables", "nl2br"]


def parse_posts() -> list:
    posts = []
    for md_file in sorted(POSTS_DIR.glob("*.md"), reverse=True):
        post = frontmatter.load(md_file)
        if post.get("status") != "published":
            continue

        date = post["date"]
        date_formatted = f"{MONTH_NAMES[date.month]} {date.year}"

        content_html = markdown.markdown(
            post.content,
            extensions=MD_EXTENSIONS,
        )

        posts.append({
            "title": post["title"],
            "date": date,
            "date_formatted": date_formatted,
            "date_iso": date.isoformat(),
            "date_rss": date.strftime("%a, %d %b %Y 00:00:00 +0000"),
            "slug": post["slug"],
            "description": post["description"],
            "tags": post["tags"],
            "read_time": post["read_time"],
            "content": content_html,
            "url": f"{SITE_URL}/writing/{post['slug']}.html",
        })
    return posts


def build_posts(posts: list, env: Environment) -> None:
    template = env.get_template("post.html")
    WRITING_DIR.mkdir(exist_ok=True)
    for post in posts:
        html = template.render(**post)
        out = WRITING_DIR / f"{post['slug']}.html"
        out.write_text(html, encoding="utf-8")
        print(f"  ✓ writing/{post['slug']}.html")


def build_writing_index(posts: list, env: Environment) -> None:
    template = env.get_template("writing.html")
    all_tags = sorted({tag for p in posts for tag in p["tags"]})
    html = template.render(posts=posts, all_tags=all_tags)
    out = WRITING_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"  ✓ writing/index.html")


def update_index_html(posts: list) -> None:
    content = INDEX_HTML.read_text(encoding="utf-8")

    if "<!-- WRITING_START -->" not in content:
        print("ERROR: WRITING_START marker not found in index.html", file=sys.stderr)
        sys.exit(1)

    items = []
    for post in posts[:5]:
        tags_html = "".join(
            f'<span class="writing-tag">{t}</span>' for t in post["tags"][:3]
        )
        items.append(
            f'      <a href="writing/{post["slug"]}.html" class="writing-item">\n'
            f'        <div class="writing-item-meta">\n'
            f'          {tags_html}\n'
            f'          <span class="writing-date">{post["date_formatted"]} · {post["read_time"]} min</span>\n'
            f'        </div>\n'
            f'        <h3 class="writing-title">{post["title"]}</h3>\n'
            f'        <p class="writing-lede">{post["description"]}</p>\n'
            f'      </a>'
        )

    list_html = "\n".join(items)
    view_all = (
        f'\n      <p style="margin-top:1.5rem">'
        f'<a href="writing/" style="font-family:var(--mono);font-size:0.78rem;color:var(--muted)">'
        f'View all articles →</a></p>'
    ) if len(posts) > 5 else ""

    new_block = (
        f"<!-- WRITING_START -->\n"
        f"    <div class=\"writing-list\">\n\n"
        f"{list_html}\n\n"
        f"    </div>{view_all}\n"
        f"    <!-- WRITING_END -->"
    )

    new_content = re.sub(
        r"<!-- WRITING_START -->.*?<!-- WRITING_END -->",
        new_block,
        content,
        flags=re.DOTALL,
    )

    if new_content == content:
        print("  ~ index.html writing section unchanged")
    else:
        INDEX_HTML.write_text(new_content, encoding="utf-8")
        print(f"  ✓ index.html (writing section updated)")


def main() -> None:
    print("Building goldlayer.dev...")

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
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
