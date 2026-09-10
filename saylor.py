"""
Saylor Academy public course catalogue collector.

Source:
https://www.saylor.org/CourseCatalog

Reads the public course catalogue and converts course-card information
into the project's common schema. It does not log in, enroll, or access
private student data.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.saylor.org"
CATALOGUE_URL = f"{BASE_URL}/CourseCatalog"
TIMEOUT = 30

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


def get_catalogue() -> str:
    response = requests.get(
        CATALOGUE_URL,
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


def normalize_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def is_course_link(href: str) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    if parsed.netloc and parsed.netloc not in {
        "www.saylor.org",
        "saylor.org",
        "learn.saylor.org",
    }:
        return False
    return (
        "/CourseCatalog/" in parsed.path
        or "/course/" in parsed.path
        or "learn.saylor.org/course/" in href
    )


def split_course_title(text: str) -> tuple[str, str]:
    text = clean_text(text)
    match = re.match(r"^([A-Z]{2,8}\d{2,4})\s*:?\s+(.+)$", text)
    if match:
        return match.group(2).strip(), match.group(1).strip()
    return text, "N/A"


def find_category(card: Tag | None) -> str:
    if card is None:
        return "N/A"

    known_categories = {
        "Arts and Humanities",
        "Business Administration",
        "Computer Science",
        "English as a Second Language",
        "Professional Development",
        "Science and Mathematics",
        "Social Science",
    }

    for heading in card.find_all_previous(["h2", "h3", "h4"], limit=8):
        value = clean_text(heading.get_text(" ", strip=True))
        if value in known_categories:
            return value

    return "N/A"


def parse_course_card(anchor: Tag) -> dict[str, str] | None:
    title_text = clean_text(anchor.get_text(" ", strip=True))
    if not title_text:
        return None

    title, code = split_course_title(title_text)
    if code == "N/A":
        return None

    href = anchor.get("href")
    if not isinstance(href, str) or not is_course_link(href):
        return None

    card: Tag | None = anchor
    for _ in range(7):
        if card is None:
            break
        text = clean_text(card.get_text(" ", strip=True))
        if len(text) >= len(title_text) + 10:
            break
        card = card.parent if isinstance(card.parent, Tag) else None

    return {
        "Course Name": title,
        "Provider": "Saylor Academy",
        "Course ID / Code": code,
        "Subject / Category": find_category(card),
        "Course Type": "Free, self-paced course",
        "Level": "N/A",
        "Duration / Resource Length": "N/A",
        "Language": "English",
        "Semester / Year": "N/A",
        "Course URL": normalize_url(href),
        "Collection Date": date.today().isoformat(),
    }


def parse_catalogue(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        record = parse_course_card(anchor)
        if not record:
            continue

        url = record["Course URL"]
        if url in seen:
            continue

        seen.add(url)
        records.append(record)

    return records


def standardize(records: list[dict[str, str]]) -> pd.DataFrame:
    df = pd.DataFrame(records, columns=COMMON_COLUMNS)

    for col in COMMON_COLUMNS:
        if col not in df.columns:
            df[col] = "N/A"
        df[col] = df[col].fillna("N/A").astype(str).str.strip()
        df.loc[df[col] == "", col] = "N/A"

    return df.drop_duplicates(
        subset=["Course Name", "Course URL"]
    ).reset_index(drop=True)


def save_outputs(
    raw_records: list[dict[str, str]],
    df: pd.DataFrame,
    raw_path: str = "data/raw/saylor_courses.json",
    csv_path: str = "data/processed/saylor_courses.csv",
    xlsx_path: str = "outputs/saylor_courses.xlsx",
) -> None:
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)

    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_records, f, ensure_ascii=False, indent=2)

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Saylor Courses")

        availability = pd.DataFrame({
            "Field": COMMON_COLUMNS,
            "Non-N/A count": [
                int((df[col] != "N/A").sum()) for col in COMMON_COLUMNS
            ],
            "Total records": [len(df)] * len(COMMON_COLUMNS),
        })
        availability.to_excel(
            writer, index=False, sheet_name="Field Availability"
        )


def main() -> None:
    print("Fetching Saylor Academy public course catalogue...")
    html = get_catalogue()
    records = parse_catalogue(html)
    df = standardize(records)

    print(f"Collected {len(df)} unique Saylor course records.")
    save_outputs(records, df)


if __name__ == "__main__":
    main()
