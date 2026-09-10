"""
OpenLearn public course catalogue collector.

The collector uses OpenLearn's public "All our free courses" catalogue.
It paginates through the catalogue and extracts the course-card metadata
that is visibly published by OpenLearn.

Source:
https://www.open.edu/openlearn/free-courses/full-catalogue

The public catalogue currently exposes filters for:
- subject
- course type
- level
- resource length
- language

The collector deliberately does not invent course IDs, languages, or other
values that are not present in the catalogue card. Such fields remain N/A.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.open.edu"
CATALOGUE_URL = f"{BASE_URL}/openlearn/free-courses/full-catalogue"
TIMEOUT = 30
REQUEST_DELAY_SECONDS = 0.5

COMMON_COLUMNS = [
    "Course Name",
    "Provider",
    "Course ID / Code",
    "Subject / Category",
    "Course Type",
    "Level",
    "Duration / Resource Length",
    "Language",
    "Semester / Year",
    "Course URL",
    "Collection Date",
]


def get_page(page: int) -> str:
    """Download one public OpenLearn catalogue page."""
    params = {"page": page} if page > 1 else None
    response = requests.get(
        CATALOGUE_URL,
        params=params,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; EdulenzaCourseResearch/1.0; "
                "+https://github.com/)"
            )
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def is_course_url(href: str) -> bool:
    """Accept OpenLearn course/resource URLs, not navigation links."""
    parsed = urlparse(href)
    if parsed.netloc and parsed.netloc not in {"www.open.edu", "open.edu"}:
        return False

    path = parsed.path.rstrip("/")
    return (
        path.startswith("/openlearn/")
        and path != "/openlearn/free-courses/full-catalogue"
        and "/free-courses/full-catalogue" not in path
    )


def extract_level(text: str) -> str:
    match = re.search(
        r"Level\s+(?:level\s+)?(1|2|3)\s*:\s*([A-Za-z -]+)",
        text,
        flags=re.I,
    )
    if match:
        return f"Level {match.group(1)}: {clean_text(match.group(2)).lower()}"
    return "N/A"


def extract_duration(text: str) -> str:
    match = re.search(r"\b(\d+)\s*hrs?\b", text, flags=re.I)
    return f"{match.group(1)} hrs" if match else "N/A"


def extract_card(anchor: Tag) -> dict[str, str] | None:
    """
    Convert a course-card anchor into a normalized record.

    OpenLearn's catalogue markup can change over time, so extraction is
    intentionally based on stable content patterns rather than one brittle
    CSS class name.
    """
    href = anchor.get("href", "")
    if not isinstance(href, str) or not is_course_url(href):
        return None

    # Find a reasonably sized parent containing the course-card content.
    parent: Tag | None = anchor
    for _ in range(6):
        if parent is None:
            break
        text = clean_text(parent.get_text(" ", strip=True))
        if len(text) >= 20 and (
            "Level" in text or "hrs" in text or "hours" in text
        ):
            break
        parent = parent.parent if isinstance(parent.parent, Tag) else None

    if parent is None:
        return None

    text = clean_text(parent.get_text(" ", strip=True))

    # Course title is normally the anchor's own visible text.
    title = clean_text(anchor.get_text(" ", strip=True))
    if not title:
        heading = parent.find(["h2", "h3", "h4"])
        title = clean_text(heading.get_text(" ", strip=True)) if heading else ""

    if not title or title.lower() in {
        "view course",
        "read more",
        "learn more",
    }:
        return None

    # Subject/category is typically the taxonomy label shown before the
    # course title. Prefer nearby category links/labels when available.
    category = "N/A"
    for element in parent.find_all(["a", "span", "div", "p"]):
        value = clean_text(element.get_text(" ", strip=True))
        if value in {
            "Money & Business",
            "Education & Development",
            "Health, Sports & Psychology",
            "History & The Arts",
            "Languages",
            "Nature & Environment",
            "Science, Maths & Technology",
            "Society, Politics & Law",
            "Digital & Computing",
        }:
            category = value
            break

    return {
        "Course Name": title,
        "Provider": "OpenLearn",
        "Course ID / Code": "N/A",
        "Subject / Category": category,
        "Course Type": "Free course",
        "Level": extract_level(text),
        "Duration / Resource Length": extract_duration(text),
        "Language": "N/A",
        "Semester / Year": "N/A",
        "Course URL": urljoin(BASE_URL, href),
        "Collection Date": date.today().isoformat(),
    }


def parse_page(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # First pass: course-looking links.
    for anchor in soup.find_all("a", href=True):
        record = extract_card(anchor)
        if record and record["Course URL"] not in seen_urls:
            seen_urls.add(record["Course URL"])
            records.append(record)

    return records


def page_has_course_results(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    heading = clean_text(soup.get_text(" ", strip=True))
    return "Results:" in heading and "items" in heading


def fetch_all_courses(max_pages: int = 100) -> list[dict[str, str]]:
    """
    Crawl catalogue pages until a page contains no course records.

    A conservative delay is used between requests.
    """
    all_records: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        html = get_page(page)
        page_records = parse_page(html)

        if not page_records:
            break

        new_count = 0
        for record in page_records:
            url = record["Course URL"]
            if url not in seen_urls:
                seen_urls.add(url)
                all_records.append(record)
                new_count += 1

        print(f"OpenLearn page {page}: {new_count} new courses")

        # Stop if the site returned a page but no new course records.
        if new_count == 0:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return all_records


def standardize(records: list[dict[str, str]]) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=COMMON_COLUMNS)

    for col in COMMON_COLUMNS:
        if col not in df.columns:
            df[col] = "N/A"
        df[col] = df[col].fillna("N/A").astype(str).str.strip()

    return df.drop_duplicates(
        subset=["Course Name", "Course URL"]
    ).reset_index(drop=True)


def save_outputs(
    raw_records: list[dict[str, str]],
    df: pd.DataFrame,
    raw_path: str = "data/raw/openlearn_courses.json",
    csv_path: str = "data/processed/openlearn_courses.csv",
    xlsx_path: str = "outputs/openlearn_courses.xlsx",
) -> None:
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)

    Path(raw_path).write_text(
        json.dumps(raw_records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="OpenLearn Courses")

        availability = (
            df.replace("N/A", pd.NA)
            .notna()
            .mean()
            .mul(100)
            .round(1)
            .reset_index()
        )
        availability.columns = ["Field", "Availability (%)"]
        availability.to_excel(
            writer, index=False, sheet_name="Field Availability"
        )


def main() -> None:
    records = fetch_all_courses()
    df = standardize(records)
    save_outputs(records, df)

    print(f"Collected: {len(records)} OpenLearn records")
    print(f"Standardized: {len(df)} records")
    print("Output: outputs/openlearn_courses.xlsx")


if __name__ == "__main__":
    main()
