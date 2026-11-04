from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import sqlite3
import random
import requests               
from datetime import datetime

app = FastAPI(title="Quiz App API")

# Підключаємо папки
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ЗМІНЮЄМО кореневий ендпоінт, щоб він віддавав HTML-сторінку
@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# Підключення папки для статичних файлів (CSS, JS) та HTML шаблонів
# Якщо у вас ще немає папок 'static' і 'templates', їх треба створити в папці quiz-app
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")

# Функція для отримання з'єднання з БД
def get_db():
    conn = sqlite3.connect("quiz.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# --- ІНТЕГРАЦІЯ З GOOGLE SHEETS ЧЕРЕЗ APPS SCRIPT ---
# ВСТАВТЕ СЮДИ ВАШЕ ДОВГЕ ПОСИЛАННЯ З GOOGLE APPS SCRIPT (те, що закінчується на /exec)
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwgXEGnlRXkKZGOAJ2xAdMxlERl1VYLrAMR4PnhUJf1-cOLXyGsWFPEtMjw1HY41aFPLA/exec"

def send_to_google_sheets(data_row):
    try:
        # Відправляємо POST-запит на наш скрипт
        response = requests.post(APPS_SCRIPT_URL, json=data_row)
        
        if response.status_code == 200:
            print("✅ Дані успішно відправлено в Google Sheets!")
        else:
            print(f"❌ Помилка відправки: статус {response.status_code}")
    except Exception as e:
        print(f"❌ Помилка з'єднання: {e}")

# --- МОДЕЛІ ДАНИХ (Pydantic) ---
class StudentInfo(BaseModel):
    full_name: str
    group_name: str
    discipline_id: int
    lecture_id: int

# --- ЕНДПОІНТИ ---

@app.get("/")
def read_root():
    return {"message": "Сервер тестування працює! Перейдіть на /docs для перегляду API."}

# 1. Отримати список всіх дисциплін
@app.get("/api/disciplines")
def get_disciplines(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.execute("SELECT id, name FROM disciplines")
    return [dict(row) for row in cursor.fetchall()]

# 2. Отримати лекції для конкретної дисципліни
@app.get("/api/disciplines/{discipline_id}/lectures")
def get_lectures(discipline_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.execute("SELECT id, title FROM lectures WHERE discipline_id = ?", (discipline_id,))
    return [dict(row) for row in cursor.fetchall()]

# 3. Згенерувати тест (випадкові питання для обраної лекції)
@app.get("/api/lectures/{lecture_id}/test")
def generate_test(lecture_id: int, limit: int = 10, db: sqlite3.Connection = Depends(get_db)):
    # Отримуємо всі питання для цієї лекції
    cursor = db.execute("SELECT id, text, option_a, option_b, option_c, option_d FROM questions WHERE lecture_id = ?", (lecture_id,))
    questions = [dict(row) for row in cursor.fetchall()]
    
    if not questions:
        raise HTTPException(status_code=404, detail="Питання для цієї лекції не знайдені")
    
    # Випадково вибираємо 10 питань (або менше, якщо їх не вистачає)
    test_questions = random.sample(questions, min(limit, len(questions)))
    
    # Перемішуємо варіанти відповідей (щоб правильна відповідь не завжди була першою)
    # Це складніше реалізувати на бекенді без зміни структури БД, тому поки залишимо як є.
    # У фронтенді ми зможемо перемішати їх за допомогою JavaScript.
    
    return {"lecture_id": lecture_id, "questions": test_questions}
# --- НОВІ ЕНДПОІНТИ ДЛЯ ТЕСТУ ---

# Додаємо модель для отримання відповідей від студента
class AnswerItem(BaseModel):
    question_id: int
    selected_option: str

class TestSubmission(BaseModel):
    full_name: str
    group_name: str
    discipline_id: int
    lecture_id: int
    answers: list[AnswerItem]

# Сторінка тесту
@app.get("/test", response_class=HTMLResponse)
def get_test_page(request: Request):
    return templates.TemplateResponse(request=request, name="test.html")

# Перевірка тесту та збереження результату
@app.post("/api/submit_test")
def submit_test(submission: TestSubmission, db: sqlite3.Connection = Depends(get_db)):
    # Отримуємо правильні відповіді для цієї лекції з бази
    cursor = db.execute("SELECT id, correct FROM questions WHERE lecture_id = ?", (submission.lecture_id,))
    correct_answers = {row["id"]: row["correct"] for row in cursor.fetchall()}
    
    score = 0
    total = len(submission.answers)
    
    # Перевіряємо кожну відповідь студента
    for ans in submission.answers:
        if ans.question_id in correct_answers:
            if ans.selected_option == correct_answers[ans.question_id]:
                score += 1
                
    # Зберігаємо результат у базу даних (SQLite)
    db.execute(
        """INSERT INTO results 
           (student_name, group_name, discipline_id, lecture_id, score, total_questions) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (submission.full_name, submission.group_name, submission.discipline_id, 
         submission.lecture_id, score, total)
    )
    db.commit()
    
    # --- ДОДАНО: ВІДПРАВКА В GOOGLE SHEETS ---
    try:
        # 1. Дістаємо назви для таблиці
        disc_name = db.execute("SELECT name FROM disciplines WHERE id=?", (submission.discipline_id,)).fetchone()["name"]
        lect_name = db.execute("SELECT title FROM lectures WHERE id=?", (submission.lecture_id,)).fetchone()["title"]
        
        # 2. Формуємо дату та рядок даних
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [now, submission.full_name, submission.group_name, disc_name, lect_name, f"{score}/{total}"]
        
        # 3. Викликаємо функцію відправки
        send_to_google_sheets(row_data)
    except Exception as e:
        # Якщо станеться помилка з таблицею, тест все одно зарахується, але в консолі буде попередження
        print(f"Помилка при формуванні даних для Google Sheets: {e}")
    # -----------------------------------------

    return {"score": score, "total": total, "message": "Результат збережено!"}

# --- КАБІНЕТ ВИКЛАДАЧА ---

# 1. Сторінка для викладача
@app.get("/teacher", response_class=HTMLResponse)
def get_teacher_page(request: Request):
    return templates.TemplateResponse(request=request, name="teacher.html")

# 2. API для отримання всіх результатів з бази
@app.get("/api/results")
def get_results(db: sqlite3.Connection = Depends(get_db)):
    # Отримуємо результати разом із назвами дисциплін та лекцій
    query = """
        SELECT r.id, r.student_name, r.group_name, d.name as discipline_name, 
               l.title as lecture_title, r.score, r.total_questions, r.created_at
        FROM results r
        JOIN disciplines d ON r.discipline_id = d.id
        JOIN lectures l ON r.lecture_id = l.id
        ORDER BY r.created_at DESC
    """
    cursor = db.execute(query)
    return [dict(row) for row in cursor.fetchall()]

# 3. API для аналітики (середній бал, кількість тестів тощо)
@app.get("/api/analytics")
def get_analytics(db: sqlite3.Connection = Depends(get_db)):
    # 1. Загальна кількість пройдених тестів
    total_tests = db.execute("SELECT COUNT(*) as count FROM results").fetchone()["count"]
    
    # 2. Кількість унікальних студентів
    unique_students = db.execute("SELECT COUNT(DISTINCT student_name) as count FROM results").fetchone()["count"]
    
    # 3. Середній відсоток успішності (рахуємо як середнє арифметичне відсотків по кожному тесту)
    avg_score_query = """
        SELECT AVG((score * 100.0) / total_questions) as avg_pct 
        FROM results WHERE total_questions > 0
    """
    avg_result = db.execute(avg_score_query).fetchone()
    avg_score = round(avg_result["avg_pct"], 1) if avg_result["avg_pct"] else 0.0

    return {
        "total_tests": total_tests,
        "unique_students": unique_students,
        "average_score_percent": avg_score
    }