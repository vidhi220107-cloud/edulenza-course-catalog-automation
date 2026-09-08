"""
MIT FireRoad Course Catalog collector.

Source:
https://fireroad.mit.edu/reference/catalog

The collector uses the documented public course lookup endpoint.
For production use, follow FireRoad's API approval/usage requirements.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

API_URL = "https://fireroad.mit.edu/courses/all"
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


def fetch_courses(full: bool = True) -> list[dict[str, Any]]:
    """Fetch the current FireRoad catalogue."""
    response = requests.get(
        API_URL,
        params={"full": str(full).lower()},
        headers={
            "User-Agent": "Edulenza-Course-Catalog-Research/1.0"
        },
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, list):
        raise ValueError("Unexpected FireRoad API response: expected a list.")

    return data


def _level(value: Any) -> str:
    mapping = {"U": "Undergraduate", "G": "Graduate"}
    return mapping.get(str(value).upper(), "N/A") if value else "N/A"


def _workload(course: dict[str, Any]) -> str:
    in_class = course.get("in_class_hours")
    out_class = course.get("out_of_class_hours")

    if in_class is not None and out_class is not None:
        return f"{in_class} in-class hrs + {out_class} out-of-class hrs"
    if in_class is not None:
        return f"{in_class} in-class hrs"
    if out_class is not None:
        return f"{out_class} out-of-class hrs"
    return "N/A"


def standardize(courses: list[dict[str, Any]]) -> pd.DataFrame:
    """Map FireRoad fields into the project's common 10-field schema."""
    collection_date = date.today().isoformat()
    rows: list[dict[str, Any]] = []

    for course in courses:
        rows.append(
            {
                "Course Name": course.get("title") or "N/A",
                "Provider": "MIT FireRoad",
                "Course ID / Code": course.get("subject_id") or "N/A",
                # FireRoad does not expose a dedicated subject/category
                # field in the documented course endpoint.
                "Subject / Category": "N/A",
                "Course Type": "N/A",
                "Level": _level(course.get("level")),
                "Duration / Resource Length": _workload(course),
                "Language": "N/A",
                "Semester / Year": course.get("source_semester") or "N/A",
                "Course URL": course.get("url") or "N/A",
                "Collection Date": collection_date,
            }
        )

    df = pd.DataFrame(rows, columns=COMMON_COLUMNS)

    # Basic cleaning: trim whitespace and remove exact duplicate rows.
    for col in COMMON_COLUMNS:
        df[col] = df[col].astype(str).str.strip()

    df = df.drop_duplicates(
        subset=["Course ID / Code", "Course Name", "Course URL"]
    ).reset_index(drop=True)

    return df


def save_outputs(
    raw_courses: list[dict[str, Any]],
    df: pd.DataFrame,
    raw_path: str = "data/raw/fireroad_courses.json",
    csv_path: str = "data/processed/fireroad_courses.csv",
    xlsx_path: str = "outputs/fireroad_courses.xlsx",
) -> None:
    """Save raw JSON plus standardized CSV and Excel outputs."""
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    Path(xlsx_path).parent.mkdir(parents=True, exist_ok=True)

    Path(raw_path).write_text(
        json.dumps(raw_courses, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    df.to_csv(csv_path, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="FireRoad Courses")
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
    courses = fetch_courses(full=True)
    df = standardize(courses)
    save_outputs(courses, df)

    print(f"Collected: {len(courses)} FireRoad records")
    print(f"Standardized: {len(df)} records")
    print("Output: outputs/fireroad_courses.xlsx")


if __name__ == "__main__":
    main()
