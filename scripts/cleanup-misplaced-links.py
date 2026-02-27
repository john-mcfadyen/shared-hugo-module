#!/usr/bin/env python3
"""
Cleanup Misplaced Links Script

Removes internal links that were incorrectly placed in:
- Markdown headings (lines starting with #)
- The first N words of a post (introduction)

Usage:
    python scripts/cleanup-misplaced-links.py --site-root /path/to/site [--dry-run]
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

# Default configuration
DEFAULT_CONFIG = {
    'skip_first_words': 300,
}


def load_config(data_dir: Path) -> dict:
    """Load configuration from internal_linking_config.yaml."""
    config_path = data_dir / 'internal_linking_config.yaml'

    if not config_path.exists():
        return DEFAULT_CONFIG.copy()

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def parse_front_matter(content: str) -> tuple[str, str, str]:
    """Parse front matter and return (fm_block, body, format)."""
    # Try TOML format (+++)
    toml_match = re.match(r'^(\+\+\+\s*\n.*?\n\+\+\+\s*\n?)', content, re.DOTALL)
    if toml_match:
        fm_block = toml_match.group(1)
        body = content[len(fm_block):]
        return fm_block, body, 'toml'

    # Try YAML format (---)
    yaml_match = re.match(r'^(---\s*\n.*?\n---\s*\n?)', content, re.DOTALL)
    if yaml_match:
        fm_block = yaml_match.group(1)
        body = content[len(fm_block):]
        return fm_block, body, 'yaml'

    return '', content, 'none'


def get_char_position_after_n_words(text: str, n_words: int) -> int:
    """Get the character position in text after N words."""
    if n_words <= 0:
        return 0

    words_found = 0
    in_word = False

    for i, char in enumerate(text):
        if char.isspace():
            if in_word:
                words_found += 1
                if words_found >= n_words:
                    return i
            in_word = False
        else:
            in_word = True

    return len(text)


def is_in_heading(body: str, position: int) -> bool:
    """Check if position is on a line that starts with #."""
    line_start = body.rfind('\n', 0, position) + 1
    line_content = body[line_start:position]
    return line_content.lstrip().startswith('#')


def cleanup_links(body: str, skip_first_words: int) -> tuple[str, list[dict]]:
    """
    Remove links that are in headings or in the first N words.
    Returns (cleaned_body, list of removed links).
    """
    # Calculate the position after first N words
    intro_end_pos = get_char_position_after_n_words(body, skip_first_words)

    # Find all markdown links: [text](url)
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

    removed = []

    # Process matches in reverse order to preserve positions
    matches = list(link_pattern.finditer(body))
    matches.reverse()

    new_body = body

    for match in matches:
        start, end = match.span()
        anchor_text = match.group(1)
        url = match.group(2)

        # Check if this link should be removed
        should_remove = False
        reason = None

        # Check if in first N words
        if start < intro_end_pos:
            should_remove = True
            reason = 'first_300_words'

        # Check if in heading
        if is_in_heading(body, start):
            should_remove = True
            reason = 'heading'

        if should_remove:
            # Replace link with just the anchor text
            new_body = new_body[:start] + anchor_text + new_body[end:]
            removed.append({
                'anchor': anchor_text,
                'url': url,
                'reason': reason,
            })

    return new_body, removed


def process_posts(content_dir: Path, blog_subdir: str, config: dict,
                  dry_run: bool = False) -> dict:
    """Process all posts and cleanup misplaced links."""

    skip_first_words = config.get('skip_first_words', 300)

    stats = {
        'total_posts': 0,
        'posts_cleaned': 0,
        'links_removed': 0,
        'in_headings': 0,
        'in_intro': 0,
        'details': [],
    }

    blog_dir = content_dir / blog_subdir
    if not blog_dir.exists():
        print(f"Blog directory not found: {blog_dir}")
        return stats

    # Collect all posts
    all_posts = list(blog_dir.glob('*/index.md')) + list(blog_dir.glob('*.md'))
    all_posts = [p for p in all_posts if p.name != '_index.md']

    stats['total_posts'] = len(all_posts)

    for post_path in all_posts:
        try:
            content = post_path.read_text(encoding='utf-8')
        except Exception as e:
            continue

        fm_block, body, fm_format = parse_front_matter(content)

        # Cleanup misplaced links
        new_body, removed = cleanup_links(body, skip_first_words)

        if not removed:
            continue

        # Count by reason
        for link in removed:
            if link['reason'] == 'heading':
                stats['in_headings'] += 1
            elif link['reason'] == 'first_300_words':
                stats['in_intro'] += 1

        # Reconstruct content
        new_content = fm_block + new_body

        # Write back (unless dry run)
        if not dry_run:
            post_path.write_text(new_content, encoding='utf-8')

        stats['posts_cleaned'] += 1
        stats['links_removed'] += len(removed)
        stats['details'].append({
            'post': str(post_path.relative_to(content_dir)),
            'removed': removed,
        })

        # Print progress
        post_name = post_path.parent.name if post_path.name == 'index.md' else post_path.stem
        action = "[DRY RUN] Would remove" if dry_run else "Removed"
        print(f"  {action} {len(removed)} link(s) from: {post_name}")
        for link in removed:
            print(f"    - \"{link['anchor']}\" ({link['reason']})")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Cleanup misplaced links in blog posts')
    parser.add_argument('--site-root', '-r', type=Path, required=True,
                        help='Root directory of the site')
    parser.add_argument('--blog-dir', '-b', type=str, default='blog',
                        help='Blog subdirectory name (default: blog)')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Preview changes without writing files')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    site_root = args.site_root.resolve()
    data_dir = site_root / 'data'
    content_dir = site_root / 'content'

    # Determine blog directory
    blog_subdir = args.blog_dir
    blog_dir = content_dir / blog_subdir
    if not blog_dir.exists():
        blog_subdir = 'articles'
        blog_dir = content_dir / blog_subdir
    if not blog_dir.exists():
        print(f"Error: No blog or articles directory found in {content_dir}")
        return 1

    print("Misplaced Link Cleanup")
    print("=" * 50)
    print(f"Site root: {site_root}")
    print(f"Blog directory: {blog_dir}")
    if args.dry_run:
        print("MODE: Dry run (no files will be modified)")
    print()

    # Load configuration
    print("Loading configuration...")
    config = load_config(data_dir)
    print(f"  Skip first words: {config.get('skip_first_words', 300)}")
    print()

    # Process posts
    print("Scanning posts for misplaced links...")
    stats = process_posts(content_dir, blog_subdir, config, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Total posts scanned: {stats['total_posts']}")
    print(f"  Posts with issues: {stats['posts_cleaned']}")
    print(f"  Links removed: {stats['links_removed']}")
    print(f"    - In headings: {stats['in_headings']}")
    print(f"    - In first 300 words: {stats['in_intro']}")

    if args.dry_run and stats['links_removed'] > 0:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
