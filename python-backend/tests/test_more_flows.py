
from __future__ import annotations

import io
import uuid

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


def test_teacher_request_approval_promotes_student(client):
    with SessionLocal() as db:
        make_user(db, email="admin2@example.com", role="ADMIN")
        make_user(db, email="wannabe@example.com")

    token = login(client, "wannabe@example.com")
    created = client.post(
        "/api/v1/teacher-requests",
        json={"reason": "Tôi muốn dạy"},
        headers=auth(token),
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    duplicate = client.post(
        "/api/v1/teacher-requests",
        json={"reason": "Lần nữa"},
        headers=auth(token),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == "A pending teacher request already exists"

    admin_token = login(client, "admin2@example.com")
    approved = client.patch(
        f"/api/v1/teacher-requests/{request_id}/decision",
        json={"status": "APPROVED", "decision_note": "Đồng ý"},
        headers=auth(admin_token),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"

    me = client.get("/api/v1/users/me", headers=auth(token))
    assert me.json()["role"] == "TEACHER"

    again = client.patch(
        f"/api/v1/teacher-requests/{request_id}/decision",
        json={"status": "REJECTED"},
        headers=auth(admin_token),
    )
    assert again.status_code == 409


def test_admin_cannot_approve_own_request(client):
    with SessionLocal() as db:
        make_user(db, email="selfadmin@example.com", role="ADMIN")

    token = login(client, "selfadmin@example.com")
    response = client.post(
        "/api/v1/teacher-requests", json={"reason": "Tự duyệt"}, headers=auth(token)
    )

    assert response.status_code == 403


def test_flashcard_lifecycle_and_student_visibility(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="fteacher@example.com", role="TEACHER")
        student = make_user(db, email="fstudent@example.com")
        category = make_category(db, "Vật lý")
        course = make_course(db, teacher, category, published=True)
        lesson = make_lesson(db, course)
        enroll(db, course, student)
        lesson_id = lesson.id

    teacher_token = login(client, "fteacher@example.com")
    created = client.post(
        f"/api/v1/lessons/{lesson_id}/flashcards",
        json={"front_text": "Câu hỏi", "back_text": "Trả lời"},
        headers=auth(teacher_token),
    )
    assert created.status_code == 201, created.text
    card_id = created.json()["id"]
    assert created.json()["status"] == "DRAFT"

    student_token = login(client, "fstudent@example.com")
    hidden = client.get(
        f"/api/v1/lessons/{lesson_id}/flashcards", headers=auth(student_token)
    )
    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0

    published = client.patch(
        f"/api/v1/flashcards/{card_id}/publication",
        json={"status": "PUBLISHED"},
        headers=auth(teacher_token),
    )
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"

    visible = client.get(
        f"/api/v1/lessons/{lesson_id}/flashcards", headers=auth(student_token)
    )
    assert visible.json()["total"] == 1


    edit = client.patch(
        f"/api/v1/flashcards/{card_id}",
        json={"front_text": "Đổi"},
        headers=auth(teacher_token),
    )
    assert edit.status_code == 409
    assert edit.json()["message"] == "Only a draft flashcard can be changed"

    closed = client.patch(
        f"/api/v1/flashcards/{card_id}/publication",
        json={"status": "CLOSED"},
        headers=auth(teacher_token),
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def test_flashcard_publication_rejects_draft_target(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="f2teacher@example.com", role="TEACHER")
        category = make_category(db, "Âm nhạc")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "f2teacher@example.com")
    card = client.post(
        f"/api/v1/lessons/{lesson_id}/flashcards",
        json={"front_text": "A", "back_text": "B"},
        headers=auth(token),
    ).json()
    response = client.patch(
        f"/api/v1/flashcards/{card['id']}/publication",
        json={"status": "DRAFT"},
        headers=auth(token),
    )
    assert response.status_code == 400
    assert response.json()["details"][0]["field"] == "status"


def test_draft_save_is_idempotent_by_request_id(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="dteacher@example.com", role="TEACHER")
        category = make_category(db, "Lịch sử")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "dteacher@example.com")
    quiz = client.post(
        f"/api/v1/lessons/{lesson_id}/quizzes",
        json={"title": "Draft"},
        headers=auth(token),
    ).json()
    quiz_id = quiz["id"]
    request_id = str(uuid.uuid4())
    payload = {
        "request_id": request_id,
        "title": "Tiêu đề mới",
        "questions": [
            {
                "content": "Câu 1",
                "explanation": "Giải thích",
                "order_index": 0,
                "options": [
                    {"content": "A", "is_correct": True, "order_index": 0},
                    {"content": "B", "is_correct": False, "order_index": 1},
                ],
            }
        ],
    }
    first = client.put(
        f"/api/v1/quizzes/{quiz_id}/draft", json=payload, headers=auth(token)
    )
    assert first.status_code == 200, first.text
    assert first.json()["title"] == "Tiêu đề mới"
    assert len(first.json()["questions"]) == 1

    replay = client.put(
        f"/api/v1/quizzes/{quiz_id}/draft", json=payload, headers=auth(token)
    )
    assert replay.status_code == 200
    assert replay.json() == first.json()

    changed = dict(payload, title="Khác")
    conflict = client.put(
        f"/api/v1/quizzes/{quiz_id}/draft", json=changed, headers=auth(token)
    )
    assert conflict.status_code == 409
    assert "request_id was already used" in conflict.json()["message"]


def test_draft_save_requires_order_index_to_match_position(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="d2teacher@example.com", role="TEACHER")
        category = make_category(db, "Triết học")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "d2teacher@example.com")
    quiz_id = client.post(
        f"/api/v1/lessons/{lesson_id}/quizzes",
        json={"title": "Draft"},
        headers=auth(token),
    ).json()["id"]

    response = client.put(
        f"/api/v1/quizzes/{quiz_id}/draft",
        json={
            "request_id": str(uuid.uuid4()),
            "title": "T",
            "questions": [
                {
                    "content": "Câu 1",
                    "explanation": "E",
                    "order_index": 3,
                    "options": [
                        {"content": "A", "is_correct": True, "order_index": 0},
                        {"content": "B", "is_correct": False, "order_index": 1},
                    ],
                }
            ],
        },
        headers=auth(token),
    )
    assert response.status_code == 400
    assert response.json()["message"] == "Question order_index must match array position"


def test_course_statistics_scoped_to_owner(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="steacher@example.com", role="TEACHER")
        make_user(db, email="otherteacher@example.com", role="TEACHER")
        student = make_user(db, email="sstudent@example.com")
        category = make_category(db, "Thể dục")
        course = make_course(db, teacher, category, published=True)
        make_lesson(db, course)
        enroll(db, course, student)
        course_id = course.id

    token = login(client, "steacher@example.com")
    response = client.get(f"/api/v1/statistics/courses/{course_id}", headers=auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["course_id"] == str(course_id)
    assert body["enrolled_students"] == 1
    assert body["completion_rate"] == 0.0

    other_token = login(client, "otherteacher@example.com")
    forbidden = client.get(
        f"/api/v1/statistics/courses/{course_id}", headers=auth(other_token)
    )
    assert forbidden.status_code == 403


def test_system_statistics_requires_admin(client):
    with SessionLocal() as db:
        make_user(db, email="sysadmin@example.com", role="ADMIN")
        make_user(db, email="sysstudent@example.com")

    admin_token = login(client, "sysadmin@example.com")
    ok = client.get("/api/v1/statistics/system", headers=auth(admin_token))
    assert ok.status_code == 200
    assert ok.json()["active_users"] == 2
    assert ok.json()["teachers"] == 0

    student_token = login(client, "sysstudent@example.com")
    denied = client.get("/api/v1/statistics/system", headers=auth(student_token))
    assert denied.status_code == 403


def test_document_upload_extracts_text_and_downloads(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="docteacher@example.com", role="TEACHER")
        category = make_category(db, "Ngoại khoá")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "docteacher@example.com")
    content = "Quang hợp là quá trình cây xanh tổng hợp chất hữu cơ."
    uploaded = client.post(
        f"/api/v1/lessons/{lesson_id}/documents",
        files={"file": ("bai-hoc.txt", io.BytesIO(content.encode()), "text/plain")},
        headers=auth(token),
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["original_name"] == "bai-hoc.txt"
    assert document["text_extracted"] is True
    assert document["size_bytes"] == len(content.encode())

    listing = client.get(f"/api/v1/lessons/{lesson_id}/documents", headers=auth(token))
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    download = client.get(
        f"/api/v1/documents/{document['id']}/content", headers=auth(token)
    )
    assert download.status_code == 200
    assert download.content == content.encode()


def test_document_upload_rejects_unsupported_type(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="doc2teacher@example.com", role="TEACHER")
        category = make_category(db, "Mỹ thuật")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "doc2teacher@example.com")
    response = client.post(
        f"/api/v1/lessons/{lesson_id}/documents",
        files={"file": ("a.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth(token),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_FILE_TYPE"


def test_lesson_with_quiz_content_cannot_be_deleted(client):
    with SessionLocal() as db:
        teacher = make_user(db, email="delteacher@example.com", role="TEACHER")
        category = make_category(db, "Y khoa")
        course = make_course(db, teacher, category)
        lesson = make_lesson(db, course)
        lesson_id = lesson.id

    token = login(client, "delteacher@example.com")
    client.post(
        f"/api/v1/lessons/{lesson_id}/quizzes",
        json={"title": "Quiz"},
        headers=auth(token),
    )
    response = client.delete(f"/api/v1/lessons/{lesson_id}", headers=auth(token))
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


def test_admin_lists_users_with_pagination(client):
    with SessionLocal() as db:
        make_user(db, email="listadmin@example.com", role="ADMIN")
        for index in range(3):
            make_user(db, email=f"user{index}@example.com")

    token = login(client, "listadmin@example.com")
    response = client.get("/api/v1/users?page=1&page_size=2", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total"] == 4
    assert len(body["items"]) == 2

    filtered = client.get("/api/v1/users?email=USER1", headers=auth(token))
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_profile_update_and_status_lock(client):
    with SessionLocal() as db:
        admin = make_user(db, email="statadmin@example.com", role="ADMIN")
        user = make_user(db, email="stat@example.com")
        user_id = user.id
        _ = admin

    token = login(client, "stat@example.com")
    updated = client.patch(
        "/api/v1/users/me", json={"full_name": "Tên Mới"}, headers=auth(token)
    )
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Tên Mới"

    admin_token = login(client, "statadmin@example.com")
    locked = client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"is_active": False},
        headers=auth(admin_token),
    )
    assert locked.status_code == 200

    denied = client.get("/api/v1/users/me", headers=auth(token))
    assert denied.status_code == 403
    assert denied.json()["code"] == "ACCOUNT_INACTIVE"


def test_unsupported_sort_field_is_validation_error(client):
    with SessionLocal() as db:
        make_user(db, email="sortadmin@example.com", role="ADMIN")

    token = login(client, "sortadmin@example.com")
    response = client.get("/api/v1/users?sort=password_hash,asc", headers=auth(token))
    assert response.status_code == 400
    assert response.json()["message"] == "Unsupported sort field"
