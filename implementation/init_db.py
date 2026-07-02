"""Create and seed the demo SQLite database.

Running this module is idempotent: it drops and recreates the three demo
tables and reseeds them, so the database is always in a known, reproducible
state for grading and demos.

    uv run python init_db.py            # -> ./lab.db
    uv run python init_db.py my.db      # -> ./my.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from db import DEFAULT_SQLITE_PATH

# --- Schema -----------------------------------------------------------
# A small relational model: students take courses via enrollments.
SCHEMA_SQL = """
DROP TABLE IF EXISTS enrollments;
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS students;

CREATE TABLE students (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    cohort     TEXT    NOT NULL,
    score      REAL    NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE courses (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT    NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL,
    UNIQUE (student_id, course_id)
);
"""

# --- Seed data --------------------------------------------------------
STUDENTS = [
    # (name, cohort, score)
    ("Alice Nguyen", "A1", 92.5),
    ("Bao Tran", "A1", 78.0),
    ("Chi Le", "A1", 85.5),
    ("Dat Pham", "A2", 66.0),
    ("Emily Vo", "A2", 88.0),
    ("Feng Li", "A2", 71.5),
    ("Giang Do", "B1", 95.0),
    ("Hana Kim", "B1", 59.0),
]

COURSES = [
    # (title, credits)
    ("Databases", 4),
    ("Algorithms", 3),
    ("Web Development", 3),
    ("Machine Learning", 4),
]

ENROLLMENTS = [
    # (student_id, course_id, grade)
    (1, 1, 90.0),
    (1, 2, 88.0),
    (2, 1, 75.0),
    (2, 3, 80.0),
    (3, 2, 82.0),
    (4, 1, 60.0),
    (5, 4, 91.0),
    (6, 3, 70.0),
    (7, 4, 96.0),
    (7, 1, 93.0),
    (8, 2, 55.0),
]


def create_database(path: str | Path = DEFAULT_SQLITE_PATH) -> Path:
    """Create the schema and seed data at ``path``. Returns the DB path."""
    path = Path(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO students (name, cohort, score) VALUES (?, ?, ?)",
            STUDENTS,
        )
        conn.executemany(
            "INSERT INTO courses (title, credits) VALUES (?, ?)",
            COURSES,
        )
        conn.executemany(
            "INSERT INTO enrollments (student_id, course_id, grade) VALUES (?, ?, ?)",
            ENROLLMENTS,
        )
        conn.commit()
    finally:
        conn.close()
    return path


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SQLITE_PATH
    path = create_database(target)
    print(f"Initialised database at: {path}")
    print(
        f"Seeded {len(STUDENTS)} students, {len(COURSES)} courses, "
        f"{len(ENROLLMENTS)} enrollments."
    )


if __name__ == "__main__":
    main()
