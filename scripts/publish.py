#!/usr/bin/env python3
"""
publish.py — stamp a post as published, rebuild the site, and verify it.

Usage:
    python scripts/publish.py <slug>          # publish a draft
    python scripts/publish.py <slug> --force  # re-stamp an already-published post
    python scripts/publish.py <slug> --dry    # preview without writing

Runs build.py + check.py automatically after stamping.
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

ROOT = Path(__file__).parent.parent
POSTS_DIR = ROOT / "content" / "posts"
SCRIPTS = Path(__file__).parent


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


def run(cmd: list[str]) -> int:
    return subprocess.run([sys.executable] + cmd).returncode


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/publish.py <slug> [--force] [--dry]")
        sys.exit(1)

    md_file = find_post(sys.argv[1])
    force = "--force" in sys.argv
    dry = "--dry" in sys.argv

    post = frontmatter.load(md_file)

    if post.get("status") == "published" and post.get("published_at") and not force:
        print(f"Already published at: {post['published_at']}")
        print("Use --force to re-stamp.")
        sys.exit(0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if dry:
        print(f"[dry] Would publish: {md_file.name}")
        print(f"[dry] Timestamp:     {now}")
        sys.exit(0)

    post["status"] = "published"
    post["published_at"] = now
    md_file.write_text(frontmatter.dumps(post), encoding="utf-8")

    print(f"Published: {md_file.name}")
    print(f"Timestamp: {now}\n")

    print("── Building site ──")
    rc = run([str(SCRIPTS / "build.py")])
    if rc != 0:
        print("\nbuild.py failed — fix errors before committing.")
        sys.exit(rc)

    print("\n── Checking output ──")
    rc = run([str(SCRIPTS / "check.py"), post["slug"]])
    if rc != 0:
        print("\ncheck.py failed — fix errors before committing.")
        sys.exit(rc)

    print("\nReady to commit and push:")
    print(f"  git add content/posts/{md_file.name} writing/{post['slug']}.html writing/index.html writing/feed.xml index.html")
    print(f"  git commit -m \"publish: {post['title']}\"")
    print("  git push origin main")


if __name__ == "__main__":
    main()
