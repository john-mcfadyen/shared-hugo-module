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

try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Paths
SCRIPT_DIR = Path(__file__).parent
SHARED_MODULE = SCRIPT_DIR.parent
GSM_ROOT = SHARED_MODULE.parent / "growingscrummasters.com"
COURSES_DIR = GSM_ROOT / "content" / "courses"
WORKSHOPS_DIR = GSM_ROOT / "content" / "workshops"
OUTPUT_FILE = SHARED_MODULE / "data" / "gsm_training.yaml"

GSM_BASE_URL = "https://www.growingscrummasters.com"


def parse_front_matter(file_path: Path) -> dict:
    """Parse YAML or TOML front matter from a markdown file."""
    content = file_path.read_text(encoding="utf-8")

    # Try YAML front matter (---)
    yaml_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if yaml_match:
        try:
            return yaml.safe_load(yaml_match.group(1)) or {}
        except yaml.YAMLError:
            return {}

    # Try TOML front matter (+++)
    toml_match = re.match(r"^\+\+\+\s*\n(.*?)\n\+\+\+", content, re.DOTALL)
    if toml_match:
        try:
            return tomllib.loads(toml_match.group(1)) or {}
        except Exception:
            return {}

    return {}


def get_all_upcoming_dates(course_dir: Path, course_title: str, course_slug: str, item_type: str = "course", seal_or_icon: str = "") -> List[Dict]:
    """Get all upcoming dates for a course or workshop."""
    now = datetime.now(timezone.utc)
    dates = []

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

            date_entry = {
                "type": item_type,
                "title": course_title,
                "slug": course_slug,
                "url": f"{GSM_BASE_URL}/{item_type}s/{course_slug}/",
                "startDate": str(fm.get("courseStartDate")),
                "finishDate": str(fm.get("courseFinishDate", "")),
                "startTime": fm.get("courseStartTime", ""),
                "finishTime": fm.get("courseFinishTime", ""),
                "location": fm.get("courseLocation", ""),
                "price": fm.get("coursePrice", ""),
                "trainer": fm.get("courseTrainer", ""),
                "link": fm.get("courseLink", ""),
                "_sort": start_date.isoformat(),  # For sorting
            }
            # Add seal image for courses or icon for workshops
            if seal_or_icon:
                if item_type == "course":
                    date_entry["sealImage"] = seal_or_icon
                else:
                    date_entry["icon"] = seal_or_icon
            dates.append(date_entry)

        except (ValueError, TypeError):
            continue

    return dates


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


def export_courses() -> tuple:
    """Export all non-private, non-draft courses."""
    courses = []
    all_dates = []

    if not COURSES_DIR.exists():
        print(f"  Warning: Courses directory not found: {COURSES_DIR}")
        return courses, all_dates

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
        title = fm.get("title", slug)
        course = {
            "slug": slug,
            "title": title,
            "description": fm.get("description", ""),
            "url": f"{GSM_BASE_URL}/courses/{slug}/",
            "price": fm.get("price", ""),
            "duration": fm.get("duration", ""),
            "format": fm.get("format", ""),
            "level": fm.get("workshopLevel", ""),
            "sealImage": fm.get("sealImage", ""),
            "benefitSummary": fm.get("benefit_summary", ""),
        }

        # Get all upcoming dates (pass seal image for courses)
        seal_image = fm.get("sealImage", "")
        upcoming_dates = get_all_upcoming_dates(course_dir, title, slug, "course", seal_image)
        all_dates.extend(upcoming_dates)

        # Get next upcoming date if available
        next_date = get_next_date(course_dir)
        if next_date:
            course["nextDate"] = next_date

        courses.append(course)
        print(f"  + Course: {course['title']} ({len(upcoming_dates)} dates)")

    return courses, all_dates


def export_workshops() -> tuple:
    """Export all non-draft workshops."""
    workshops = []
    all_dates = []

    if not WORKSHOPS_DIR.exists():
        print(f"  Warning: Workshops directory not found: {WORKSHOPS_DIR}")
        return workshops, all_dates

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
        title = fm.get("title", slug)
        workshop = {
            "slug": slug,
            "title": title,
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

        # Get all upcoming dates (pass icon for workshops)
        icon = fm.get("icon", "")
        upcoming_dates = get_all_upcoming_dates(workshop_dir, title, slug, "workshop", icon)
        all_dates.extend(upcoming_dates)

        # Get next upcoming date if available
        next_date = get_next_date(workshop_dir)
        if next_date:
            workshop["nextDate"] = next_date

        workshops.append(workshop)
        print(f"  + Workshop: {workshop['title']} ({len(upcoming_dates)} dates)")

    return workshops, all_dates


def main():
    print("GSM Training Export")
    print("=" * 50)

    print("\nExporting courses...")
    courses, course_dates = export_courses()

    print("\nExporting workshops...")
    workshops, workshop_dates = export_workshops()

    # Combine and sort all upcoming dates
    all_dates = course_dates + workshop_dates
    all_dates.sort(key=lambda x: x.get("_sort", ""))

    # Remove sort key from output
    for d in all_dates:
        d.pop("_sort", None)

    # Build output structure
    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": "growingscrummasters.com",
        "baseUrl": GSM_BASE_URL,
        "courses": courses,
        "workshops": workshops,
        "upcomingDates": all_dates,
    }

    # Write YAML file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n{'=' * 50}")
    print(f"Exported {len(courses)} courses and {len(workshops)} workshops")
    print(f"Exported {len(all_dates)} upcoming dates")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
