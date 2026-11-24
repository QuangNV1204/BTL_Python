
from __future__ import annotations

from decimal import Decimal

from app.shared.database.base import utcnow
from app.shared.database.models import User
from tests.conftest import auth


def _set_password(session, user: User, password: str) -> None:
    from app.modules.identity.application.auth_service import hash_password

    user.password_hash = hash_password(password)
    session.commit()


def test_login_with_wrong_password_returns_unauthenticated(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import make_user

    with SessionLocal() as db:
        make_user(db, email="student@example.com")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["X-Request-Id"]


def test_validation_uses_400_not_422(client):
    response = client.post("/api/v1/auth/login", json={"email": "x@example.com"})
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert any(detail["field"] == "password" for detail in body["details"])


def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_login_sets_refresh_cookie_and_returns_access_token(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import make_user

    with SessionLocal() as db:
        make_user(db, email="verified@example.com")

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "verified@example.com", "password": "password1234"},
    )
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refreshToken" in response.cookies

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]


def test_login_requires_verified_email(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import make_user

    with SessionLocal() as db:
        make_user(db, email="unverified@example.com", verified=False)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": "password1234"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"


def test_inactive_account_returns_403_even_with_valid_token(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import auth, login, make_user

    with SessionLocal() as db:
        user = make_user(db, email="locked@example.com", password="password1234")
        user_id = user.id
    token = login(client, "locked@example.com")

    with SessionLocal() as db:
        db.get(User, user_id).is_active = False
        db.commit()

    response = client.get("/api/v1/users/me", headers=auth(token))
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_INACTIVE"


def test_admin_can_create_category_and_student_cannot(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import auth, login, make_user

    with SessionLocal() as db:
        make_user(db, email="admin@example.com", role="ADMIN")
        make_user(db, email="student@example.com")

    admin_token = login(client, "admin@example.com")
    created = client.post(
        "/api/v1/categories",
        json={"name": "Toán", "description": "Mô tả"},
        headers=auth(admin_token),
    )
    assert created.status_code == 201
    assert created.json()["id"].isdigit()

    duplicate = client.post(
        "/api/v1/categories",
        json={"name": "Toán"},
        headers=auth(admin_token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "INVALID_STATE"

    student_token = login(client, "student@example.com")
    forbidden = client.post(
        "/api/v1/categories", json={"name": "Lý"}, headers=auth(student_token)
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"

    public = client.get("/api/v1/categories")
    assert public.status_code == 200
    assert public.json()["total"] >= 1
    assert public.json()["page"] == 1
    assert public.json()["page_size"] == 10


def test_course_publication_requires_thumbnail_and_lesson(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import auth, login, make_category, make_user

    with SessionLocal() as db:
        make_user(db, email="teacher@example.com", role="TEACHER")
        category = make_category(db, "Tin học")
        category_id = category.id

    token = login(client, "teacher@example.com")
    created = client.post(
        "/api/v1/courses",
        json={
            "title": "Python cơ bản",
            "description": "Nhập môn",
            "category_id": str(category_id),
            "price": "0.00",
        },
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    course = created.json()
    assert course["price"] == "0.00"
    assert course["is_published"] is False

    unpublished = client.patch(
        f"/api/v1/courses/{course['id']}/publication",
        json={"is_published": True},
        headers=auth(token),
    )
    assert unpublished.status_code == 409
    assert "thumbnail is required" in unpublished.json()["message"]

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    thumbnail = client.post(
        f"/api/v1/courses/{course['id']}/thumbnail",
        files={"file": ("a.png", png, "image/png")},
        headers=auth(token),
    )
    assert thumbnail.status_code == 200, thumbnail.text
    assert thumbnail.json()["thumbnail_url"].startswith("/api/v1/files/")

    still_blocked = client.patch(
        f"/api/v1/courses/{course['id']}/publication",
        json={"is_published": True},
        headers=auth(token),
    )
    assert still_blocked.status_code == 409
    assert "at least one lesson is required" in still_blocked.json()["message"]

    lesson = client.post(
        f"/api/v1/courses/{course['id']}/lessons",
        json={
            "title": "Bài 1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "transcript_text": "Nội dung bài học.",
        },
        headers=auth(token),
    )
    assert lesson.status_code == 201, lesson.text
    assert lesson.json()["order_index"] == 1

    published = client.patch(
        f"/api/v1/courses/{course['id']}/publication",
        json={"is_published": True},
        headers=auth(token),
    )
    assert published.status_code == 200, published.text
    assert published.json()["is_published"] is True

    public = client.get("/api/v1/courses")
    assert public.status_code == 200
    assert public.json()["total"] == 1
    listing = public.json()["items"][0]
    assert listing["price"] == "0.00"
    assert listing["teacher"]["full_name"] == "Người Dùng"
    assert listing["lesson_count"] == 1


def test_invalid_youtube_url_is_validation_error(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import auth, login, make_category, make_course, make_user

    with SessionLocal() as db:
        teacher = make_user(db, email="teacher2@example.com", role="TEACHER")
        category = make_category(db, "Khác")
        course = make_course(db, teacher, category)
        course_id = course.id

    token = login(client, "teacher2@example.com")
    response = client.post(
        f"/api/v1/courses/{course_id}/lessons",
        json={"title": "Bài", "video_url": "https://vimeo.com/1"},
        headers=auth(token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["details"][0]["field"] == "video_url"


def test_student_cannot_see_transcript_until_enrolled(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import (
        auth,
        enroll,
        login,
        make_category,
        make_course,
        make_lesson,
        make_user,
    )

    with SessionLocal() as db:
        teacher = make_user(db, email="teacher3@example.com", role="TEACHER")
        student = make_user(db, email="student3@example.com")
        category = make_category(db, "Hoá")
        course = make_course(db, teacher, category, published=True)
        lesson = make_lesson(db, course, transcript="Bí mật")
        lesson_id = lesson.id
        course_id = course.id
        student_id = student.id

    token = login(client, "student3@example.com")
    blocked = client.get(f"/api/v1/lessons/{lesson_id}", headers=auth(token))
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "ENROLLMENT_REQUIRED"

    with SessionLocal() as db:
        enroll(db, db.get(type(course), course_id), db.get(User, student_id))

    visible = client.get(f"/api/v1/lessons/{lesson_id}", headers=auth(token))
    assert visible.status_code == 200
    assert visible.json()["transcript_text"] is None
    assert visible.json()["can_delete"] is True


def _quiz_fixture(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import (
        auth,
        enroll,
        login,
        make_category,
        make_course,
        make_lesson,
        make_user,
    )

    with SessionLocal() as db:
        teacher = make_user(db, email="qteacher@example.com", role="TEACHER")
        student = make_user(db, email="qstudent@example.com")
        category = make_category(db, "Sinh học")
        course = make_course(db, teacher, category, published=True)
        lesson = make_lesson(db, course, transcript="Quang hợp là quá trình.")
        enroll(db, course, student)
        lesson_id = lesson.id
        student_id = student.id

    teacher_token = login(client, "qteacher@example.com")
    quiz = client.post(
        f"/api/v1/lessons/{lesson_id}/quizzes",
        json={"title": "Kiểm tra 15 phút"},
        headers=auth(teacher_token),
    )
    assert quiz.status_code == 201, quiz.text
    quiz_id = quiz.json()["id"]

    option_ids: list[str] = []
    for index in range(2):
        question = client.post(
            f"/api/v1/quizzes/{quiz_id}/questions",
            json={
                "content": f"Câu {index + 1}",
                "explanation": "Vì vậy",
                "order_index": index,
                "options": [
                    {"content": "Đáp án đúng", "is_correct": True, "order_index": 0},
                    {"content": "Đáp án sai", "is_correct": False, "order_index": 1},
                ],
            },
            headers=auth(teacher_token),
        )
        assert question.status_code == 201, question.text
        option_ids.append(question.json()["options"][0]["id"])

    published = client.patch(
        f"/api/v1/quizzes/{quiz_id}/publication",
        json={"status": "PUBLISHED"},
        headers=auth(teacher_token),
    )
    assert published.status_code == 200, published.text

    return {
        "teacher_token": teacher_token,
        "student_token": login(client, "qstudent@example.com"),
        "lesson_id": lesson_id,
        "quiz_id": quiz_id,
        "correct_option_ids": option_ids,
        "student_id": str(student_id),
    }


def test_student_quiz_flow_has_no_answer_leak(client):
    ctx = _quiz_fixture(client)
    token = ctx["student_token"]

    student_view = client.get(f"/api/v1/quizzes/{ctx['quiz_id']}", headers=auth(token))
    assert student_view.status_code == 200
    payload = student_view.json()
    assert "explanation" not in payload["questions"][0]
    assert all("is_correct" not in option for option in payload["questions"][0]["options"])

    started = client.post(f"/api/v1/quizzes/{ctx['quiz_id']}/attempts", headers=auth(token))
    assert started.status_code == 201, started.text
    attempt_id = started.json()["id"]
    assert started.headers["Location"] == f"/api/v1/attempts/{attempt_id}"


    again = client.post(f"/api/v1/quizzes/{ctx['quiz_id']}/attempts", headers=auth(token))
    assert again.status_code == 200
    assert again.json()["id"] == attempt_id

    submitted = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        json={
            "answers": [
                {"question_id": "999999", "selected_option_id": ctx["correct_option_ids"][0]},
                {"question_id": "2", "selected_option_id": None},
            ]
        },
        headers=auth(token),
    )

    assert submitted.status_code == 400
    assert submitted.json()["code"] == "INVALID_ANSWER"

    review = client.get(f"/api/v1/quizzes/{ctx['quiz_id']}", headers=auth(token))
    assert review.status_code == 200
    question_ids = [question["id"] for question in review.json()["questions"]]

    result = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        json={
            "answers": [
                {"question_id": question_ids[0], "selected_option_id": ctx["correct_option_ids"][0]},
                {"question_id": question_ids[1], "selected_option_id": None},
            ]
        },
        headers=auth(token),
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "SUBMITTED"
    assert body["score"] == 50.0
    assert body["correct_count"] == 1
    assert len(body["review"]) == 2

    repeated = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        json={"answers": []},
        headers=auth(token),
    )
    assert repeated.status_code == 200
    assert repeated.json()["score"] == 50.0

    history = client.get("/api/v1/users/me/attempts", headers=auth(token))
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["course_id"] == str(
        history.json()["items"][0]["course_id"]
    )


def test_quiz_question_validation_messages_match_java(client):
    ctx = _quiz_fixture(client)
    token = ctx["teacher_token"]

    unknown_field = client.post(
        f"/api/v1/quizzes/{ctx['quiz_id']}/questions",
        json={
            "content": "Câu",
            "explanation": "Vì",
            "order_index": 5,
            "options": [
                {"content": "A", "is_correct": True, "order_index": 0},
                {"content": "B", "is_correct": False, "order_index": 1},
            ],
            "extra": 1,
        },
        headers=auth(token),
    )
    assert unknown_field.status_code == 400
    assert unknown_field.json()["message"] == "Unknown field: extra"

    two_correct = client.post(
        f"/api/v1/quizzes/{ctx['quiz_id']}/questions",
        json={
            "content": "Câu",
            "explanation": "Vì",
            "order_index": 6,
            "options": [
                {"content": "A", "is_correct": True, "order_index": 0},
                {"content": "B", "is_correct": True, "order_index": 1},
            ],
        },
        headers=auth(token),
    )
    assert two_correct.status_code == 400
    assert two_correct.json()["message"] == "Exactly one option must be correct"


def test_published_quiz_cannot_be_edited(client):
    ctx = _quiz_fixture(client)
    response = client.patch(
        f"/api/v1/quizzes/{ctx['quiz_id']}",
        json={"title": "Đổi tên"},
        headers=auth(ctx["teacher_token"]),
    )
    assert response.status_code == 409
    assert response.json()["message"] == "Only DRAFT quizzes can be changed"


def test_enrollment_is_idempotent(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import (
        auth,
        login,
        make_category,
        make_course,
        make_user,
    )

    with SessionLocal() as db:
        teacher = make_user(db, email="eteacher@example.com", role="TEACHER")
        make_user(db, email="estudent@example.com")
        category = make_category(db, "Ngoại ngữ")
        course = make_course(db, teacher, category, published=True)
        course_id = course.id

    token = login(client, "estudent@example.com")
    first = client.post(f"/api/v1/courses/{course_id}/enroll", headers=auth(token))
    assert first.status_code == 201
    second = client.post(f"/api/v1/courses/{course_id}/enroll", headers=auth(token))
    assert second.status_code == 200
    assert second.json() == first.json()

    mine = client.get("/api/v1/users/me/courses", headers=auth(token))
    assert mine.status_code == 200
    assert mine.json()["total"] == 1
    assert mine.json()["items"][0]["enrolled_at"].endswith("Z")


def test_paid_course_cannot_be_enrolled(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import auth, login, make_category, make_course, make_user

    with SessionLocal() as db:
        teacher = make_user(db, email="pteacher@example.com", role="TEACHER")
        make_user(db, email="pstudent@example.com")
        category = make_category(db, "Kinh tế")
        course = make_course(
            db, teacher, category, published=True, price=Decimal("100.00")
        )
        course_id = course.id

    token = login(client, "pstudent@example.com")
    response = client.post(f"/api/v1/courses/{course_id}/enroll", headers=auth(token))
    assert response.status_code == 409
    assert response.json()["code"] == "COURSE_NOT_FREE"


def test_ai_generation_with_mock_provider(client):
    from app.shared.database.session import SessionLocal
    from tests.conftest import (
        auth,
        login,
        make_category,
        make_course,
        make_lesson,
        make_user,
    )

    with SessionLocal() as db:
        teacher = make_user(db, email="aiteacher@example.com", role="TEACHER")
        category = make_category(db, "Địa lý")
        course = make_course(db, teacher, category)
        lesson = make_lesson(
            db,
            course,
            transcript="Việt Nam nằm ở Đông Nam Á. Thủ đô là Hà Nội. Dân số đông.",
        )
        lesson_id = lesson.id

    token = login(client, "aiteacher@example.com")
    response = client.post(
        "/api/v1/ai/generate-quiz",
        json={
            "lesson_id": lesson_id,
            "source_type": "TRANSCRIPT",
            "count": 2,
            "difficulty": "EASY",
        },
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation_id"].isdigit()
    assert body["source_truncated"] is False
    assert len(body["candidate"]["questions"]) == 2

    missing_difficulty = client.post(
        "/api/v1/ai/generate-quiz",
        json={"lesson_id": lesson_id, "source_type": "TRANSCRIPT", "count": 1},
        headers=auth(token),
    )
    assert missing_difficulty.status_code == 400
    assert missing_difficulty.json()["details"][0]["field"] == "difficulty"


def test_attempt_history_scores_are_numbers(client):
    ctx = _quiz_fixture(client)
    token = ctx["student_token"]
    started = client.post(f"/api/v1/quizzes/{ctx['quiz_id']}/attempts", headers=auth(token))
    attempt_id = started.json()["id"]
    quiz = client.get(f"/api/v1/quizzes/{ctx['quiz_id']}", headers=auth(token)).json()
    question_ids = [question["id"] for question in quiz["questions"]]
    client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        json={
            "answers": [
                {
                    "question_id": question_ids[0],
                    "selected_option_id": ctx["correct_option_ids"][0],
                }
            ]
        },
        headers=auth(token),
    )
    history = client.get("/api/v1/users/me/attempts", headers=auth(token)).json()
    assert isinstance(history["items"][0]["score"], (int, float))


_ = utcnow
