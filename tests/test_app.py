"""Автоматичні тести застосунку (pytest). Запуск: pytest"""
import os
import sqlite3

import db


# ----------------------------------------------------------------- допоміжні функції

def raw_db():
    conn = sqlite3.connect(os.environ["QUIZ_DB_PATH"])
    conn.row_factory = sqlite3.Row
    return conn


def first_lecture_id(client):
    discipline = client.get("/api/disciplines").json()[0]
    return client.get(f"/api/disciplines/{discipline['id']}/lectures").json()[0]["id"]


def start_test(client, lecture_id=None, limit=10):
    lecture_id = lecture_id or first_lecture_id(client)
    response = client.get(f"/api/lectures/{lecture_id}/test", params={"limit": limit})
    assert response.status_code == 200
    return response.json()


def submit(client, test, answers, name="Іван Іванов", group="КН-21", **extra):
    payload = {"token": test["token"], "full_name": name, "group_name": group, "answers": answers}
    payload.update(extra)
    return client.post("/api/submit_test", json=payload)


def answers_for(test, correct=True):
    """Збирає відповіді: усі правильні або усі неправильні (беремо відповіді з БД)."""
    conn = raw_db()
    result = []
    for question in test["questions"]:
        right = conn.execute("SELECT correct FROM questions WHERE id = ?", (question["id"],)).fetchone()["correct"]
        chosen = right if correct else next(k for k in "ABCD" if k != right)
        result.append({"question_id": question["id"], "selected_option": chosen})
    conn.close()
    return result


# ----------------------------------------------------------------------- сторінки

def test_pages_are_served(client):
    assert client.get("/").status_code == 200
    assert "text/html" in client.get("/").headers["content-type"]
    assert client.get("/test").status_code == 200
    assert client.get("/teacher").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}


# --------------------------------------------------------------- база та довідники

def test_disciplines_and_lectures_are_listed(client):
    disciplines = client.get("/api/disciplines").json()
    assert len(disciplines) >= 2
    lectures = client.get(f"/api/disciplines/{disciplines[0]['id']}/lectures").json()
    assert lectures and all(lec["question_count"] > 0 for lec in lectures)


def test_each_question_has_valid_correct_answer(client):
    rows = raw_db().execute("SELECT correct FROM questions").fetchall()
    assert len(rows) >= 60
    assert {r["correct"] for r in rows} <= set("ABCD")


# ------------------------------------------------------------------ генерація тесту

def test_generated_test_has_unique_questions_and_no_answers(client):
    test = start_test(client)
    ids = [q["id"] for q in test["questions"]]
    assert 1 <= len(ids) <= 10
    assert len(ids) == len(set(ids))
    assert "correct" not in str(test)  # ключ відповіді не повинен потрапляти до клієнта


def test_options_keep_mapping_to_database_text(client):
    test = start_test(client)
    conn = raw_db()
    for question in test["questions"]:
        row = conn.execute("SELECT * FROM questions WHERE id = ?", (question["id"],)).fetchone()
        assert sorted(o["key"] for o in question["options"]) == ["A", "B", "C", "D"]
        for option in question["options"]:
            assert option["text"] == row[f"option_{option['key'].lower()}"]


def test_option_order_is_random(client):
    lecture_id = first_lecture_id(client)
    first_keys = {start_test(client, lecture_id)["questions"][0]["options"][0]["key"] for _ in range(25)}
    assert len(first_keys) > 1


def test_limit_is_respected_and_validated(client):
    lecture_id = first_lecture_id(client)
    assert len(start_test(client, lecture_id, limit=5)["questions"]) == 5
    assert client.get(f"/api/lectures/{lecture_id}/test", params={"limit": 0}).status_code == 422
    assert client.get("/api/lectures/99999/test").status_code == 404


# ------------------------------------------------------------------- оцінювання

def test_all_correct_gives_full_score(client):
    test = start_test(client)
    data = submit(client, test, answers_for(test, correct=True)).json()
    assert data["score"] == data["total"] == len(test["questions"])
    assert data["percent"] == 100.0 and data["passed"] is True
    assert all(item["is_correct"] for item in data["review"])


def test_all_wrong_gives_zero(client):
    test = start_test(client)
    data = submit(client, test, answers_for(test, correct=False)).json()
    assert data["score"] == 0 and data["passed"] is False


def test_unanswered_questions_count_in_total(client):
    test = start_test(client)
    one = answers_for(test, correct=True)[:1]
    data = submit(client, test, one).json()
    assert data["score"] == 1
    assert data["total"] == len(test["questions"])  # не 1/1


def test_duplicate_answers_are_not_counted_twice(client):
    test = start_test(client)
    one = answers_for(test, correct=True)[0]
    data = submit(client, test, [one] * 10).json()
    assert data["score"] == 1


def test_answers_for_foreign_questions_are_ignored(client):
    test = start_test(client)
    foreign_id = max(q["id"] for q in test["questions"]) + 1000
    data = submit(client, test, [{"question_id": foreign_id, "selected_option": "A"}]).json()
    assert data["score"] == 0 and data["total"] == len(test["questions"])


def test_token_cannot_be_reused(client):
    test = start_test(client)
    assert submit(client, test, answers_for(test)).status_code == 200
    assert submit(client, test, answers_for(test)).status_code == 409


def test_unknown_token_is_rejected(client):
    fake = {"token": "0" * 32, "questions": []}
    assert submit(client, fake, []).status_code == 404


def test_input_validation(client):
    test = start_test(client)
    assert submit(client, test, [], name=" ").status_code == 422
    assert submit(client, test, [], name="А" * 101).status_code == 422
    bad_option = [{"question_id": test["questions"][0]["id"], "selected_option": "Z"}]
    assert submit(client, test, bad_option).status_code == 422


# ---------------------------------------------------------- результати й аналітика

def test_names_and_groups_are_normalized(client):
    test = start_test(client)
    submit(client, test, answers_for(test), name="  петренко   олена ", group=" кн-21 ")
    row = client.get("/api/results").json()[0]
    assert row["student_name"] == "Петренко Олена" and row["group_name"] == "КН-21"


def test_questions_in_database_are_unique(client):
    rows = raw_db().execute("SELECT lecture_id, text FROM questions").fetchall()
    assert len(rows) == len({(r["lecture_id"], r["text"]) for r in rows})


def test_results_and_analytics(client):
    lecture_id = first_lecture_id(client)
    good = start_test(client, lecture_id)
    bad = start_test(client, lecture_id)
    submit(client, good, answers_for(good, True), name="Петренко Олена", group="КН-21")
    submit(client, bad, answers_for(bad, False), name="Мельник Іван", group="КН-22")

    results = client.get("/api/results").json()
    assert len(results) == 2
    assert {r["student_name"] for r in results} == {"Петренко Олена", "Мельник Іван"}

    stats = client.get("/api/analytics").json()
    assert stats["total_tests"] == 2
    assert stats["unique_students"] == 2
    assert stats["average_score_percent"] == 50.0
    assert stats["pass_rate_percent"] == 50.0
    assert {g["grp"] for g in stats["by_group"]} == {"КН-21", "КН-22"}
    assert len(stats["by_lecture"]) == 1

    filtered = client.get("/api/analytics", params={"group": "кн-21"}).json()
    assert filtered["total_tests"] == 1 and filtered["average_score_percent"] == 100.0
    assert client.get("/api/groups").json() == ["КН-21", "КН-22"]


def test_analytics_on_empty_database(client):
    stats = client.get("/api/analytics").json()
    assert stats["total_tests"] == 0 and stats["average_score_percent"] == 0.0


def test_csv_export_neutralizes_formulas(client):
    test = start_test(client)
    submit(client, test, answers_for(test), name="=HYPERLINK(1)")
    response = client.get("/api/export.csv")
    assert response.status_code == 200
    assert "'=Hyperlink(1)" in response.text  # ім'я нормалізоване, формула знешкоджена
    assert response.text.startswith("﻿")


# ------------------------------------------------------------------ безпека кабінету

def test_teacher_area_requires_password_when_configured(client, monkeypatch):
    monkeypatch.setenv("TEACHER_PASSWORD", "secret")
    for url in ("/teacher", "/api/results", "/api/analytics", "/api/groups", "/api/export.csv"):
        assert client.get(url).status_code == 401, url
        assert client.get(url, auth=("teacher", "wrong")).status_code == 401, url
        assert client.get(url, auth=("teacher", "secret")).status_code == 200, url
    # студентські сторінки лишаються відкритими
    assert client.get("/").status_code == 200
    assert client.get("/api/disciplines").status_code == 200


# --------------------------------------------------------------------- імпорт CSV

def test_csv_import_skips_bad_rows_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("QUIZ_DB_PATH", str(tmp_path / "import.db"))
    csv_path = tmp_path / "q.csv"
    csv_path.write_text(
        "discipline,lecture,question,a,b,c,d,correct\n"
        "Фізика,Лекція 1,Питання 1?,1,2,3,4,b\n"
        "Фізика,Лекція 1,Питання 2?,1,2,3,4,E\n"       # невірна літера
        "Фізика,Лекція 1,Питання 3?,1,2,,4,a\n",         # порожній варіант
        encoding="utf-8",
    )
    db.init_db()
    assert db.load_csv(csv_path) == 1
    assert db.load_csv(csv_path) == 1  # повторний імпорт не створює дублікатів
    conn = sqlite3.connect(tmp_path / "import.db")
    assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 1
    assert conn.execute("SELECT correct FROM questions").fetchone()[0] == "B"


def test_csv_import_updates_changed_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("QUIZ_DB_PATH", str(tmp_path / "upd.db"))
    path = tmp_path / "q.csv"
    header = "discipline,lecture,question,a,b,c,d,correct\n"
    path.write_text(header + "Фізика,Лекція 1,Питання?,1,2,3,4,a\n", encoding="utf-8")
    db.init_db()
    db.load_csv(path)
    path.write_text(header + "Фізика,Лекція 1,Питання?,1,2,3,4,c\n", encoding="utf-8")
    db.load_csv(path)
    conn = sqlite3.connect(tmp_path / "upd.db")
    assert conn.execute("SELECT COUNT(*), MAX(correct) FROM questions").fetchone() == (1, "C")
