import csv
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "quiz.db"
DATA_DIR = BASE_DIR / "data"

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
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def load_csv(path):
    count = 0
    with get_connection() as conn, open(path, encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2): # start=2, бо 1-й рядок це заголовки
            # Перевіряємо, чи не порожній рядок взагалі (про всяк випадок)
            if not row.get("question"):
                continue

            # Безпечно дістаємо правильну відповідь
            correct_val = (row.get("correct") or "").strip().upper()
            
            # Якщо відповідь не A, B, C або D — пропускаємо цей рядок і пишемо попередження
            if correct_val not in ('A', 'B', 'C', 'D'):
                print(f"⚠️ Рядок {i} пропущено! Значення 'correct' = '{correct_val}'. Текст питання: {row.get('question')[:30]}...")
                continue

            discipline = row["discipline"].strip()
            lecture = row["lecture"].strip()

            conn.execute("INSERT OR IGNORE INTO disciplines(name) VALUES (?)", (discipline,))
            d_id = conn.execute(
                "SELECT id FROM disciplines WHERE name = ?", (discipline,)
            ).fetchone()["id"]

            conn.execute(
                "INSERT OR IGNORE INTO lectures(discipline_id, title) VALUES (?, ?)",
                (d_id, lecture),
            )
            l_id = conn.execute(
                "SELECT id FROM lectures WHERE discipline_id = ? AND title = ?",
                (d_id, lecture),
            ).fetchone()["id"]

            # Вставляємо питання, використовуючи вже перевірену correct_val
            conn.execute(
                """INSERT INTO questions
                   (lecture_id, text, option_a, option_b, option_c, option_d, correct)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (l_id, row["question"].strip(), row["a"].strip(), row["b"].strip(),
                 row["c"].strip(), row["d"].strip(), correct_val),
            )
            count += 1
    return count


if __name__ == "__main__":
    DB_PATH.unlink(missing_ok=True)  # перебудовуємо базу з нуля
    init_db()
    total = 0
    for csv_file in sorted(DATA_DIR.glob("*.csv")):
        n = load_csv(csv_file)
        print(f"{csv_file.name}: завантажено {n} питань")
        total += n
    print(f"Усього: {total}")
    
import csv

with open('data/questions.csv', mode='r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader, 2): # Починаємо з 2, бо 1-й рядок це заголовок
        val = row.get("correct")
        if not val or val.strip().upper() not in ('A', 'B', 'C', 'D'):
            print(f"❌ Помилка у рядку {i}: correct = '{val}'")
            print("Повний рядок:", row)