"""Кросплатформний вебзастосунок для інтерактивного тестування студентів.

Налаштування через змінні середовища (див. README.md):
    TEACHER_PASSWORD  - пароль до кабінету викладача (якщо не задано, кабінет відкритий)
    APPS_SCRIPT_URL   - адреса Google Apps Script для запису результатів у Google Sheets
    QUIZ_DB_PATH      - шлях до файлу SQLite (за замовчуванням quiz.db поруч із кодом)
"""
import csv
import io
import json
import os
import random
import secrets
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

import db

BASE_DIR = Path(__file__).parent
DEFAULT_QUESTIONS = 10   # скільки питань у тесті
MAX_QUESTIONS = 30
PASS_PERCENT = 60        # поріг «склав» для аналітики
SESSION_TTL_HOURS = 24   # скільки живе незавершений тест


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Таблиці створюються, а питання з data/*.csv докидаються при кожному старті.
    # Тому на Render не потрібно зберігати quiz.db у Git.
    db.init_db()
    db.load_all()
    yield


app = FastAPI(title="Quiz App", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
security = HTTPBasic(auto_error=False)


# ---------------------------------------------------------------- допоміжне

def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def require_teacher(credentials: Optional[HTTPBasicCredentials] = Depends(security)):
    """Захист кабінету викладача паролем (HTTP Basic). Ім'я користувача ігнорується."""
    password = os.environ.get("TEACHER_PASSWORD")
    if not password:
        return  # пароль не задано: зручно для локальної розробки
    given = credentials.password.encode() if credentials else b""
    if not secrets.compare_digest(given, password.encode()):
        raise HTTPException(
            status_code=401,
            detail="Потрібен пароль викладача",
            headers={"WWW-Authenticate": 'Basic realm="teacher"'},  # заголовок лише ASCII
        )


def now_local() -> datetime:
    try:
        return datetime.now(ZoneInfo("Europe/Kyiv"))
    except ZoneInfoNotFoundError:  # на Windows без пакета tzdata
        return datetime.now(timezone.utc)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_local_text(created_at: str) -> str:
    """'2026-11-04T19:22:51Z' або '2026-11-04 19:22:51' (UTC) -> київський час."""
    try:
        raw = created_at.replace("T", " ").rstrip("Z")[:19]
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        try:
            dt = dt.astimezone(ZoneInfo("Europe/Kyiv"))
        except ZoneInfoNotFoundError:
            pass
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, AttributeError):
        return created_at


# ------------------------------------------------------- Google Sheets

def send_to_google_sheets(row: list) -> None:
    url = os.environ.get("APPS_SCRIPT_URL")
    if not url:
        return
    try:
        response = requests.post(url, json=row, timeout=10)
        if response.status_code == 200:
            print("✅ Дані відправлено в Google Sheets")
        else:
            print(f"❌ Google Sheets: статус {response.status_code}")
    except requests.RequestException as error:
        print(f"❌ Google Sheets недоступний: {error}")


def send_in_background(row: list) -> None:
    """Не змушуємо студента чекати на Google: відправляємо у фоновому потоці."""
    if os.environ.get("APPS_SCRIPT_URL"):
        threading.Thread(target=send_to_google_sheets, args=(row,), daemon=True).start()


# ---------------------------------------------------------------- сторінки

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/test", response_class=HTMLResponse)
def test_page(request: Request):
    return templates.TemplateResponse(request=request, name="test.html")


@app.get("/teacher", response_class=HTMLResponse, dependencies=[Depends(require_teacher)])
def teacher_page(request: Request):
    return templates.TemplateResponse(request=request, name="teacher.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------- довідники (публічні)

@app.get("/api/disciplines")
def get_disciplines(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        """SELECT d.id, d.name FROM disciplines d
           WHERE EXISTS (SELECT 1 FROM lectures l JOIN questions q ON q.lecture_id = l.id
                         WHERE l.discipline_id = d.id)
           ORDER BY d.name"""
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/disciplines/{discipline_id}/lectures")
def get_lectures(discipline_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        """SELECT l.id, l.title, COUNT(q.id) AS question_count
           FROM lectures l LEFT JOIN questions q ON q.lecture_id = l.id
           WHERE l.discipline_id = ?
           GROUP BY l.id HAVING COUNT(q.id) > 0
           ORDER BY l.id""",
        (discipline_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------ проходження тесту

@app.get("/api/lectures/{lecture_id}/test")
def generate_test(
    lecture_id: int,
    limit: int = Query(DEFAULT_QUESTIONS, ge=1, le=MAX_QUESTIONS),
    conn: sqlite3.Connection = Depends(get_conn),
):
    """Випадкові питання лекції + випадковий порядок варіантів. Правильних відповідей не віддаємо."""
    lecture = conn.execute("SELECT id, title FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
    rows = conn.execute(
        "SELECT id, text, option_a, option_b, option_c, option_d FROM questions WHERE lecture_id = ?",
        (lecture_id,),
    ).fetchall()
    if not lecture or not rows:
        raise HTTPException(status_code=404, detail="Питання для цієї лекції не знайдені")

    questions = []
    for row in random.sample(rows, min(limit, len(rows))):
        # key - початкова літера варіанта в БД; саме її клієнт повертає при відповіді.
        options = [{"key": k, "text": row[f"option_{k.lower()}"]} for k in "ABCD"]
        random.shuffle(options)
        questions.append({"id": row["id"], "text": row["text"], "options": options})

    token = uuid.uuid4().hex
    cutoff = utc_iso(datetime.now(timezone.utc) - timedelta(hours=SESSION_TTL_HOURS))
    conn.execute("DELETE FROM test_sessions WHERE created_at < ?", (cutoff,))
    conn.execute(
        "INSERT INTO test_sessions (token, lecture_id, question_ids) VALUES (?, ?, ?)",
        (token, lecture_id, json.dumps([q["id"] for q in questions])),
    )
    conn.commit()
    return {
        "token": token,
        "lecture_id": lecture_id,
        "lecture_title": lecture["title"],
        "questions": questions,
    }


def normalize_group(value: str) -> str:
    """КН-21, кн-21 і ' кн-21 ' - це одна група. SQLite не вміє міняти регістр кирилиці, тож робимо це тут."""
    return " ".join(value.split()).upper()


def normalize_name(value: str) -> str:
    return " ".join(value.split()).title()


class AnswerItem(BaseModel):
    question_id: int
    selected_option: Literal["A", "B", "C", "D"]


class TestSubmission(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(min_length=8, max_length=64)
    full_name: str = Field(min_length=2, max_length=100)
    group_name: str = Field(min_length=1, max_length=30)
    answers: list[AnswerItem] = Field(max_length=100)
    duration_sec: Optional[int] = Field(default=None, ge=0, le=86400)


@app.post("/api/submit_test")
def submit_test(submission: TestSubmission, conn: sqlite3.Connection = Depends(get_conn)):
    session = conn.execute(
        "SELECT lecture_id, question_ids FROM test_sessions WHERE token = ?", (submission.token,)
    ).fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Тест не знайдено або він застарів. Почніть заново.")

    # Атомарно «спалюємо» токен: повторно надіслати результат не вийде.
    claimed = conn.execute(
        "UPDATE test_sessions SET used = 1 WHERE token = ? AND used = 0", (submission.token,)
    )
    conn.commit()
    if claimed.rowcount == 0:
        raise HTTPException(status_code=409, detail="Цей тест уже завершено")

    question_ids = json.loads(session["question_ids"])
    placeholders = ",".join("?" * len(question_ids))
    rows = {
        r["id"]: r
        for r in conn.execute(
            f"SELECT * FROM questions WHERE id IN ({placeholders})", question_ids
        ).fetchall()
    }

    # Враховуємо лише питання з цього тесту, по одній відповіді на питання.
    chosen = {a.question_id: a.selected_option for a in submission.answers if a.question_id in rows}

    score = 0
    review = []
    for qid in question_ids:
        row = rows[qid]
        selected = chosen.get(qid)
        correct = row["correct"]
        is_correct = selected == correct
        score += is_correct
        review.append({
            "text": row["text"],
            "selected_text": row[f"option_{selected.lower()}"] if selected else None,
            "correct_text": row[f"option_{correct.lower()}"],
            "is_correct": is_correct,
        })

    total = len(question_ids)  # питання без відповіді теж рахуються в total
    full_name = normalize_name(submission.full_name)
    group_name = normalize_group(submission.group_name)
    lecture = conn.execute(
        """SELECT l.title AS lecture, l.discipline_id, d.name AS discipline
           FROM lectures l JOIN disciplines d ON d.id = l.discipline_id WHERE l.id = ?""",
        (session["lecture_id"],),
    ).fetchone()

    conn.execute(
        """INSERT INTO results
           (student_name, group_name, discipline_id, lecture_id, score, total_questions, duration_sec, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (full_name, group_name, lecture["discipline_id"], session["lecture_id"],
         score, total, submission.duration_sec, utc_iso(datetime.now(timezone.utc))),
    )
    conn.commit()

    send_in_background([
        now_local().strftime("%Y-%m-%d %H:%M:%S"),
        full_name,
        group_name,
        lecture["discipline"],
        lecture["lecture"],
        f"{score}/{total}",
    ])

    percent = round(score * 100 / total, 1) if total else 0.0
    return {
        "score": score,
        "total": total,
        "percent": percent,
        "passed": percent >= PASS_PERCENT,
        "review": review,
        "message": "Результат збережено!",
    }


# ------------------------------------------------------------- кабінет викладача

def _where(discipline_id: Optional[int], lecture_id: Optional[int], group: Optional[str]):
    clauses, params = ["r.total_questions > 0"], []
    if discipline_id:
        clauses.append("r.discipline_id = ?")
        params.append(discipline_id)
    if lecture_id:
        clauses.append("r.lecture_id = ?")
        params.append(lecture_id)
    if group:
        clauses.append("r.group_name = ?")
        params.append(normalize_group(group))
    return "WHERE " + " AND ".join(clauses), params


_FROM = """FROM results r
           JOIN disciplines d ON d.id = r.discipline_id
           JOIN lectures l ON l.id = r.lecture_id"""
_PCT = "(r.score * 100.0 / r.total_questions)"


@app.get("/api/groups", dependencies=[Depends(require_teacher)])
def get_groups(conn: sqlite3.Connection = Depends(get_conn)):
    rows = conn.execute(
        "SELECT MIN(group_name) AS name FROM results GROUP BY lower(group_name) ORDER BY name"
    ).fetchall()
    return [r["name"] for r in rows]


@app.get("/api/results", dependencies=[Depends(require_teacher)])
def get_results(
    discipline_id: Optional[int] = None,
    lecture_id: Optional[int] = None,
    group: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    where, params = _where(discipline_id, lecture_id, group)
    rows = conn.execute(
        f"""SELECT r.id, r.student_name, r.group_name, d.name AS discipline_name,
                   l.title AS lecture_title, r.score, r.total_questions,
                   ROUND({_PCT}, 1) AS percent, r.duration_sec, r.created_at
            {_FROM} {where}
            ORDER BY r.created_at DESC, r.id DESC""",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/analytics", dependencies=[Depends(require_teacher)])
def get_analytics(
    discipline_id: Optional[int] = None,
    lecture_id: Optional[int] = None,
    group: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    where, params = _where(discipline_id, lecture_id, group)

    summary = conn.execute(
        f"""SELECT COUNT(*) AS tests,
                   COUNT(DISTINCT lower(r.student_name) || '|' || lower(r.group_name)) AS students,
                   AVG({_PCT}) AS avg_pct,
                   AVG(CASE WHEN {_PCT} >= {PASS_PERCENT} THEN 100.0 ELSE 0 END) AS pass_pct
            {_FROM} {where}""",
        params,
    ).fetchone()

    by_lecture = conn.execute(
        f"""SELECT d.name AS discipline, l.title AS lecture, COUNT(*) AS tests,
                   ROUND(AVG({_PCT}), 1) AS avg_percent
            {_FROM} {where} GROUP BY l.id ORDER BY d.name, l.id""",
        params,
    ).fetchall()

    by_group = conn.execute(
        f"""SELECT MIN(r.group_name) AS grp, COUNT(*) AS tests,
                   COUNT(DISTINCT lower(r.student_name)) AS students,
                   ROUND(AVG({_PCT}), 1) AS avg_percent
            {_FROM} {where} GROUP BY lower(r.group_name) ORDER BY avg_percent DESC""",
        params,
    ).fetchall()

    timeline = conn.execute(
        f"""SELECT substr(r.created_at, 1, 10) AS day, COUNT(*) AS tests,
                   ROUND(AVG({_PCT}), 1) AS avg_percent
            {_FROM} {where} GROUP BY day ORDER BY day DESC LIMIT 30""",
        params,
    ).fetchall()

    return {
        "total_tests": summary["tests"],
        "unique_students": summary["students"],
        "average_score_percent": round(summary["avg_pct"], 1) if summary["avg_pct"] is not None else 0.0,
        "pass_rate_percent": round(summary["pass_pct"], 1) if summary["pass_pct"] is not None else 0.0,
        "pass_threshold": PASS_PERCENT,
        "by_lecture": [dict(r) for r in by_lecture],
        "by_group": [dict(r) for r in by_group],
        "timeline": [dict(r) for r in reversed(timeline)],
    }


def _safe_cell(value):
    """Захист від CSV-ін'єкції: Excel виконує комірки, що починаються з = + - @."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@app.get("/api/export.csv", dependencies=[Depends(require_teacher)])
def export_csv(
    discipline_id: Optional[int] = None,
    lecture_id: Optional[int] = None,
    group: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_conn),
):
    rows = get_results(discipline_id, lecture_id, group, conn)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Дата (Київ)", "Студент", "Група", "Дисципліна", "Лекція", "Бал", "З", "Відсоток", "Час, с"])
    for r in rows:
        writer.writerow([
            to_local_text(r["created_at"]), _safe_cell(r["student_name"]), _safe_cell(r["group_name"]),
            r["discipline_name"], r["lecture_title"], r["score"], r["total_questions"],
            r["percent"], r["duration_sec"] if r["duration_sec"] is not None else "",
        ])
    # BOM, щоб Excel правильно відкрив українські літери
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="results.csv"'},
    )
