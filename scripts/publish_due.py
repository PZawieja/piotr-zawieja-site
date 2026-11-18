import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
from notion_client import Client

ROOT = Path(__file__).parent.parent
POSTS = ROOT / "content" / "posts"
ASSETS = ROOT / "assets" / "posts"
SITE = "https://goldlayer.dev/writing"
DEFAULT_TIME = "09:00:00+00:00"


def plain(prop: dict) -> str:
    return "".join(
        t["plain_text"] for t in prop.get("rich_text") or prop.get("title") or []
    )


def due_at(prop: dict) -> datetime | None:
    start = (prop.get("date") or {}).get("start")
    if not start:
        return None
    if "T" not in start:
        start = f"{start}T{DEFAULT_TIME}"
    return datetime.fromisoformat(start.replace("Z", "+00:00"))


def due_rows(client: Client, ds_id: str, now: datetime) -> list[dict]:
    rows, cursor = [], None
    while True:
        kwargs = {"filter": {"property": "Status", "select": {"equals": "Scheduled"}}}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = client.data_sources.query(ds_id, **kwargs)
        rows += resp["results"]
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]
    due = []
    for row in rows:
        when = due_at(row["properties"]["Publish at"])
        if when and when <= now and plain(row["properties"]["Slug"]):
            due.append(row)
    return sorted(due, key=lambda r: due_at(r["properties"]["Publish at"]))


def sh(*cmd: str) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def blocked_terms() -> list[str]:
    terms = [t.strip().lower() for t in os.environ.get("BLOCKLIST", "").split(",")]
    terms = [t for t in terms if t]
    if not terms:
        sys.exit(
            "BLOCKLIST is empty; refusing to publish without the confidentiality check"
        )
    return terms


def check_blocklist(paths: list[Path], terms: list[str]) -> None:
    for path in paths:
        files = (
            [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
        )
        for f in files:
            if f.suffix.lower() not in {".md", ".html", ".svg", ".xml", ".txt"}:
                continue
            body = f.read_text(encoding="utf-8", errors="ignore").lower()
            if any(t in body for t in terms):
                raise RuntimeError(f"blocklisted term found in {f.relative_to(ROOT)}")


def stage(slug: str, drafts: Path, today: str) -> Path:
    src = drafts / "posts" / slug
    if not (src / "post.md").exists():
        raise RuntimeError("post.md missing in drafts repo")
    if list(POSTS.glob(f"*-{slug}.md")):
        raise RuntimeError("a post with this slug already exists on the site")
    post = frontmatter.load(src / "post.md")
    post["date"] = datetime.fromisoformat(today).date()
    post["status"] = "draft"
    dest = POSTS / f"{today}-{slug}.md"
    dest.write_text(frontmatter.dumps(post, sort_keys=False) + "\n", encoding="utf-8")
    if (src / "assets").is_dir():
        shutil.copytree(src / "assets", ASSETS / slug, dirs_exist_ok=True)
    return dest


def publish_one(row: dict, drafts: Path, terms: list[str], today: str) -> str:
    slug = plain(row["properties"]["Slug"])
    dest = stage(slug, drafts, today)
    sh(sys.executable, "scripts/publish.py", slug)
    page = ROOT / "writing" / f"{slug}.html"
    check_blocklist([dest, ASSETS / slug, page], terms)
    title = frontmatter.load(dest)["title"]
    paths = [str(dest), "writing", "index.html"]
    if (ASSETS / slug).exists():
        paths.append(str(ASSETS / slug))
    sh("git", "add", *paths)
    sh("git", "commit", "-q", "-m", f"publish: {title}")
    return slug


def mark_published(client: Client, row: dict, slug: str) -> None:
    client.pages.update(
        row["id"],
        properties={
            "Status": {"select": {"name": "Published"}},
            "Live URL": {"url": f"{SITE}/{slug}.html"},
            "Publish at": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        },
    )
    for rel in row["properties"]["Topic"].get("relation", []):
        client.pages.update(
            rel["id"], properties={"Status": {"select": {"name": "Published"}}}
        )


def note_failure(client: Client, row: dict, msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = f"Auto-publish failed {stamp}: {msg}"[:1900]
    client.pages.update(
        row["id"], properties={"Notes": {"rich_text": [{"text": {"content": note}}]}}
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--count", action="store_true", help="print the number of due posts"
    )
    ap.add_argument("--drafts", type=Path, default=ROOT / "_drafts")
    args = ap.parse_args()

    client = Client(auth=os.environ["NOTION_TOKEN"])
    ds_id = os.environ["NOTION_POSTS_DATA_SOURCE_ID"].removeprefix("collection://")
    now = datetime.now(timezone.utc)
    rows = due_rows(client, ds_id, now)

    if args.count:
        print(len(rows))
        if out := os.environ.get("GITHUB_OUTPUT"):
            with open(out, "a") as fh:
                fh.write(f"due={len(rows)}\n")
        return

    terms = blocked_terms()
    today = now.date().isoformat()
    done, failed = [], 0
    for row in rows:
        slug = plain(row["properties"]["Slug"])
        try:
            done.append((row, publish_one(row, args.drafts, terms, today)))
            print(f"published {slug}")
        except Exception as exc:
            failed += 1
            msg = (
                str(exc)
                if not isinstance(exc, subprocess.CalledProcessError)
                else "build or check failed"
            )
            print(f"FAILED {slug}: {msg}")
            sh("git", "reset", "-q", "--hard", "HEAD")
            sh("git", "clean", "-qfd", "content/posts", "assets/posts", "writing")
            note_failure(client, row, msg)

    if done:
        sh("git", "pull", "-q", "--rebase", "origin", "main")
        sh("git", "push", "-q", "origin", "HEAD:main")
        for row, slug in done:
            mark_published(client, row, slug)
    print(f"{len(done)} published, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
