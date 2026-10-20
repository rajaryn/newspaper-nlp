"""
Phase 2: clean the scraped CSVs and profile them for the report.

Usage:
    pip install pandas
    python clean_and_profile.py

For each input file it writes, next to the input (data/<site>/):
    <name>_clean.csv        cleaned rows (one per article)
    <name>_sections.csv     every URL section with its article count -> fill in a 'category' column by hand
    <name>_per_day.csv      articles per day (for the report and to spot gaps)
and prints a summary you can copy into the Running log.

Cleaning steps (each one's row count is printed, so you can report it):
    1. drop exact duplicate URLs
    2. drop non-article pages (videos, photos, live blogs, web stories, horoscopes, tags, authors)
    3. build a 'text' column: the headline, or the URL slug when the headline is empty
    4. drop rows whose text is shorter than 3 words
    5. drop duplicate texts on the same day (same story filed under two URLs)
"""

import re
import sys
from pathlib import Path

import pandas as pd

JUNK = re.compile(
    r"/(?:videos?|photos?|gallery|live-?blog|liveblog|web-?stories|webstories|horoscope|rashifal|tag|tags|author|topic|podcast)s?/",
    re.I,
)


def clean(path):
    df = pd.read_csv(path, dtype=str).fillna("")
    steps = [("raw rows", len(df))]

    df = df.drop_duplicates(subset="url")
    steps.append(("after removing duplicate URLs", len(df)))

    df = df[~df["url"].str.contains(JUNK)]
    steps.append(("after removing videos/photos/live blogs/etc.", len(df)))

    headline = df["headline"].str.strip() if "headline" in df else ""
    slug = df["slug"].str.strip() if "slug" in df else ""
    df["text"] = headline.where(headline != "", slug) if "headline" in df else slug
    df["text"] = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["text"].str.split().str.len() >= 3]
    steps.append(("after removing empty/very short headlines", len(df)))

    df = df.drop_duplicates(subset=["date", "text"])
    steps.append(("after removing same-day duplicate headlines", len(df)))

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    return df, steps



# ============================== SETTINGS ==============================
DATA = Path(__file__).parent / "data"
INPUTS = [DATA / "ie" / "ie_2024.csv", DATA / "jansatta" / "jansatta_2024.csv"]   # files made by sitemap_scraper / headline_fetcher
# ======================================================================


def main():
    for path in INPUTS:
        p = Path(path)
        df, steps = clean(p)
        stem = p.with_suffix("")

        df.to_csv(f"{stem}_clean.csv", index=False, date_format="%Y-%m-%d")

        sections = df["section"].replace("", "(none)").value_counts().rename_axis("section").reset_index(name="articles")
        sections["category"] = ""  # fill this in by hand
        sections.to_csv(f"{stem}_sections.csv", index=False)

        per_day = df.groupby(df["date"].dt.date).size()
        all_days = pd.date_range(df["date"].min(), df["date"].max()).date
        per_day = per_day.reindex(all_days, fill_value=0)
        per_day.rename_axis("date").reset_index(name="articles").to_csv(f"{stem}_per_day.csv", index=False)

        print(f"\n=== {p.name} ===")
        for name, n in steps:
            print(f"  {name:<48}{n:>8}")
        print(f"  date range: {df['date'].min().date()} to {df['date'].max().date()}")
        print(f"  articles per day: mean {per_day.mean():.1f}, min {per_day.min()}, max {per_day.max()}")
        print(f"  days with no articles: {(per_day == 0).sum()}")
        print(f"  distinct URL sections: {len(sections)} (top 10 below)")
        print(sections.head(10).to_string(index=False))
        print(f"  wrote {stem.name}_clean.csv, {stem.name}_sections.csv, {stem.name}_per_day.csv in {p.parent}")


if __name__ == "__main__":
    main()