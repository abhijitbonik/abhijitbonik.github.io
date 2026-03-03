#!/usr/bin/env python3
"""
Build static HTML pages for the readings section.

Run:  python scripts/build_readings.py

Generates:
  readings/index.html                          — category grid
  readings/<category>/index.html               — article list
  readings/<category>/<article>/index.html     — individual article
"""

import json
import re
from pathlib import Path

try:
    import markdown as md_module
except ImportError:
    raise SystemExit("Missing dependency: pip install markdown")

REPO_ROOT = Path(__file__).parent.parent
READINGS_DIR = REPO_ROOT / "readings"
IGNORE_DIRS = {"index.html", "manifest.json", ".DS_Store"}
IGNORE_PREFIXES = (".", "_")
MD_EXTENSIONS = ["fenced_code", "tables", "attr_list"]


# ── Utilities ─────────────────────────────────────────────────────────────────

def natural_sort_key(path: Path) -> list:
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r"(\d+)", path.stem)]


def to_title(stem: str) -> str:
    if "_" not in stem and "-" not in stem and len(stem) <= 5:
        return stem.upper()
    return stem.replace("_", " ").replace("-", " ").title()


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


def extract_excerpt(md_text: str, max_chars: int = 200) -> str:
    """First non-heading, non-code, non-table paragraph as plain text."""
    in_fence = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if stripped.startswith(("#", "|", "!", "---", "```")):
            continue
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
        text = re.sub(r"[*_`~]", "", text)
        if text:
            return (text[:max_chars] + "…") if len(text) > max_chars else text
    return ""


def esc(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── Shared HTML blocks ────────────────────────────────────────────────────────

def html_head(title: str, root: str, description: str = "") -> str:
    desc = esc(description or f"{title} — Readings by Abhijit Bonik")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="{desc}">
    <meta name="author" content="Abhijit Bonik">
    <title>{esc(title)} | Readings | Abhijit Bonik</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css">
    <link rel="stylesheet" href="{root}assets/css/style.css">
    <script>(function(){{var t=localStorage.getItem('theme');document.documentElement.setAttribute('data-theme',t||'dark');}})();</script>
</head>"""


def html_nav(root: str, active: str = "readings") -> str:
    return f"""    <nav class="nav" id="nav">
        <div class="nav-container">
            <a href="{root}index.html" class="nav-logo" aria-label="Home">
                <span class="logo-bracket">[</span>AB<span class="logo-bracket">]</span>
            </a>
            <button class="nav-toggle" id="nav-toggle" aria-label="Toggle navigation">
                <span></span><span></span><span></span>
            </button>
            <ul class="nav-menu" id="nav-menu">
                <li><a href="{root}index.html#about"          class="nav-link">About</a></li>
                <li><a href="{root}index.html#experience"     class="nav-link">Experience</a></li>
                <li><a href="{root}index.html#skills"         class="nav-link">Skills</a></li>
                <li><a href="{root}index.html#certifications" class="nav-link">Certifications</a></li>
                <li><a href="{root}index.html#education"      class="nav-link">Education</a></li>
                <li><a href="{root}blog/index.html"           class="nav-link">Blog</a></li>
                <li><a href="{root}readings/index.html"       class="nav-link{' active' if active == 'readings' else ''}">Readings</a></li>
                <li><a href="{root}index.html#contact"        class="nav-link">Contact</a></li>
            </ul>
            <button class="theme-toggle" id="theme-toggle" aria-label="Toggle theme">
                <span id="theme-icon">☀</span>
            </button>
        </div>
    </nav>"""


def html_footer() -> str:
    return """    <footer class="footer">
        <div class="container">
            <p class="footer-text">
                <span class="footer-bracket">[</span> abhijit bonik <span class="footer-bracket">]</span>
            </p>
            <p class="footer-sub">// knowledge is meant to be shared</p>
        </div>
    </footer>"""


def html_scripts(root: str, highlight: bool = False) -> str:
    out = f'    <script src="{root}assets/js/main.js"></script>\n'
    if highlight:
        out += '    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>\n'
        out += '    <script>document.addEventListener("DOMContentLoaded",()=>hljs.highlightAll());</script>\n'
    return out


# ── Page builders ─────────────────────────────────────────────────────────────

def build_readings_index(categories: list, out_path: Path) -> None:
    root = "../"

    cards = ""
    for cat in categories:
        count = len(cat["articles"])
        desc  = f'<p class="readings-category-card-desc">{esc(cat["description"])}</p>' if cat.get("description") else ""
        cards += f"""
                <a href="{cat['id']}/index.html" class="readings-category-card">
                    <div class="readings-category-card-top">
                        <h2 class="readings-category-card-title">{esc(cat['title'])}</h2>
                        <span class="readings-category-card-count">{count}</span>
                    </div>
                    {desc}
                    <div class="readings-category-card-footer">
                        <span class="tech-tag">{count} article{'s' if count != 1 else ''}</span>
                        <span class="readings-category-card-arrow">→</span>
                    </div>
                </a>"""

    if not cards:
        cards = '<p style="font-family:var(--font-mono);color:var(--text-dim);font-size:0.9rem;grid-column:1/-1;">No readings yet. Add .md files to readings/&lt;category&gt;/ and push.</p>'

    page = f"""{html_head('Readings', root)}
<body>
    <canvas id="particle-canvas"></canvas>
    <div class="scanline-overlay"></div>

{html_nav(root)}

    <div class="blog-hero">
        <div class="container">
            <span class="section-tag">&lt;readings&gt;</span>
            <h1 class="section-title">Knowledge.base</h1>
            <p style="color:var(--text-secondary);margin-top:12px;font-family:var(--font-mono);font-size:0.85rem;letter-spacing:1px;">
                Personal notes and deep-dives on ML, Mathematics, and Engineering
            </p>
        </div>
    </div>

    <section class="section" style="padding-top:0;">
        <div class="container">
            <div class="readings-category-grid">
                {cards}
            </div>
        </div>
    </section>

{html_footer()}
{html_scripts(root)}
</body>
</html>"""

    out_path.write_text(page, encoding="utf-8")
    print(f"  ✓  {out_path.relative_to(REPO_ROOT)}")


def build_category_page(cat: dict, out_path: Path) -> None:
    root    = "../../"
    title   = cat["title"]
    cat_id  = cat["id"]

    items = ""
    for art in cat["articles"]:
        excerpt  = art.get("excerpt", "")
        date_tag = f'<span class="blog-date">{esc(art["date"])}</span>' if art.get("date") else ""
        tags_row = "".join(f'<span class="tech-tag">{esc(t)}</span>' for t in art.get("tags", []))
        meta     = f'<div class="readings-article-card-meta">{date_tag}{tags_row}</div>' if (date_tag or tags_row) else ""
        excp_div = f'<p class="readings-article-card-excerpt">{esc(excerpt)}</p>' if excerpt else ""

        items += f"""
                <a href="{art['id']}/index.html" class="readings-article-card">
                    <div class="readings-article-card-body">
                        <h3 class="readings-article-card-title">{esc(art['title'])}</h3>
                        {excp_div}
                        {meta}
                    </div>
                    <span class="readings-article-arrow">→</span>
                </a>"""

    desc_p = f'<p class="readings-section-desc">{esc(cat.get("description",""))}</p>' if cat.get("description") else ""

    page = f"""{html_head(title, root)}
<body>
    <canvas id="particle-canvas"></canvas>
    <div class="scanline-overlay"></div>

{html_nav(root)}

    <div class="blog-hero">
        <div class="container">
            <div class="readings-breadcrumb" style="justify-content:center;margin-bottom:16px;">
                <a href="../index.html">Readings</a>
                <span class="bc-sep">/</span>
                {esc(title)}
            </div>
            <span class="section-tag">&lt;{cat_id}&gt;</span>
            <h1 class="section-title">{esc(title)}</h1>
            {desc_p}
        </div>
    </div>

    <section class="section" style="padding-top:0;">
        <div class="container">
            <div class="readings-article-list">
                {items}
            </div>
        </div>
    </section>

{html_footer()}
{html_scripts(root)}
</body>
</html>"""

    out_path.write_text(page, encoding="utf-8")
    print(f"  ✓  {out_path.relative_to(REPO_ROOT)}")


def build_article_page(cat: dict, article: dict, content_html: str,
                        prev_art, next_art, out_path: Path) -> None:
    root      = "../../../"
    title     = article["title"]
    cat_title = cat["title"]
    cat_id    = cat["id"]

    tags_html = "".join(f'<span class="tech-tag">{esc(t)}</span>' for t in article.get("tags", []))
    date_html = f'<span class="blog-date">{esc(article["date"])}</span>' if article.get("date") else ""
    meta_html = f'<div class="reading-article-meta">{date_html}{tags_html}</div>' if (date_html or tags_html) else ""

    prev_block = ""
    next_block = ""
    if prev_art:
        prev_block = f"""<a href="../{prev_art['id']}/index.html" class="reading-nav-link reading-nav-prev">
                        <span class="reading-nav-label">← Previous</span>
                        <span class="reading-nav-title">{esc(prev_art['title'])}</span>
                    </a>"""
    if next_art:
        next_block = f"""<a href="../{next_art['id']}/index.html" class="reading-nav-link reading-nav-next">
                        <span class="reading-nav-label">Next →</span>
                        <span class="reading-nav-title">{esc(next_art['title'])}</span>
                    </a>"""

    article_nav = ""
    if prev_block or next_block:
        article_nav = f"""
            <div class="reading-article-nav">
                {prev_block}
                {next_block}
            </div>"""

    page = f"""{html_head(title, root, description=article.get('description', ''))}
<body>
    <canvas id="particle-canvas"></canvas>
    <div class="scanline-overlay"></div>

{html_nav(root)}

    <div class="reading-article-page">
        <div class="container">

            <div class="readings-breadcrumb">
                <a href="../../index.html">Readings</a>
                <span class="bc-sep">/</span>
                <a href="../index.html">{esc(cat_title)}</a>
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
    if not READINGS_DIR.is_dir():
        print(f"readings/ not found at {READINGS_DIR}")
        return

    categories = []

    for cat_dir in sorted(READINGS_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        if cat_dir.name in IGNORE_DIRS or any(cat_dir.name.startswith(p) for p in IGNORE_PREFIXES):
            continue

        md_files = sorted(cat_dir.glob("*.md"), key=natural_sort_key)
        if not md_files:
            continue

        # Optional _category.json for custom title/description
        meta_path = cat_dir / "_category.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        cat = {
            "id":          cat_dir.name,
            "title":       meta.get("title", to_title(cat_dir.name)),
            "description": meta.get("description", ""),
            "articles":    [],
        }

        print(f"\n[{cat['id']}] {cat['title']}")

        for md_file in md_files:
            raw_content = md_file.read_text(encoding="utf-8")
            fm, body    = parse_frontmatter(raw_content)

            title       = fm.get("title") or extract_first_heading(body) or to_title(md_file.stem)
            date        = fm.get("date", "")
            tags        = parse_tags(fm.get("tags", ""))
            description = fm.get("description", "")
            excerpt     = extract_excerpt(body)
            html_body   = md_module.markdown(body, extensions=MD_EXTENSIONS)

            cat["articles"].append({
                "id":          md_file.stem,
                "title":       title,
                "date":        date,
                "tags":        tags,
                "description": description,
                "excerpt":     excerpt,
                "html":        html_body,
            })

        categories.append(cat)

        # Generate article pages
        arts = cat["articles"]
        for i, art in enumerate(arts):
            art_dir = READINGS_DIR / cat["id"] / art["id"]
            art_dir.mkdir(parents=True, exist_ok=True)
            build_article_page(
                cat, art, art["html"],
                prev_art=arts[i - 1] if i > 0 else None,
                next_art=arts[i + 1] if i < len(arts) - 1 else None,
                out_path=art_dir / "index.html",
            )

        # Generate category index
        build_category_page(cat, READINGS_DIR / cat["id"] / "index.html")

    # Generate main readings index
    build_readings_index(categories, READINGS_DIR / "index.html")

    total = sum(len(c["articles"]) for c in categories)
    print(f"\nDone — {total} articles across {len(categories)} categories.")


if __name__ == "__main__":
    build()
