"""
transform.py  -  Movie Ratings ETL - Transform Phase
Cleans, validates, enriches, and filters raw_movies.csv.
"""

import sys
import io
import logging
import pandas as pd
import numpy as np
from pathlib import Path

# -- CONFIG ------------------------------------------------------------------
INPUT_CSV    = Path("data/raw_movies.csv")
OUTPUT_CSV   = Path("data/cleaned_movies.csv")
LOG_DIR      = Path("log")
LOG_FILE     = LOG_DIR / "transform.log"
CURRENT_YEAR = 2026
MIN_YEAR     = 1980
MIN_VOTES    = 10

# -- Logging (console + file) -----------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
    ],
)
log = logging.getLogger("transform")


# ============================================================================
#  1. LOAD RAW DATA
# ============================================================================
def load_raw_data(path: Path = INPUT_CSV) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
        log.info("Loaded %d rows, %d columns from %s", len(df), len(df.columns), path)
        return df
    except Exception as exc:
        log.error("Cannot read %s: %s", path, exc)
        sys.exit(1)


# ============================================================================
#  2. REMOVE DUPLICATES
# ============================================================================
def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    exact = df.duplicated().sum()
    df = df.drop_duplicates()
    log.info("Removed %d exact duplicate rows", exact)

    title_year = df.duplicated(subset=["title", "year"]).sum()
    df = df.drop_duplicates(subset=["title", "year"], keep="first")
    log.info("Removed %d title+year duplicate rows", title_year)

    log.info("Duplicates: %d -> %d rows (-%d)", before, len(df), before - len(df))
    return df.reset_index(drop=True)


# ============================================================================
#  3. HANDLE MISSING VALUES
# ============================================================================
def handle_missing_values(df: pd.DataFrame) -> pd.DataFrame:
    log.info("Missing values before: %s", df.isna().sum().to_dict())

    # year: drop if missing
    n = df["year"].isna().sum()
    df = df.dropna(subset=["year"])
    log.info("Dropped %d rows with missing year", n)

    # rating: fill with mean if <5%% missing, else drop
    null_pct = df["rating"].isna().mean()
    n = df["rating"].isna().sum()
    if n > 0:
        if null_pct < 0.05:
            mean_val = round(df["rating"].mean(), 1)
            df["rating"] = df["rating"].fillna(mean_val)
            log.info("Filled %d missing ratings with mean: %.1f", n, mean_val)
        else:
            df = df.dropna(subset=["rating"])
            log.info("Dropped %d rows with missing rating (%.1f%% null)", n, null_pct * 100)
    else:
        log.info("No missing ratings - no action needed")

    # genre: fill with Unknown
    n = df["genre"].isna().sum()
    df["genre"] = df["genre"].fillna("Unknown")
    log.info("Filled %d missing genres with 'Unknown'", n)

    # votes: fill with 0
    n = df["votes"].isna().sum()
    df["votes"] = df["votes"].fillna(0)
    log.info("Filled %d missing votes with 0", n)

    # title: fill blanks
    n = df["title"].isna().sum()
    df["title"] = df["title"].fillna("Untitled")
    log.info("Filled %d missing titles with 'Untitled'", n)

    log.info("Missing values after: %s", df.isna().sum().to_dict())
    return df


# ============================================================================
#  4. VALIDATE DATA TYPES
# ============================================================================
def validate_data_types(df: pd.DataFrame) -> pd.DataFrame:
    # Type conversions
    df["year"]   = df["year"].astype(int)
    df["rating"] = df["rating"].astype(float)
    df["votes"]  = df["votes"].astype(int)
    log.info("Converted year->int, rating->float, votes->int")

    # Title: strip whitespace, title case
    df["title"] = df["title"].str.strip().str.title()
    log.info("Cleaned titles: stripped whitespace, applied title case")

    # Genre: strip whitespace
    df["genre"] = df["genre"].str.strip()
    log.info("Cleaned genres: stripped whitespace")

    # Range validation
    before = len(df)
    df = df[(df["rating"] >= 0) & (df["rating"] <= 10)]
    dropped = before - len(df)
    log.info("Dropped %d rows with rating outside 0-10 range", dropped)

    before = len(df)
    df = df[(df["year"] >= 1900) & (df["year"] <= CURRENT_YEAR)]
    dropped = before - len(df)
    log.info("Dropped %d rows with year outside 1900-%d", dropped, CURRENT_YEAR)

    log.info("Data types: %s", df.dtypes.to_dict())
    return df.reset_index(drop=True)


# ============================================================================
#  5. CREATE DERIVED COLUMNS
# ============================================================================
def create_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    # movie_age
    df["movie_age"] = CURRENT_YEAR - df["year"]
    log.info("Created movie_age column (sample: %s)", list(df["movie_age"].head(3)))

    # decade
    df["decade"] = (df["year"] // 10) * 10
    log.info("Created decade column (sample: %s)", list(df["decade"].head(3)))

    # rating_category
    df["rating_category"] = pd.cut(
        df["rating"],
        bins=[-0.1, 6.0, 7.0, 8.0, 10.1],
        labels=["Poor", "Average", "Good", "Excellent"],
    )
    log.info("Created rating_category column - distribution: %s",
             df["rating_category"].value_counts().to_dict())

    # votes_category
    df["votes_category"] = pd.cut(
        df["votes"],
        bins=[-1, 1_000, 10_000, 100_000, float("inf")],
        labels=["Low", "Moderate", "Popular", "Very Popular"],
    )
    log.info("Created votes_category column - distribution: %s",
             df["votes_category"].value_counts().to_dict())

    return df


# ============================================================================
#  6. DETECT OUTLIERS
# ============================================================================
def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    suspect = (df["rating"] == 10) & (df["votes"] < 5)
    df["is_suspect"] = suspect
    n = suspect.sum()
    if n:
        log.warning("Flagged %d suspect entries (rating=10, votes<5):", n)
        for _, row in df[suspect].iterrows():
            log.warning("  -> '%s' (%d) rating=%.1f votes=%d",
                        row["title"], row["year"], row["rating"], row["votes"])
    else:
        log.info("No suspect entries found (rating=10 with votes<5)")
    return df


# ============================================================================
#  7. FILTER DATA (business logic)
# ============================================================================
def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    before = len(df)

    df = df[df["year"] >= MIN_YEAR]
    log.info("Filter year >= %d: %d -> %d rows", MIN_YEAR, before, len(df))

    before_v = len(df)
    df = df[df["votes"] >= MIN_VOTES]
    log.info("Filter votes >= %d: %d -> %d rows", MIN_VOTES, before_v, len(df))

    before_t = len(df)
    df = df[df["title"].str.len() >= 2]
    log.info("Filter title >= 2 chars: %d -> %d rows", before_t, len(df))

    # Remove suspect rows
    before_s = len(df)
    df = df[~df["is_suspect"]]
    log.info("Removed %d suspect entries", before_s - len(df))
    df = df.drop(columns=["is_suspect"])

    log.info("Filtering done: %d -> %d rows total", before, len(df))
    return df.reset_index(drop=True)


# ============================================================================
#  8. VALIDATE CLEANED DATA
# ============================================================================
def validate_cleaned_data(df: pd.DataFrame) -> bool:
    log.info("--- Final Validation ---")
    ok = True
    checks = {
        "No duplicates":                    df.duplicated().sum() == 0,
        "No null in title":                 df["title"].isna().sum() == 0,
        "No null in year":                  df["year"].isna().sum() == 0,
        "No null in rating":                df["rating"].isna().sum() == 0,
        "No null in votes":                 df["votes"].isna().sum() == 0,
        "Rating in 0-10":                   df["rating"].between(0, 10).all(),
        f"Year in {MIN_YEAR}-{CURRENT_YEAR}": df["year"].between(MIN_YEAR, CURRENT_YEAR).all(),
        f"Votes >= {MIN_VOTES}":            (df["votes"] >= MIN_VOTES).all(),
    }
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        log.info("  [%s] %s", status, name)
        if not passed:
            ok = False
    return ok


# ============================================================================
#  9. SAVE
# ============================================================================
def save_cleaned(df: pd.DataFrame, path: Path = OUTPUT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.info("Saved %d cleaned rows -> %s", len(df), path)


# ============================================================================
#  10. SUMMARY
# ============================================================================
def print_summary(df: pd.DataFrame, rows_before: int) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print("  TRANSFORM SUMMARY")
    print(f"{bar}\n")
    print(f"  Rows before : {rows_before:,}")
    print(f"  Rows after  : {len(df):,}")
    print(f"  Rows dropped: {rows_before - len(df):,}")
    print(f"  Columns     : {list(df.columns)}")
    print(f"  Nulls       : {df.isna().sum().sum()}")
    print(f"  Year range  : {df['year'].min()} - {df['year'].max()}")
    print(f"  Rating avg  : {df['rating'].mean():.2f}")

    print(f"\n  Data types:")
    for col, dtype in df.dtypes.items():
        print(f"    {col:<20} {str(dtype)}")

    print(f"\n  Rating distribution:")
    for cat, cnt in df["rating_category"].value_counts().sort_index().items():
        pct = cnt / len(df) * 100
        bar_char = "#" * int(pct / 2)
        print(f"    {cat:<12} {cnt:>5,}  ({pct:4.1f}%)  {bar_char}")

    print(f"\n  Votes distribution:")
    for cat, cnt in df["votes_category"].value_counts().sort_index().items():
        pct = cnt / len(df) * 100
        bar_char = "#" * int(pct / 2)
        print(f"    {cat:<14} {cnt:>5,}  ({pct:4.1f}%)  {bar_char}")

    print(f"\n  Top decades:")
    for dec, cnt in df["decade"].value_counts().sort_index(ascending=False).head(5).items():
        print(f"    {int(dec)}s  {cnt:>5,}")

    print(f"\n  New columns (first 5 rows):")
    print(df[["title", "movie_age", "decade", "rating_category", "votes_category"]].head().to_string(index=False))

    print(f"\n{bar}")
    print("  [OK] Transform phase complete!")
    print(f"  Log saved -> {LOG_FILE}")
    print(f"{bar}\n")


# ============================================================================
#  MAIN
# ============================================================================
def main():
    print("\n Movie Ratings ETL - TRANSFORM\n")

    df = load_raw_data()
    rows_before = len(df)

    df = remove_duplicates(df)
    df = handle_missing_values(df)
    df = validate_data_types(df)
    df = create_derived_columns(df)
    df = detect_outliers(df)
    df = filter_data(df)

    if validate_cleaned_data(df):
        log.info("All validation checks PASSED!")
    else:
        log.warning("Some validation checks FAILED - review data")

    save_cleaned(df)
    print_summary(df, rows_before)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()
