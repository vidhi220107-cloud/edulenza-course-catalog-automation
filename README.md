# edulenza-course-catalog-automation
Python-based automation tool for collecting, standardizing, analyzing, and visualizing public course catalogue data from multiple educational sources.

# Edulenza Course Catalog Automation

A Python-based research data automation tool developed for Edulenza to collect, standardize, analyze, and visualize publicly available course catalogue data from multiple educational sources.

## Objective

The objective of this project is to build a reusable baseline for public course catalogue analysis without relying on large historical datasets.

The tool automates the collection of publicly available course information, converts data from different sources into a common structure, and generates datasets and visual insights for comparison.

## Selected Sources

The project currently covers the following public course catalogues:

- MIT FireRoad Course Catalog
- MIT OpenCourseWare
- OpenLearn
- Saylor Academy

## Common Data Fields

The collected course data is standardized using the following fields:

1. Course Name
2. Provider
3. Course ID / Code
4. Subject / Category
5. Course Type
6. Level
7. Duration / Resource Length
8. Language
9. Semester / Year
10. Course URL

Where a source does not provide a particular field, the value will be recorded as `N/A` rather than being estimated or invented.

## Workflow

```text
Public Course Sources
        |
        v
Automated Data Collection
        |
        v
Raw Course Data
        |
        v
Data Cleaning & Standardization
        |
        v
Combined Course Dataset
        |
        v
Data Analysis
        |
        v
Visualizations & Comparison
        |
        v
Research Report / Insights
