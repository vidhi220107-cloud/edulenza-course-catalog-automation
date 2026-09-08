"""
MIT OpenCourseWare collector.

MIT's own MIT Learn export project uses the public MIT Learn API endpoint:
https://api.learn.mit.edu/api/v1/courses/?platform=ocw

The API is paginated. This collector fetches all pages and maps the
available metadata into Edulenza's common course schema.

Source evidence:
https://github.com/mitodl/ocw_oer_export
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

API_URL = "https://api.learn.mit.edu/api/v1/courses/?platform=ocw"
TIMEOUT = 60
PAGE_SIZE = 100

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


def _get(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Edulenza-Course-Catalog-Research/1.0"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise ValueError("Unexpected MIT OCW API response.")

    return data


def fetch_courses() -> list[dict[str, Any]]:
    """Fetch every OCW course through the paginated MIT Learn API."""
    results: list[dict[str, Any]] = []
    next_url: str | None = API_URL
    params: dict[str, Any] | None = {"limit": PAGE_SIZE}

    while next_url:
        page = _get(next_url, params=params)
        page_results = page.get("results", [])

        if not isinstance(page_results, list):
            raise ValueError("Unexpected API response: 'results' is not a list.")

        results.extend(page_results)
        next_url = page.get("next")
        params = None  # 'next' already contains its pagination parameters.

    return results


def _first_run(course: dict[str, Any]) -> dict[str, Any]:
    runs = course.get("runs") or []
    return runs[0] if isinstance(runs, list) and runs else {}


def _join_topics(topics: Any) -> str:
    if not topics:
        return "N/A"

    if isinstance(topics, list):
        values = []
        for topic in topics:
            if isinstance(topic, dict):
                value = topic.get("name") or topic.get("title")
            else:
                value = topic
            if value:
                values.append(str(value).strip())
        return ", ".join(dict.fromkeys(values)) or "N/A"

    return str(topics).strip() or "N/A"


def _join_instructors(instructors: Any) -> str:
    if not instructors:
        return "N/A"

    if isinstance(instructors, list):
        names = []
        for instructor in instructors:
            if isinstance(instructor, dict):
                name = instructor.get("full_name") or instructor.get("name")
            else:
                name = instructor
            if name:
                names.append(str(name).strip())
        return ", ".join(dict.fromkeys(names)) or "N/A"

    return str(instructors).strip() or "N/A"


def standardize(courses: list[dict[str, Any]]) -> pd.DataFrame:
    """Map MIT OCW metadata into the common Edulenza schema."""
    collection_date = date.today().isoformat()
    rows: list[dict[str, Any]] = []

    for course in courses:
        run = _first_run(course)

        semester = run.get("semester") or course.get("semester")
        year = run.get("year") or course.get("year")

        if semester and year:
            semester_year = f"{semester} {year}"
        elif year:
            semester_year = str(year)
        elif semester:
            semester_year = str(semester)
        else:
            semester_year = "N/A"

        # OCW publishes course metadata such as title, URL, topics,
        # level and run/semester information. It does not guarantee
        # language or a single duration value for every course.
        rows.append(
            {
                "Course Name": course.get("title") or "N/A",
                "Provider": "MIT OpenCourseWare",
                "Course ID / Code": (
                    course.get("course_number")
                    or course.get("course_id")
                    or course.get("uid")
                    or "N/A"
                ),
                "Subject / Category": _join_topics(course.get("topics")),
                "Course Type": (
                    course.get("course_type")
                    or course.get("resource_type")
                    or "N/A"
                ),
                "Level": run.get("level") or course.get("level") or "N/A",
                "Duration / Resource Length": (
                    course.get("duration")
                    or course.get("resource_length")
                    or "N/A"
                ),
                "Language": course.get("language") or "N/A",
                "Semester / Year": semester_year,
                "Course URL": course.get("url") or "N/A",
                "Collection Date": collection_date,
            }
        )

    df = pd.DataFrame(rows, columns=COMMON_COLUMNS)

    for col in COMMON_COLUMNS:
        df[col] = df[col].fillna("N/A").astype(str).str.strip()

    return df.drop_duplicates(
        subset=["Course ID / Code", "Course Name", "Course URL"]
    ).reset_index(drop=True)


def save_outputs(
    raw_courses: list[dict[str, Any]],
    df: pd.DataFrame,
    raw_path: str = "data/raw/mit_ocw_courses.json",
    csv_path: str = "data/processed/mit_ocw_courses.csv",
    xlsx_path: str = "outputs/mit_ocw_courses.xlsx",
) -> None:
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)

    Path(raw_path).write_text(
        json.dumps(raw_courses, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="MIT OCW Courses")

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
    courses = fetch_courses()
    df = standardize(courses)
    save_outputs(courses, df)

    print(f"Collected: {len(courses)} MIT OCW records")
    print(f"Standardized: {len(df)} records")
    print("Output: outputs/mit_ocw_courses.xlsx")


if __name__ == "__main__":
    main()
