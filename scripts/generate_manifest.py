#!/usr/bin/env python3
"""
Generate readings/manifest.json by scanning the readings/ directory.

For each subdirectory in readings/, it creates a category entry.
For each .md file in a category directory, it creates an article entry.

Frontmatter (optional):
  ---
  title: My Article Title
  date: 2025-01-10
  tags: ml, regression, supervised
  description: A short description of the article
  ---

If frontmatter is absent:
  - title  → first `# Heading` in the file, or filename title-cased
  - date   → empty string
  - tags   → empty list
"""

import json
import os
import re
from pathlib import Path


def natural_sort_key(path: Path) -> list:
    """Sort key that orders '1.2' before '1.10' (natural numeric order)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', path.stem)]


READINGS_DIR = Path(__file__).parent.parent / "readings"
MANIFEST_PATH = READINGS_DIR / "manifest.json"

# Files and directories to ignore inside readings/
IGNORE_NAMES = {"index.html", "manifest.json"}
IGNORE_PREFIXES = (".", "_")


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and return (data_dict, body_text)."""
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    raw = content[3:end].strip()
    body = content[end + 3:].strip()
    data: dict = {}

    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip().strip("\"'")
        data[key] = val

    return data, body


def extract_first_heading(body: str) -> str | None:
    """Return text of the first markdown `# Heading`, or None."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else None


def filename_to_title(stem: str) -> str:
    """Convert snake_case or kebab-case filename to Title Case.

    Short names with no separators (e.g. 'ml', 'nlp', 'asr') are uppercased.
    """
    # If no separators and short, treat as acronym
    if "_" not in stem and "-" not in stem and len(stem) <= 5:
        return stem.upper()
    return stem.replace("_", " ").replace("-", " ").title()


def parse_tags(raw: str) -> list[str]:
    """Parse a comma-separated tags string into a list."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def process_article(md_path: Path) -> dict:
    content = md_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)

    title = (
        frontmatter.get("title")
        or extract_first_heading(body)
        or filename_to_title(md_path.stem)
    )
    date = frontmatter.get("date", "")
    tags = parse_tags(frontmatter.get("tags", ""))
    description = frontmatter.get("description", "")

    article: dict = {
        "id": md_path.stem,
        "title": title,
        "date": date,
        "tags": tags,
    }
    if description:
        article["description"] = description

    return article


def process_category(cat_dir: Path) -> dict | None:
    md_files = sorted(cat_dir.glob("*.md"), key=natural_sort_key)
    if not md_files:
        return None

    articles = [process_article(f) for f in md_files]

    # Check for a _category.json metadata file for custom title/description
    meta_path = cat_dir / "_category.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    else:
        meta = {}

    return {
        "id": cat_dir.name,
        "title": meta.get("title", filename_to_title(cat_dir.name)),
        "description": meta.get("description", ""),
        "articles": articles,
    }


def generate() -> None:
    if not READINGS_DIR.is_dir():
        print(f"readings/ directory not found at {READINGS_DIR}")
        return

    categories = []

    for entry in sorted(READINGS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in IGNORE_NAMES:
            continue
        if any(entry.name.startswith(p) for p in IGNORE_PREFIXES):
            continue

        cat = process_category(entry)
        if cat:
            categories.append(cat)

    manifest = {"categories": categories}
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {MANIFEST_PATH} ({len(categories)} categories)")
    for cat in categories:
        print(f"  [{cat['id']}] {cat['title']} — {len(cat['articles'])} articles")


if __name__ == "__main__":
    generate()
