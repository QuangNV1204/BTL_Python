"""Shared API remains compatible with older Java statistics responses."""

import re
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"


def test_active_role_fields_are_additive_not_required_in_shared_contract():
    content = CONTRACT.read_text(encoding="utf-8")
    section = content.split("    SystemStatistics:\n", 1)[1].split("    Id:\n", 1)[0]
    required = re.search(r"required: \[([^\]]+)\]", section).group(1)
    required_fields = {item.strip() for item in required.split(",")}
    assert required_fields == {
        "active_users",
        "teachers",
        "published_courses",
        "enrollments",
        "submitted_attempts",
        "generated_at",
    }
    assert "active_teachers:" in section
    assert "active_students:" in section
