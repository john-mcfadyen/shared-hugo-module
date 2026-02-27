#!/usr/bin/env python3
"""
Internal Link Injection Script

Injects internal links into blog posts based on the internal_links.json registry.
Uses anchor terms from related pages to find natural insertion points.

Configuration via data/internal_linking_config.yaml in each site.

Features:
- Skips first 300 words (introduction protection)
- Respects existing internal links
- Limits links per post
- Prioritizes longer/more specific anchor terms
- Dry-run mode for preview
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

# Default configuration
DEFAULT_CONFIG = {
    'max_links_per_post': 3,
    'min_word_count': 300,
    'skip_first_words': 300,  # Don't inject links in first N words
    'min_anchor_length': 5,
    'excluded_terms': ['agile', 'scrum', 'team', 'sprint', 'the', 'and', 'for'],
}


def load_config(data_dir: Path) -> dict:
    """Load internal linking configuration."""
    config_path = data_dir / 'internal_linking_config.yaml'

    if not config_path.exists():
        # Fall back to defaults
        return DEFAULT_CONFIG.copy()

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # Merge with defaults
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def load_link_registry(data_dir: Path) -> dict:
    """Load the internal links registry."""
    registry_path = data_dir / 'internal_links.json'

    if not registry_path.exists():
        print(f"Error: Link registry not found at {registry_path}")
        print("Run generate-internal-links.py first to create the registry.")
        return {}

    with open(registry_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def parse_front_matter(content: str) -> tuple[dict, str, str]:
    """Parse front matter and return (front_matter, body, format)."""
    # Try TOML format (+++)
    toml_match = re.match(r'^(\+\+\+\s*\n.*?\n\+\+\+\s*\n?)', content, re.DOTALL)
    if toml_match:
        fm_block = toml_match.group(1)
        body = content[len(fm_block):]
        try:
            import tomllib
            fm_text = re.search(r'^\+\+\+\s*\n(.*?)\n\+\+\+', fm_block, re.DOTALL).group(1)
            front_matter = tomllib.loads(fm_text)
        except:
            front_matter = {}
        return front_matter, body, 'toml'

    # Try YAML format (---)
    yaml_match = re.match(r'^(---\s*\n.*?\n---\s*\n?)', content, re.DOTALL)
    if yaml_match:
        fm_block = yaml_match.group(1)
        body = content[len(fm_block):]
        try:
            fm_text = re.search(r'^---\s*\n(.*?)\n---', fm_block, re.DOTALL).group(1)
            front_matter = yaml.safe_load(fm_text) or {}
        except:
            front_matter = {}
        return front_matter, body, 'yaml'

    return {}, content, 'none'


def get_word_count(body: str) -> int:
    """Get word count of body content."""
    text = re.sub(r'<[^>]+>', '', body)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'{{<[^>]+>}}', '', text)
    return len(text.split())


def get_char_position_after_n_words(text: str, n_words: int) -> int:
    """
    Get the character position in text after N words.
    Used to skip the introduction/first N words when injecting links.
    """
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


def has_link_to_path(body: str, target_path: str) -> bool:
    """Check if body already contains a link to the target path."""
    # Check for markdown links to this path
    # Handle both relative and absolute paths
    escaped_path = re.escape(target_path.rstrip('/'))
    pattern = rf'\[([^\]]+)\]\({escaped_path}/?(?:\s*"[^"]*")?\)'
    return bool(re.search(pattern, body))


def find_anchor_matches(body: str, anchor_terms: list[str], target_path: str,
                        excluded_terms: list[str], skip_first_words: int = 0,
                        min_anchor_length: int = 5) -> list[dict]:
    """Find all anchor term matches in the body."""
    matches = []

    # Calculate minimum position (skip first N words)
    min_position = get_char_position_after_n_words(body, skip_first_words)

    # Track matched positions to avoid overlaps
    matched_positions = set()

    for anchor in anchor_terms:
        anchor_lower = anchor.lower()

        # Skip excluded terms
        if anchor_lower in [t.lower() for t in excluded_terms]:
            continue

        # Skip short anchors
        if len(anchor) < min_anchor_length:
            continue

        # Find occurrences (word boundary matching)
        try:
            pattern = re.compile(rf'\b({re.escape(anchor)})\b', re.IGNORECASE)
        except re.error:
            continue

        for match in pattern.finditer(body):
            start, end = match.span()

            # Skip matches in first N words
            if start < min_position:
                continue

            # Check for overlaps
            if any(start < mp_end and end > mp_start for mp_start, mp_end in matched_positions):
                continue

            # Check if already inside a link
            before = body[max(0, start-50):start]
            if '[' in before and '](' not in before:
                continue

            # Check if inside HTML tag
            if '<' in before and '>' not in before[before.rfind('<'):]:
                continue

            matches.append({
                'anchor': match.group(1),
                'target_path': target_path,
                'start': start,
                'end': end,
                'length': len(anchor),
            })

            matched_positions.add((start, end))
            # Only use first match per anchor term
            break

    # Sort by length (prefer longer/more specific anchors)
    matches.sort(key=lambda x: -x['length'])

    return matches


def inject_links(body: str, matches: list[dict], max_links: int) -> tuple[str, list[dict]]:
    """Inject links into body content. Returns (new_body, injected_links)."""
    if not matches:
        return body, []

    # Limit matches
    to_inject = matches[:max_links]

    # Sort by position (reverse) to inject from end to start
    to_inject.sort(key=lambda x: -x['start'])

    injected = []
    new_body = body

    for match in to_inject:
        start = match['start']
        end = match['end']
        anchor = match['anchor']
        target_path = match['target_path']

        # Create markdown link
        link_md = f"[{anchor}]({target_path})"

        # Replace in body
        new_body = new_body[:start] + link_md + new_body[end:]

        injected.append({
            'anchor': anchor,
            'target_path': target_path,
        })

    return new_body, injected


def get_post_path_from_file(file_path: Path, content_dir: Path) -> str:
    """Convert file path to URL path."""
    rel_path = file_path.relative_to(content_dir)

    if file_path.name == 'index.md':
        return "/" + str(rel_path.parent) + "/"
    else:
        return "/" + str(rel_path).replace(".md", "/")


def process_posts(content_dir: Path, blog_subdir: str, registry: dict, config: dict,
                  dry_run: bool = False) -> dict:
    """Process all blog posts and inject internal links."""

    max_links_per_post = config['max_links_per_post']
    min_word_count = config['min_word_count']
    skip_first_words = config.get('skip_first_words', 300)
    min_anchor_length = config.get('min_anchor_length', 5)
    excluded_terms = config.get('excluded_terms', [])

    pages = registry.get('pages', {})

    stats = {
        'total_posts': 0,
        'too_short': 0,
        'no_targets': 0,
        'no_matches': 0,
        'already_linked': 0,
        'newly_linked': 0,
        'links_injected': 0,
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

    if not all_posts:
        print("No posts found!")
        return stats

    for post_path in all_posts:
        try:
            content = post_path.read_text(encoding='utf-8')
        except Exception as e:
            continue

        front_matter, body, fm_format = parse_front_matter(content)
        word_count = get_word_count(body)

        if word_count < min_word_count:
            stats['too_short'] += 1
            continue

        # Get this post's path and find its outbound targets
        post_url_path = get_post_path_from_file(post_path, content_dir)
        page_data = pages.get(post_url_path, {})
        outbound_targets = page_data.get('outbound_targets', [])

        if not outbound_targets:
            stats['no_targets'] += 1
            continue

        # Build list of potential links from targets
        all_matches = []
        for target in outbound_targets:
            target_path = target.get('path', '')
            target_data = pages.get(target_path, {})
            anchor_terms = target_data.get('anchor_terms', [])

            if not anchor_terms:
                continue

            # Skip if already linked to this target
            if has_link_to_path(body, target_path):
                continue

            matches = find_anchor_matches(
                body, anchor_terms, target_path,
                excluded_terms, skip_first_words, min_anchor_length
            )
            all_matches.extend(matches)

        if not all_matches:
            stats['no_matches'] += 1
            continue

        # Deduplicate by target path (one link per target)
        seen_targets = set()
        unique_matches = []
        for m in all_matches:
            if m['target_path'] not in seen_targets:
                unique_matches.append(m)
                seen_targets.add(m['target_path'])

        # Inject links
        new_body, injected = inject_links(body, unique_matches, max_links_per_post)

        if not injected:
            stats['no_matches'] += 1
            continue

        # Reconstruct content
        if fm_format == 'toml':
            fm_match = re.match(r'^(\+\+\+\s*\n.*?\n\+\+\+\s*\n?)', content, re.DOTALL)
            new_content = fm_match.group(1) + new_body if fm_match else new_body
        elif fm_format == 'yaml':
            fm_match = re.match(r'^(---\s*\n.*?\n---\s*\n?)', content, re.DOTALL)
            new_content = fm_match.group(1) + new_body if fm_match else new_body
        else:
            new_content = new_body

        # Write back (unless dry run)
        if not dry_run:
            post_path.write_text(new_content, encoding='utf-8')

        stats['newly_linked'] += 1
        stats['links_injected'] += len(injected)
        stats['details'].append({
            'post': str(post_path.relative_to(content_dir)),
            'links': injected,
        })

        # Print progress
        post_name = post_path.parent.name if post_path.name == 'index.md' else post_path.stem
        action = "[DRY RUN] Would inject" if dry_run else "Injected"
        print(f"  {action} {len(injected)} link(s) into: {post_name}")
        for link in injected:
            print(f"    - \"{link['anchor']}\" -> {link['target_path']}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Inject internal links into blog posts')
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
        # Try 'articles' as fallback
        blog_subdir = 'articles'
        blog_dir = content_dir / blog_subdir
    if not blog_dir.exists():
        print(f"Error: No blog or articles directory found in {content_dir}")
        return 1

    print("Internal Link Injector")
    print("=" * 50)
    print(f"Site root: {site_root}")
    print(f"Blog directory: {blog_dir}")
    if args.dry_run:
        print("MODE: Dry run (no files will be modified)")
    print()

    # Load configuration
    print("Loading configuration...")
    config = load_config(data_dir)

    print(f"  Max links per post: {config['max_links_per_post']}")
    print(f"  Skip first words: {config.get('skip_first_words', 300)}")
    print()

    # Load link registry
    print("Loading link registry...")
    registry = load_link_registry(data_dir)

    if not registry:
        return 1

    pages = registry.get('pages', {})
    print(f"  Pages in registry: {len(pages)}")
    print()

    # Process posts
    print("Processing posts...")
    stats = process_posts(content_dir, blog_subdir, registry, config, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Total posts scanned: {stats['total_posts']}")
    print(f"  Too short (skipped): {stats['too_short']}")
    print(f"  No outbound targets: {stats['no_targets']}")
    print(f"  No matching anchors: {stats['no_matches']}")
    print(f"  Newly linked: {stats['newly_linked']}")
    print(f"  Links injected: {stats['links_injected']}")

    if args.dry_run and stats['newly_linked'] > 0:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
