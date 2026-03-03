#!/usr/bin/env python3
"""
Build static HTML pages for the blog section.

Run:  python scripts/build_blog.py

Reads all .md files from blog/ (flat, no subdirectories).

Generates:
  blog/index.html              — listing page with category filter
  blog/<slug>/index.html       — individual post page

Frontmatter (all fields optional):
  ---
  title:       My Post Title
  date:        2025-01-30
  category:    Voice AI
  tags:        websocket, latency, streaming
  description: A short description shown in the listing
  ---
"""

import json
import re
from datetime import datetime
from pathlib import Path

try:
    import markdown as md_module
except ImportError:
    raise SystemExit("Missing dependency: pip install markdown")

REPO_ROOT = Path(__file__).parent.parent
BLOG_DIR  = REPO_ROOT / "blog"
IGNORE    = {"index.html", ".DS_Store"}
IGNORE_PREFIXES = (".", "_")
MD_EXTENSIONS   = ["fenced_code", "tables", "attr_list"]


# ── Utilities ─────────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple:
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    raw  = content[3:end].strip()
    body = content[end + 3:].strip()
    data = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        data[key.strip().lower()] = val.strip().strip("\"'")
    return data, body


def parse_tags(raw: str) -> list:
    return [t.strip() for t in raw.split(",") if t.strip()]


def extract_first_heading(body: str):
    m = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def extract_excerpt(md_text: str, max_chars: int = 220) -> str:
    in_fence = False
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue
        if s.startswith(("#", "|", "!", "---")):
            continue
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        text = re.sub(r"[*_`~]", "", text)
        if text:
            return (text[:max_chars] + "…") if len(text) > max_chars else text
    return ""


def format_date(date_str: str) -> str:
    """'2025-01-30' → 'Jan 30, 2025'"""
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return date_str


def sort_key_date(post: dict) -> str:
    """Sort key for descending date order (negate by padding)."""
    raw = post.get("date", "")
    if not raw:
        return "0000-00-00"
    return raw


def to_title(stem: str) -> str:
    return stem.replace("_", " ").replace("-", " ").title()


def esc(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── Shared HTML blocks ────────────────────────────────────────────────────────

def html_head(title: str, root: str, description: str = "") -> str:
    desc = esc(description or f"{title} — Blog by Abhijit Bonik")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{desc}">
    <meta name="author" content="Abhijit Bonik">
    <title>{esc(title)} | Abhijit Bonik</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <link rel="stylesheet" href="{root}assets/css/style.css">
</head>"""


def html_nav(root: str, active: str = "") -> str:
    def a(href, label, key=""):
        cls = "nav-link active" if key == active else "nav-link"
        return f'<li><a href="{href}" class="{cls}">{label}</a></li>'

    return f"""    <nav class="nav" id="nav">
        <div class="nav-container">
            <a href="{root}index.html" class="nav-logo" aria-label="Home">
                <span class="logo-bracket">[</span>AB<span class="logo-bracket">]</span>
            </a>
            <button class="nav-toggle" id="nav-toggle" aria-label="Toggle navigation">
                <span></span><span></span><span></span>
            </button>
            <ul class="nav-menu" id="nav-menu">
                {a(root + "index.html#about",          "About")}
                {a(root + "index.html#experience",     "Experience")}
                {a(root + "index.html#skills",         "Skills")}
                {a(root + "index.html#certifications", "Certifications")}
                {a(root + "index.html#education",      "Education")}
                {a(root + "blog/index.html",           "Blog",     "blog")}
                {a(root + "readings/index.html",       "Readings", "readings")}
                {a(root + "index.html#contact",        "Contact")}
            </ul>
        </div>
    </nav>"""


def html_footer() -> str:
    return """    <footer class="footer">
        <div class="container">
            <p class="footer-text">
                <span class="footer-bracket">[</span> abhijit bonik <span class="footer-bracket">]</span>
            </p>
            <p class="footer-sub">// thoughts worth sharing</p>
        </div>
    </footer>"""


def html_scripts(root: str, highlight: bool = False, extra: str = "") -> str:
    out = f'    <script src="{root}assets/js/main.js"></script>\n'
    if highlight:
        out += '    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>\n'
        out += '    <script>document.addEventListener("DOMContentLoaded",()=>hljs.highlightAll());</script>\n'
    if extra:
        out += f'    <script>{extra}</script>\n'
    return out


# ── Page builders ─────────────────────────────────────────────────────────────

def build_blog_index(posts: list, categories: list, out_path: Path) -> None:
    root = "../"

    # Filter buttons
    filter_btns = '<button class="filter-btn active" data-filter="all">All Posts</button>\n'
    for cat in categories:
        filter_btns += f'                <button class="filter-btn" data-filter="{esc(cat)}">{esc(cat)}</button>\n'

    # Post list items
    items = ""
    for post in posts:
        cat       = post.get("category", "")
        date_disp = format_date(post.get("date", ""))
        tags_html = "".join(f'<span class="tech-tag">{esc(t)}</span>' for t in post.get("tags", []))
        excerpt   = post.get("excerpt", "")

        items += f"""
                <a href="{post['slug']}/index.html" class="blog-list-item" data-category="{esc(cat)}">
                    <div class="blog-list-meta">
                        <span class="blog-date">{esc(date_disp)}</span>
                        {f'<span class="blog-category">{esc(cat)}</span>' if cat else ""}
                    </div>
                    <h2 class="blog-list-title">{esc(post['title'])}</h2>
                    {f'<p class="blog-list-excerpt">{esc(excerpt)}</p>' if excerpt else ""}
                    {f'<div class="blog-list-tags">{tags_html}</div>' if tags_html else ""}
                </a>"""

    filter_js = """
        const filterBtns = document.querySelectorAll('.filter-btn');
        const postItems   = document.querySelectorAll('.blog-list-item');
        filterBtns.forEach(function(btn) {
            btn.addEventListener('click', function() {
                filterBtns.forEach(function(b) { b.classList.remove('active'); });
                btn.classList.add('active');
                var filter = btn.dataset.filter;
                postItems.forEach(function(item) {
                    item.style.display = (filter === 'all' || item.dataset.category === filter) ? '' : 'none';
                });
            });
        });
    """

    page = f"""{html_head('Blog', root, 'Articles on Voice AI, Machine Learning, and Engineering by Abhijit Bonik')}
<body>
    <canvas id="particle-canvas"></canvas>
    <div class="scanline-overlay"></div>

{html_nav(root, active='blog')}

    <div class="blog-hero">
        <div class="container">
            <span class="section-tag">&lt;blog&gt;</span>
            <h1 class="section-title">Signal.broadcast</h1>
            <p style="color:var(--text-secondary);margin-top:12px;font-family:var(--font-mono);font-size:0.85rem;letter-spacing:1px;">
                Thoughts on Voice AI, Machine Learning, and Engineering
            </p>
        </div>
    </div>

    <section class="section" style="padding-top:0;">
        <div class="container">
            <div class="blog-filters">
                {filter_btns}
            </div>
            <div class="blog-list">
                {items if items else '<p style="font-family:var(--font-mono);color:var(--text-dim);">&gt; No posts yet. Add .md files to blog/ and push.</p>'}
            </div>
        </div>
    </section>

{html_footer()}
{html_scripts(root, extra=filter_js)}
</body>
</html>"""

    out_path.write_text(page, encoding="utf-8")
    print(f"  ✓  {out_path.relative_to(REPO_ROOT)}")


def build_post_page(post: dict, content_html: str,
                    prev_post, next_post, out_path: Path) -> None:
    root      = "../../"
    title     = post["title"]
    cat       = post.get("category", "")
    date_disp = format_date(post.get("date", ""))

    tags_html = "".join(f'<span class="tech-tag">{esc(t)}</span>' for t in post.get("tags", []))
    meta_parts = []
    if date_disp:
        meta_parts.append(f'<span class="blog-date">{esc(date_disp)}</span>')
    if cat:
        meta_parts.append(f'<span class="blog-category">{esc(cat)}</span>')
    meta_html = f'<div class="reading-article-meta">{"".join(meta_parts)}{tags_html}</div>' if meta_parts or tags_html else ""

    prev_block = ""
    next_block = ""
    if prev_post:
        prev_block = f"""<a href="../{prev_post['slug']}/index.html" class="reading-nav-link reading-nav-prev">
                        <span class="reading-nav-label">← Newer</span>
                        <span class="reading-nav-title">{esc(prev_post['title'])}</span>
                    </a>"""
    if next_post:
        next_block = f"""<a href="../{next_post['slug']}/index.html" class="reading-nav-link reading-nav-next">
                        <span class="reading-nav-label">Older →</span>
                        <span class="reading-nav-title">{esc(next_post['title'])}</span>
                    </a>"""

    article_nav = ""
    if prev_block or next_block:
        article_nav = f"""
            <div class="reading-article-nav">
                {prev_block}
                {next_block}
            </div>"""

    page = f"""{html_head(title, root, description=post.get('description', ''))}
<body>
    <canvas id="particle-canvas"></canvas>
    <div class="scanline-overlay"></div>

{html_nav(root, active='blog')}

    <div class="reading-article-page">
        <div class="container">

            <div class="readings-breadcrumb">
                <a href="../index.html">Blog</a>
                <span class="bc-sep">/</span>
                {esc(title)}
            </div>

            <header class="reading-article-header">
                <h1 class="reading-article-title">{esc(title)}</h1>
                {meta_html}
            </header>

            <article class="markdown-body">
{content_html}
            </article>

            {article_nav}

        </div>
    </div>

{html_footer()}
{html_scripts(root, highlight=True)}
</body>
</html>"""

    out_path.write_text(page, encoding="utf-8")
    print(f"  ✓  {out_path.relative_to(REPO_ROOT)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def build() -> None:
    if not BLOG_DIR.is_dir():
        BLOG_DIR.mkdir()
        print("Created blog/ directory.")

    md_files = [
        f for f in BLOG_DIR.glob("*.md")
        if f.name not in IGNORE and not any(f.name.startswith(p) for p in IGNORE_PREFIXES)
    ]

    posts = []
    for md_file in md_files:
        raw       = md_file.read_text(encoding="utf-8")
        fm, body  = parse_frontmatter(raw)

        title       = fm.get("title") or extract_first_heading(body) or to_title(md_file.stem)
        date        = fm.get("date", "")
        category    = fm.get("category", "")
        tags        = parse_tags(fm.get("tags", ""))
        description = fm.get("description", "")
        excerpt     = extract_excerpt(body)
        html_body   = md_module.markdown(body, extensions=MD_EXTENSIONS)

        posts.append({
            "slug":        md_file.stem,
            "title":       title,
            "date":        date,
            "category":    category,
            "tags":        tags,
            "description": description,
            "excerpt":     excerpt,
            "html":        html_body,
        })

    # Sort newest first
    posts.sort(key=sort_key_date, reverse=True)

    # Unique sorted categories (preserve insertion order of sorted posts)
    seen = set()
    categories = []
    for p in posts:
        cat = p.get("category", "")
        if cat and cat not in seen:
            seen.add(cat)
            categories.append(cat)

    print(f"\n[blog] {len(posts)} posts across {len(categories)} categories")

    # Generate individual post pages
    for i, post in enumerate(posts):
        post_dir = BLOG_DIR / post["slug"]
        post_dir.mkdir(exist_ok=True)
        # prev = newer post (lower index), next = older post (higher index)
        build_post_page(
            post, post["html"],
            prev_post=posts[i - 1] if i > 0 else None,
            next_post=posts[i + 1] if i < len(posts) - 1 else None,
            out_path=post_dir / "index.html",
        )

    # Generate blog index
    build_blog_index(posts, categories, BLOG_DIR / "index.html")

    print(f"\nDone — {len(posts)} posts built.")


if __name__ == "__main__":
    build()
