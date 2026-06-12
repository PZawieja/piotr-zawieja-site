#!/usr/bin/env python3
"""
publish.py — stamp a post as published with the current UTC timestamp.

Usage:
    python scripts/publish.py <slug>          # publish a draft
    python scripts/publish.py <slug> --force  # re-stamp an already-published post

After running, execute:
    python scripts/build.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"


def find_post(arg: str) -> Path:
    p = Path(arg)
    if p.exists():
        return p
    matches = list(POSTS_DIR.glob(f"*{arg}*.md"))
    if not matches:
        print(f"No post found matching: {arg}")
        sys.exit(1)
    if len(matches) > 1:
        print("Multiple matches — be more specific:")
        for m in matches:
            print(f"  {m.name}")
        sys.exit(1)
    return matches[0]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/publish.py <slug> [--force]")
        sys.exit(1)

    md_file = find_post(sys.argv[1])
    force = "--force" in sys.argv

    post = frontmatter.load(md_file)

    if post.get("status") == "published" and post.get("published_at") and not force:
        print(f"Already published at: {post['published_at']}")
        print("Use --force to re-stamp.")
        sys.exit(0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    post["status"] = "published"
    post["published_at"] = now

    md_file.write_text(frontmatter.dumps(post), encoding="utf-8")

    print(f"Published: {md_file.name}")
    print(f"Timestamp: {now}")
    print("\nNext: python scripts/build.py")


if __name__ == "__main__":
    main()
