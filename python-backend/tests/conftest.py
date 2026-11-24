
from __future__ import annotations

import base64
import os
import tempfile
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="learningai-tests-"))
os.environ.setdefault("JWT_SIGNING_KEY", base64.b64encode(b"test-signing-key-32-bytes-long!!").decode())
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_TMP / 'test.db'}")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
os.environ.setdefault("MAIL_USERNAME", "")
os.environ.setdefault("APP_STORAGE_LOCATION", str(_TMP / "uploads"))
os.environ.setdefault("LESSON_DOCUMENT_STORAGE", str(_TMP / "documents"))
os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("CLEANUP_DELAY_MS", "0")

from app.shared.database.base import Base, utcnow
from app.shared.database.models import (
    Category,
    Course,
    Lesson,
    User,
)
from app.shared.database.session import SessionLocal, engine


@pytest.fixture(autouse=True)
def _fresh_schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def session():
    with SessionLocal() as db:
        yield db


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def make_user(
    session,
    *,
    email: str,
    full_name: str = "Người Dùng",
    role: str = "STUDENT",
    password: str | None = None,
    is_active: bool = True,
    verified: bool = True,
) -> User:
    from app.modules.identity.application.auth_service import hash_password

    now = utcnow()
    user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password or "password1234"),
        role=role,
        is_active=is_active,
        email_verified_at=now if verified else None,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.commit()
    return user


def make_category(session, name: str = "Lập trình") -> Category:
    now = utcnow()
    category = Category(name=name, description="Mô tả", created_at=now, updated_at=now)
    session.add(category)
    session.commit()
    return category


def make_course(
    session,
    teacher: User,
    category: Category,
    *,
    title: str = "Khóa học",
    price: Decimal = Decimal("0.00"),
    published: bool = False,
    thumbnail_key: str | None = None,
) -> Course:
    now = utcnow()
    course = Course(
        teacher_id=teacher.id,
        category_id=category.id,
        title=title,
        description="Mô tả khóa học",
        thumbnail_storage_key=thumbnail_key,
        thumbnail_url=f"/api/v1/files/{thumbnail_key}" if thumbnail_key else None,
        price=price,
        is_published=published,
        created_at=now,
        updated_at=now,
    )
    session.add(course)
    session.commit()
    return course


def make_lesson(
    session,
    course: Course,
    *,
    title: str = "Bài học",
    order_index: int = 1,
    transcript: str | None = None,
    video_url: str = "https://www.youtube.com/watch?v=abc123",
) -> Lesson:
    now = utcnow()
    lesson = Lesson(
        course_id=course.id,
        title=title,
        video_url=video_url,
        transcript_text=transcript,
        order_index=order_index,
        created_at=now,
        updated_at=now,
    )
    session.add(lesson)
    session.commit()
    return lesson


def enroll(session, course: Course, student: User):
    from app.shared.database.models import CourseMember

    member = CourseMember(
        course_id=course.id, student_id=student.id, enrolled_at=utcnow()
    )
    session.add(member)
    session.commit()
    return member


def login(client, email: str, password: str = "password1234") -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


__all__ = [
    "auth",
    "client",
    "enroll",
    "login",
    "make_category",
    "make_course",
    "make_lesson",
    "make_user",
    "session",
    "utcnow",
    "datetime",
]
