"""RSS 2.0 feed generator for goldlayer.dev/writing/feed.xml"""
from pathlib import Path

SITE_URL = "https://goldlayer.dev"


def escape_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def build_rss(posts: list, writing_dir: Path) -> None:
    items = []
    for p in posts:
        items.append(f"""    <item>
      <title>{escape_xml(p['title'])}</title>
      <link>{p['url']}</link>
      <guid isPermaLink="true">{p['url']}</guid>
      <pubDate>{p['date_rss']}</pubDate>
      <description>{escape_xml(p['description'])}</description>
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Piotr Zawieja — Blog</title>
    <link>{SITE_URL}/writing/</link>
    <description>Analytics engineering, dbt, Snowflake, and AI-assisted data systems.</description>
    <language>en</language>
    <atom:link href="{SITE_URL}/writing/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>"""

    out = writing_dir / "feed.xml"
    out.write_text(rss, encoding="utf-8")
    print(f"  ✓ {out.name}")
