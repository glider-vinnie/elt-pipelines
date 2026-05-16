# Movie Ratings ETL Pipeline

A Python ETL pipeline that **extracts** movie data from a Kaggle dataset, **transforms** it with cleaning and enrichment, and **loads** it into a SQLite database.
## Pipeline Details

### 1. Extract (`extract.py`)

Reads the Kaggle movies dataset and maps it to a canonical schema.

- **Source**: Kaggle `abdallahwagih/movies` dataset (4,803 rows, 24 columns)
- **Config**: CSV path, API key, output dir, max rows — all at top of file
- **Column mapping**: `vote_average` → `rating`, `release_date` → `year`, `genres` → `genre`, etc.
- **Cleaning**: Coerces types, drops rows with unusable nulls
- **Output**: `data/raw_movies.csv` (4,802 rows, 5 columns)

### 2. Transform (`transform.py`)

The core cleaning and enrichment step.

| Operation | Details |
|-----------|---------|
| Remove duplicates | Exact + title+year duplicates |
| Missing values | rating → mean fill, year → drop, genre → "Unknown", votes → 0 |
| Type validation | year → int, rating → float (0–10), title → Title Case |
| Derived columns | `movie_age`, `decade`, `rating_category`, `votes_category` |
| Outlier detection | Flags rating=10 with votes<5 as suspect |
| Business filters | year ≥ 1980, votes ≥ 10, title ≥ 2 chars |
| Validation | 8 post-clean checks (nulls, ranges, duplicates) |

**Rating categories**: Excellent (≥8.0), Good (7.0–8.0), Average (6.0–7.0), Poor (<6.0)

**Result**: 4,802 → 4,157 rows (645 dropped)

### 3. Load (`load.py`)

Loads cleaned data into SQLite with full metadata tracking.

- **Database**: `db/movies.db` (SQLite with WAL mode)
- **Tables**: `movies` (data) + `load_metadata` (ETL run tracking)
- **Indexes**: 5 indexes on title, year, rating, genre, rating_category
- **Duplicate handling**: Skips existing (title+year) pairs — safe to re-run
- **Validation**: Row count match, NULL checks, spot-check, index verification

#### Schema

```sql
-- Main data table
CREATE TABLE movies (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    year              INTEGER NOT NULL,
    rating            REAL NOT NULL,
    votes             INTEGER NOT NULL,
    genre             TEXT,
    movie_age         INTEGER,
    rating_category   TEXT,
    decade            INTEGER,
    votes_category    TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ETL run tracking
CREATE TABLE load_metadata (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    load_run_id      TEXT UNIQUE NOT NULL,
    source_file      TEXT NOT NULL,
    row_count_loaded INTEGER NOT NULL,
    load_timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status           TEXT,
    error_message    TEXT
);
```
## Data Source

[Kaggle: Movies Dataset](https://www.kaggle.com/datasets/abdallahwagih/movies) by Abdallah Wagih — 4,803 movies with ratings, genres, cast, crew, and more.
