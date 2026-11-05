"""База даних SQLite: схема, невеликі міграції та імпорт питань із CSV.

Запуск вручну (створює таблиці й докидає питання з data/*.csv, нічого не видаляючи):
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
    """Шлях до файлу БД. Можна змінити змінною середовища QUIZ_DB_PATH."""
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

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    discipline_id INTEGER NOT NULL REFERENCES disciplines(id),
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    score INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    duration_sec INTEGER,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Одна сесія = один згенерований тест. Токен можна використати лише раз.
CREATE TABLE IF NOT EXISTS test_sessions (
    token TEXT PRIMARY KEY,
    lecture_id INTEGER NOT NULL REFERENCES lectures(id),
    question_ids TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_questions_lecture ON questions(lecture_id);
CREATE INDEX IF NOT EXISTS idx_results_lecture ON results(lecture_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Дозволяє працювати зі старою базою, створеною першою версією застосунку."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(results)")}
    if "duration_sec" not in columns:
        conn.execute("ALTER TABLE results ADD COLUMN duration_sec INTEGER")


def init_db() -> None:
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()


def _clean(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _import_row(conn: sqlite3.Connection, row: dict) -> None:
    """Додає або оновлює одне питання. Кидає ValueError для некоректного рядка."""
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
        "SELECT id FROM questions WHERE lecture_id = ? AND text = ?", (lecture_id, text)
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE questions
               SET option_a = ?, option_b = ?, option_c = ?, option_d = ?, correct = ?
               WHERE id = ?""",
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
    """Імпортує питання з CSV. Повторний запуск не створює дублікатів."""
    count = 0
    with closing(connect()) as conn:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                try:
                    _import_row(conn, row)
                except ValueError as error:
                    print(f"⚠️  {Path(path).name}, рядок {line_no} пропущено: {error}")
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
