"""База даних SQLite: схема, міграції та імпорт питань із CSV.

Запуск:
    python db.py
"""
import csv
import os
import sqlite3
from contextlib import closing
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"


def db_path() -> str:
    return os.environ.get("QUIZ_DB_PATH", str(BASE_DIR / "quiz.db"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS disciplines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    title TEXT NOT NULL,
    UNIQUE (discipline_id, title)
);

CREATE TABLE IF NOT EXISTS uploaded_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    title TEXT NOT NULL,
    stored_filename TEXT NOT NULL UNIQUE,
    uploaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    text TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    correct TEXT NOT NULL CHECK (correct IN ('A','B','C','D'))
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    score INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    duration_sec INTEGER,
    student_id INTEGER REFERENCES students(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS test_sessions (
    token TEXT PRIMARY KEY,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    question_ids TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS student_sessions (
    token_hash TEXT PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_questions_lecture ON questions(lecture_id);
CREATE INDEX IF NOT EXISTS idx_results_lecture ON results(lecture_id);
CREATE INDEX IF NOT EXISTS idx_student_sessions_student ON student_sessions(student_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Підтримка старих баз."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
    if "duration_sec" not in columns:
        conn.execute("ALTER TABLE results ADD COLUMN duration_sec INTEGER")
    if "student_id" not in columns:
        conn.execute(
            "ALTER TABLE results ADD COLUMN student_id INTEGER REFERENCES students(id)"
        )


def init_db() -> None:
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_results_student ON results(student_id)")
        conn.commit()


def _clean(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _import_row(conn: sqlite3.Connection, row: dict) -> None:
    discipline = _clean(row, "discipline")
    lecture = _clean(row, "lecture")
    text = _clean(row, "question")
    options = [_clean(row, key) for key in "abcd"]
    correct = _clean(row, "correct").upper()

    if not (discipline and lecture and text):
        raise ValueError("порожня дисципліна, лекція або текст питання")
    if not all(options):
        raise ValueError("заповнено не всі 4 варіанти відповіді")
    if correct not in ("A", "B", "C", "D"):
        raise ValueError(f"поле correct = '{correct}', очікується A, B, C або D")

    conn.execute("INSERT OR IGNORE INTO disciplines(name) VALUES (?)", (discipline,))
    discipline_id = conn.execute(
        "SELECT id FROM disciplines WHERE name = ?", (discipline,)
    ).fetchone()["id"]

    conn.execute(
        "INSERT OR IGNORE INTO lectures(discipline_id, title) VALUES (?, ?)",
        (discipline_id, lecture),
    )
    lecture_id = conn.execute(
        "SELECT id FROM lectures WHERE discipline_id = ? AND title = ?",
        (discipline_id, lecture),
    ).fetchone()["id"]

    existing = conn.execute(
        "SELECT id FROM questions WHERE lecture_id = ? AND text = ?",
        (lecture_id, text),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE questions
               SET option_a=?, option_b=?, option_c=?, option_d=?, correct=?
               WHERE id=?""",
            (*options, correct, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO questions
               (lecture_id, text, option_a, option_b, option_c, option_d, correct)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lecture_id, text, *options, correct),
        )


def load_csv(path) -> int:
    count = 0
    with closing(connect()) as conn:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                try:
                    _import_row(conn, row)
                except ValueError as error:
                    print(f"⚠️  {Path(path).name}, рядок {line_no}: {error}")
                    continue
                count += 1
        conn.commit()
    return count


def load_all() -> int:
    total = 0
    for csv_file in sorted(DATA_DIR.glob("*.csv")):
        loaded = load_csv(csv_file)
        print(f"{csv_file.name}: оброблено {loaded} питань")
        total += loaded
    return total


if __name__ == "__main__":
    init_db()
    print(f"Усього оброблено питань: {load_all()}")