#!/usr/bin/env python3
"""
Network Link Injection Script

Injects links to other sites in the network into blog posts.
Reads exported sitemaps from target sites and finds matching anchor terms.

Configuration via data/network_linking_config.yaml in each site.

Features:
- 70% maximum threshold for network-linked posts (configurable)
- Respects existing network links
- Limits links per post
- Prioritizes longer/more specific anchor terms
- Dry-run mode for preview
"""

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

# Network link marker comment (to identify injected links)
NETWORK_LINK_MARKER = "<!-- network-link -->"

# Default configuration
DEFAULT_CONFIG = {
    'max_network_linked_posts_percent': 70,
    'max_links_per_post': 2,
    'min_word_count': 300,
    'min_anchor_length': 5,
    'skip_first_words': 300,  # Don't inject links in first N words
    'excluded_terms': ['agile', 'scrum', 'team', 'sprint'],
}


def load_config(data_dir: Path) -> dict:
    """Load network linking configuration."""
    config_path = data_dir / 'network_linking_config.yaml'

    if not config_path.exists():
        print(f"Warning: No config found at {config_path}, using defaults")
        return DEFAULT_CONFIG.copy()

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    # Merge with defaults
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def load_network_sitemaps(data_dir: Path, sources: list[dict]) -> list[dict]:
    """Load external sitemaps from network sources."""
    all_links = []

    for source in sources:
        source_name = source.get('name', 'unknown')
        sitemap_file = source.get('sitemap_file')

        if not sitemap_file:
            print(f"Warning: No sitemap_file specified for source {source_name}")
            continue

        sitemap_path = data_dir / sitemap_file
        if not sitemap_path.exists():
            print(f"Warning: Sitemap not found: {sitemap_path}")
            continue

        with open(sitemap_path, 'r', encoding='utf-8') as f:
            sitemap_data = yaml.safe_load(f) or {}

        # Handle both 'links' and 'posts' keys (different export formats)
        links = sitemap_data.get('links', sitemap_data.get('posts', []))

        for link in links:
            link['_source'] = source_name
            link['_priority'] = source.get('priority', 1)
            all_links.append(link)

        print(f"  Loaded {len(links)} links from {source_name}")

    return all_links


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
    # Strip markdown/HTML
    text = re.sub(r'<[^>]+>', '', body)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'{{<[^>]+>}}', '', text)
    return len(text.split())


def get_char_position_after_n_words(text: str, n_words: int) -> int:
    """
    Get the character position in text after N words.
    Used to skip the introduction/first N words when injecting links.
    Returns 0 if n_words is 0, or len(text) if text has fewer words.
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

    # Text has fewer words than n_words, return end of text
    return len(text)


def has_network_links(body: str, target_domains: list[str]) -> bool:
    """Check if body already contains network links to target domains."""
    for domain in target_domains:
        if domain in body:
            return True
    return False


def count_existing_network_links(body: str, target_domains: list[str]) -> int:
    """Count existing network links in the body."""
    count = 0
    for domain in target_domains:
        # Count markdown links to this domain
        pattern = rf'\[([^\]]+)\]\(https?://[^)]*{re.escape(domain)}[^)]*\)'
        count += len(re.findall(pattern, body))
    return count


def find_anchor_matches(body: str, links: list[dict], excluded_terms: list[str],
                        skip_first_words: int = 0) -> list[dict]:
    """Find all anchor term matches in the body, skipping first N words."""
    matches = []
    body_lower = body.lower()

    # Calculate minimum position (skip first N words)
    min_position = get_char_position_after_n_words(body, skip_first_words)

    # Track which positions have been matched to avoid overlaps
    matched_positions = set()

    # Track which anchor terms (lowercase) have been matched to avoid duplicate anchors
    matched_anchors = set()

    # Track which URLs have been matched to avoid linking to same URL twice
    matched_urls = set()

    for link in links:
        anchor_terms = link.get('anchor_terms', [])
        url = link.get('url', '')

        if not url or not anchor_terms:
            continue

        # Skip if we already have a link to this URL
        if url in matched_urls:
            continue

        for anchor in anchor_terms:
            anchor_lower = anchor.lower()

            # Skip excluded terms
            if anchor_lower in [t.lower() for t in excluded_terms]:
                continue

            # Skip very short anchors
            if len(anchor) < 5:
                continue

            # Skip if this anchor text was already used for another link
            if anchor_lower in matched_anchors:
                continue

            # Find all occurrences (word boundary matching)
            try:
                pattern = re.compile(rf'\b({re.escape(anchor)})\b', re.IGNORECASE)
            except re.error:
                continue

            for match in pattern.finditer(body):
                start, end = match.span()

                # Skip matches in the first N words (introduction protection)
                if start < min_position:
                    continue

                # Check if this position overlaps with existing match
                if any(start < mp_end and end > mp_start for mp_start, mp_end in matched_positions):
                    continue

                # Check if already inside a link
                before = body[max(0, start-50):start]
                if '[' in before and '](' not in before:
                    continue

                # Check if inside HTML tag
                if '<' in before and '>' not in before[before.rfind('<'):]:
                    continue

                # Check if inside a markdown heading
                line_start = body.rfind('\n', 0, start) + 1
                line_content = body[line_start:start]
                if line_content.lstrip().startswith('#'):
                    continue

                matches.append({
                    'anchor': match.group(1),  # Preserve original case
                    'url': url,
                    'start': start,
                    'end': end,
                    'length': len(anchor),
                    'priority': link.get('_priority', 1),
                    'source': link.get('_source', 'unknown'),
                })

                # Mark this position, anchor, and URL as matched
                matched_positions.add((start, end))
                matched_anchors.add(anchor_lower)
                matched_urls.add(url)

                # Only match first occurrence per anchor term, then move to next link
                break

    # Sort by priority (higher first), then by length (longer first)
    matches.sort(key=lambda x: (-x['priority'], -x['length']))

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
        url = match['url']

        # Create markdown link
        link_md = f"[{anchor}]({url})"

        # Replace in body
        new_body = new_body[:start] + link_md + new_body[end:]

        injected.append({
            'anchor': anchor,
            'url': url,
            'source': match['source'],
        })

    return new_body, injected


def process_posts(blog_dir: Path, links: list[dict], config: dict,
                  target_domains: list[str], dry_run: bool = False) -> dict:
    """Process all blog posts and inject network links."""

    max_percent = config['max_network_linked_posts_percent']
    max_links_per_post = config['max_links_per_post']
    min_word_count = config['min_word_count']
    skip_first_words = config.get('skip_first_words', 300)
    excluded_terms = config.get('excluded_terms', [])

    stats = {
        'total_posts': 0,
        'already_linked': 0,
        'too_short': 0,
        'no_matches': 0,
        'newly_linked': 0,
        'skipped_threshold': 0,
        'links_injected': 0,
        'details': [],
    }

    # Collect all eligible posts
    all_posts = list(blog_dir.glob('*/index.md')) + list(blog_dir.glob('*.md'))
    # Filter out _index.md files
    all_posts = [p for p in all_posts if p.name != '_index.md']

    stats['total_posts'] = len(all_posts)

    if not all_posts:
        print("No posts found!")
        return stats

    # Calculate threshold
    max_linked = int(len(all_posts) * max_percent / 100)

    # First pass: count already linked posts
    already_linked_posts = []
    eligible_posts = []

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

        if has_network_links(body, target_domains):
            stats['already_linked'] += 1
            already_linked_posts.append(post_path)
        else:
            eligible_posts.append((post_path, content, body, fm_format))

    # Calculate remaining slots
    remaining_slots = max_linked - len(already_linked_posts)

    if remaining_slots <= 0:
        print(f"Already at or above {max_percent}% threshold ({len(already_linked_posts)}/{len(all_posts)} posts linked)")
        stats['skipped_threshold'] = len(eligible_posts)
        return stats

    print(f"Threshold: {max_linked} posts ({max_percent}%), already linked: {len(already_linked_posts)}, slots available: {remaining_slots}")

    # Shuffle eligible posts for randomness
    random.shuffle(eligible_posts)

    # Process eligible posts up to remaining slots
    posts_to_link = eligible_posts[:remaining_slots]

    for post_path, content, body, fm_format in posts_to_link:
        # Find anchor matches (skipping first N words)
        matches = find_anchor_matches(body, links, excluded_terms, skip_first_words)

        if not matches:
            stats['no_matches'] += 1
            continue

        # Inject links
        new_body, injected = inject_links(body, matches, max_links_per_post)

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
            'post': str(post_path.relative_to(blog_dir.parent)),
            'links': injected,
        })

        # Print progress
        post_name = post_path.parent.name if post_path.name == 'index.md' else post_path.stem
        action = "[DRY RUN] Would inject" if dry_run else "Injected"
        print(f"  {action} {len(injected)} link(s) into: {post_name}")
        for link in injected:
            print(f"    - \"{link['anchor']}\" -> {link['url']}")

    # Count skipped due to threshold
    stats['skipped_threshold'] = len(eligible_posts) - len(posts_to_link) - stats['no_matches']

    return stats


def main():
    parser = argparse.ArgumentParser(description='Inject network links into blog posts')
    parser.add_argument('--site-root', '-r', type=Path, required=True,
                        help='Root directory of the site')
    parser.add_argument('--dry-run', '-n', action='store_true',
                        help='Preview changes without writing files')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    site_root = args.site_root.resolve()
    data_dir = site_root / 'data'
    content_dir = site_root / 'content'

    # Find blog directory (could be 'blog' or 'articles')
    blog_dir = content_dir / 'blog'
    if not blog_dir.exists():
        blog_dir = content_dir / 'articles'
    if not blog_dir.exists():
        print(f"Error: No blog or articles directory found in {content_dir}")
        return 1

    print("Network Link Injector")
    print("=" * 50)
    print(f"Site root: {site_root}")
    print(f"Blog directory: {blog_dir}")
    if args.dry_run:
        print("MODE: Dry run (no files will be modified)")
    print()

    # Load configuration
    print("Loading configuration...")
    config = load_config(data_dir)

    sources = config.get('sources', [])
    if not sources:
        print("Error: No sources configured in network_linking_config.yaml")
        return 1

    print(f"  Max network-linked posts: {config['max_network_linked_posts_percent']}%")
    print(f"  Max links per post: {config['max_links_per_post']}")
    print(f"  Skip first words: {config.get('skip_first_words', 300)}")
    print(f"  Sources: {len(sources)}")

    # Collect target domains for checking existing links
    target_domains = []
    for source in sources:
        domain = source.get('domain', '')
        if domain:
            target_domains.append(domain)

    # Load network sitemaps
    print("\nLoading network sitemaps...")
    links = load_network_sitemaps(data_dir, sources)

    if not links:
        print("Error: No links loaded from sitemaps")
        return 1

    print(f"  Total links available: {len(links)}")

    # Process posts
    print("\nProcessing posts...")
    stats = process_posts(blog_dir, links, config, target_domains, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 50)
    print("Summary")
    print("=" * 50)
    print(f"  Total posts scanned: {stats['total_posts']}")
    print(f"  Already had network links: {stats['already_linked']}")
    print(f"  Too short (skipped): {stats['too_short']}")
    print(f"  No matching anchors: {stats['no_matches']}")
    print(f"  Skipped (threshold): {stats['skipped_threshold']}")
    print(f"  Newly linked: {stats['newly_linked']}")
    print(f"  Links injected: {stats['links_injected']}")

    # Calculate final percentage
    total_linked = stats['already_linked'] + stats['newly_linked']
    eligible = stats['total_posts'] - stats['too_short']
    if eligible > 0:
        pct = (total_linked / eligible) * 100
        print(f"\n  Network-linked posts: {total_linked}/{eligible} ({pct:.1f}%)")

    if args.dry_run and stats['newly_linked'] > 0:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")

    return 0


if __name__ == '__main__':
    sys.exit(main())
