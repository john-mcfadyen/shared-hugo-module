#!/usr/bin/env python3
"""
Export GSM courses and workshops to shared data file for cross-site display.

This script reads course and workshop content from Growing Scrum Masters
and exports a simplified data structure to the shared Hugo module.
"""

import os
import yaml
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List

# Paths
SCRIPT_DIR = Path(__file__).parent
SHARED_MODULE = SCRIPT_DIR.parent
GSM_ROOT = SHARED_MODULE.parent / "growingscrummasters.com"
COURSES_DIR = GSM_ROOT / "content" / "courses"
WORKSHOPS_DIR = GSM_ROOT / "content" / "workshops"
OUTPUT_FILE = SHARED_MODULE / "data" / "gsm_training.yaml"

GSM_BASE_URL = "https://www.growingscrummasters.com"


def parse_front_matter(file_path: Path) -> dict:
    """Parse YAML front matter from a markdown file."""
    content = file_path.read_text(encoding="utf-8")

    # Match YAML front matter between --- markers
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def get_next_date(course_dir: Path) -> Optional[Dict]:
    """Find the next upcoming date for a course."""
    now = datetime.now(timezone.utc)
    next_date = None

    for date_dir in course_dir.iterdir():
        if not date_dir.is_dir() or date_dir.name.startswith("."):
            continue

        index_file = date_dir / "index.md"
        if not index_file.exists():
            continue

        fm = parse_front_matter(index_file)

        # Skip drafts
        if fm.get("draft", False):
            continue

        # Parse course start date
        start_date_str = fm.get("courseStartDate")
        if not start_date_str:
            continue

        try:
            # Parse date (could be various formats)
            if isinstance(start_date_str, datetime):
                start_date = start_date_str
            else:
                start_date = datetime.fromisoformat(str(start_date_str).replace("Z", "+00:00"))

            # Make timezone-aware if needed
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)

            # Skip past dates
            if start_date < now:
                continue

            # Track the earliest upcoming date
            if next_date is None or start_date < next_date["start"]:
                next_date = {
                    "start": start_date,
                    "startDate": fm.get("courseStartDate"),
                    "finishDate": fm.get("courseFinishDate"),
                    "startTime": fm.get("courseStartTime"),
                    "finishTime": fm.get("courseFinishTime"),
                    "location": fm.get("courseLocation"),
                    "price": fm.get("coursePrice"),
                    "link": fm.get("courseLink"),
                }
        except (ValueError, TypeError):
            continue

    if next_date:
        # Remove the datetime object (not YAML-serializable)
        del next_date["start"]
        return next_date

    return None


def export_courses() -> list:
    """Export all non-private, non-draft courses."""
    courses = []

    if not COURSES_DIR.exists():
        print(f"  Warning: Courses directory not found: {COURSES_DIR}")
        return courses

    for course_dir in sorted(COURSES_DIR.iterdir()):
        if not course_dir.is_dir() or course_dir.name.startswith("."):
            continue

        index_file = course_dir / "_index.md"
        if not index_file.exists():
            continue

        fm = parse_front_matter(index_file)

        # Skip drafts and private courses
        if fm.get("draft", False):
            continue
        if fm.get("privateTraining", False):
            continue
        if fm.get("comingSoon", False):
            continue

        # Build course data
        slug = course_dir.name
        course = {
            "slug": slug,
            "title": fm.get("title", slug),
            "description": fm.get("description", ""),
            "url": f"{GSM_BASE_URL}/courses/{slug}/",
            "price": fm.get("price", ""),
            "duration": fm.get("duration", ""),
            "format": fm.get("format", ""),
            "level": fm.get("workshopLevel", ""),
            "sealImage": fm.get("sealImage", ""),
            "benefitSummary": fm.get("benefit_summary", ""),
        }

        # Get next upcoming date if available
        next_date = get_next_date(course_dir)
        if next_date:
            course["nextDate"] = next_date

        courses.append(course)
        print(f"  + Course: {course['title']}")

    return courses


def export_workshops() -> list:
    """Export all non-draft workshops."""
    workshops = []

    if not WORKSHOPS_DIR.exists():
        print(f"  Warning: Workshops directory not found: {WORKSHOPS_DIR}")
        return workshops

    for workshop_dir in sorted(WORKSHOPS_DIR.iterdir()):
        if not workshop_dir.is_dir() or workshop_dir.name.startswith("."):
            continue

        index_file = workshop_dir / "_index.md"
        if not index_file.exists():
            continue

        fm = parse_front_matter(index_file)

        # Skip drafts and coming soon
        if fm.get("draft", False):
            continue
        if fm.get("comingSoon", False):
            continue

        # Build workshop data
        slug = workshop_dir.name
        workshop = {
            "slug": slug,
            "title": fm.get("title", slug),
            "description": fm.get("description", ""),
            "url": f"{GSM_BASE_URL}/workshops/{slug}/",
            "price": fm.get("price", ""),
            "duration": fm.get("duration", ""),
            "format": fm.get("format", ""),
            "level": fm.get("workshopLevel", ""),
            "track": fm.get("track", ""),
            "icon": fm.get("icon", ""),
            "benefitSummary": fm.get("benefit_summary", ""),
        }

        # Get next upcoming date if available
        next_date = get_next_date(workshop_dir)
        if next_date:
            workshop["nextDate"] = next_date

        workshops.append(workshop)
        print(f"  + Workshop: {workshop['title']}")

    return workshops


def main():
    print("GSM Training Export")
    print("=" * 50)

    print("\nExporting courses...")
    courses = export_courses()

    print("\nExporting workshops...")
    workshops = export_workshops()

    # Build output structure
    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": "growingscrummasters.com",
        "baseUrl": GSM_BASE_URL,
        "courses": courses,
        "workshops": workshops,
    }

    # Write YAML file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n{'=' * 50}")
    print(f"Exported {len(courses)} courses and {len(workshops)} workshops")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
