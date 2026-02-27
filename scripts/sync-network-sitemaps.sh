#!/bin/bash
#
# Sync Network Sitemaps
#
# This script:
# 1. Regenerates the export sitemaps for GSM and JM
# 2. Copies them to all consuming sites
#
# Run from the shared-hugo-module directory or any site directory.
#

set -e

# Find the websites root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBSITES_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "Network Sitemap Sync"
echo "===================="
echo "Websites root: $WEBSITES_ROOT"
echo

# Paths
GSM_ROOT="$WEBSITES_ROOT/growingscrummasters.com"
JM_ROOT="$WEBSITES_ROOT/johnmcfadyen.com"
DA_ROOT="$WEBSITES_ROOT/daily-agile.com"
SA_ROOT="$WEBSITES_ROOT/unleashingthepowerofstoicagile.com"

# Step 1: Regenerate GSM blog sitemap
echo "1. Regenerating GSM blog sitemap..."
if [ -f "$GSM_ROOT/scripts/export-blog-sitemap.py" ]; then
    cd "$GSM_ROOT"
    python3 scripts/export-blog-sitemap.py
    echo "   Done."
else
    echo "   Warning: GSM export script not found, skipping."
fi

echo

# Step 2: Regenerate JM content sitemap
echo "2. Regenerating JM content sitemap..."
if [ -f "$JM_ROOT/scripts/export-content-sitemap.py" ]; then
    cd "$JM_ROOT"
    python3 scripts/export-content-sitemap.py
    echo "   Done."
else
    echo "   Warning: JM export script not found, skipping."
fi

echo

# Step 3: Copy sitemaps to consuming sites
echo "3. Copying sitemaps to consuming sites..."

# GSM sitemap -> daily-agile, stoic-agile
if [ -f "$GSM_ROOT/data/blog_sitemap_curated.yaml" ]; then
    mkdir -p "$DA_ROOT/data" "$SA_ROOT/data"
    cp "$GSM_ROOT/data/blog_sitemap_curated.yaml" "$DA_ROOT/data/gsm_blog_sitemap.yaml"
    cp "$GSM_ROOT/data/blog_sitemap_curated.yaml" "$SA_ROOT/data/gsm_blog_sitemap.yaml"
    echo "   Copied GSM sitemap to daily-agile and stoic-agile"
fi

# JM sitemap -> daily-agile, stoic-agile, GSM
if [ -f "$JM_ROOT/data/content_sitemap_curated.yaml" ]; then
    mkdir -p "$DA_ROOT/data" "$SA_ROOT/data" "$GSM_ROOT/data"
    cp "$JM_ROOT/data/content_sitemap_curated.yaml" "$DA_ROOT/data/jm_content_sitemap.yaml"
    cp "$JM_ROOT/data/content_sitemap_curated.yaml" "$SA_ROOT/data/jm_content_sitemap.yaml"
    cp "$JM_ROOT/data/content_sitemap_curated.yaml" "$GSM_ROOT/data/jm_content_sitemap.yaml"
    echo "   Copied JM sitemap to daily-agile, stoic-agile, and GSM"
fi

echo
echo "===================="
echo "Sync complete!"
echo
echo "To inject network links into a site, run:"
echo "  cd <site-directory>"
echo "  python3 ../shared-hugo-module/scripts/inject-network-links.py --site-root . --dry-run"
echo
echo "Remove --dry-run to apply changes."
