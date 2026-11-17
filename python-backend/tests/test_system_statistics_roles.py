"""Active role counts must share a scope, excluding inactive users and Admin."""

import pytest
from app.shared.database.session import SessionLocal
from tests.conftest import auth, login, make_user


@pytest.mark.parametrize("population", ["empty", "mixed", "only_teacher", "only_student"])
def test_system_statistics_active_roles(client, population):
    with SessionLocal() as db:
        make_user(db, email="role-admin@example.invalid", role="ADMIN")
        make_user(db, email="role-admin-off@example.invalid", role="ADMIN", is_active=False)
        if population == "mixed":
            for role, active, count in [
                ("TEACHER", True, 1),
                ("TEACHER", False, 2),
                ("STUDENT", True, 2),
                ("STUDENT", False, 1),
            ]:
                for index in range(count):
                    make_user(
                        db,
                        email=f"{role}-{active}-{index}@example.invalid",
                        role=role,
                        is_active=active,
                    )
        elif population == "only_teacher":
            make_user(db, email="only-teacher@example.invalid", role="TEACHER")
        elif population == "only_student":
            make_user(db, email="only-student@example.invalid", role="STUDENT")
    token = login(client, "role-admin@example.invalid")
    response = client.get("/api/v1/statistics/system", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    expected = {
        "empty": (1, 0, 0, 0),
        "mixed": (4, 3, 1, 2),
        "only_teacher": (2, 1, 1, 0),
        "only_student": (2, 0, 0, 1),
    }[population]
    assert (
        tuple(
            body[key] for key in ("active_users", "teachers", "active_teachers", "active_students")
        )
        == expected
    )
    assert body["published_courses"] == body["enrollments"] == body["submitted_attempts"] == 0
    assert body["generated_at"].endswith("Z")


def test_system_role_breakdown_remains_admin_only(client):
    with SessionLocal() as db:
        make_user(db, email="role-teacher@example.invalid", role="TEACHER")
        make_user(db, email="role-student@example.invalid", role="STUDENT")
    assert client.get("/api/v1/statistics/system").status_code == 401
    for email in ("role-teacher@example.invalid", "role-student@example.invalid"):
        token = login(client, email)
        response = client.get("/api/v1/statistics/system", headers=auth(token))
        assert response.status_code == 403
        assert "active_students" not in response.json()
