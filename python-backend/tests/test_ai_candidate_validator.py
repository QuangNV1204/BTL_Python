
from __future__ import annotations

import json

import pytest

from app.modules.ai.domain.candidate_validator import (
    normalize,
    parse_card_candidate,
    parse_quiz_candidate,
)
from app.modules.ai.infrastructure.mock_client import MockAIClient
from app.modules.ai.infrastructure.prompts import (
    build_flashcard_prompt,
    build_quiz_prompt,
)
from app.shared.domain.enums import Difficulty
from app.shared.error.exceptions import InvalidCandidateException


def _quiz(count: int = 1) -> str:
    return json.dumps(
        {
            "questions": [
                {
                    "content": f"Câu hỏi {index}",
                    "options": [
                        {"content": "Đúng", "is_correct": True},
                        {"content": "Sai", "is_correct": False},
                    ],
                    "explanation": "Vì đúng",
                }
                for index in range(count)
            ]
        },
        ensure_ascii=False,
    )


def test_parses_valid_quiz_candidate() -> None:
    questions = parse_quiz_candidate(_quiz(2), 2)
    assert len(questions) == 2
    assert questions[0].options[0].is_correct is True


def test_accepts_single_json_code_fence() -> None:
    raw = "```json\n" + _quiz() + "\n```"
    assert len(parse_quiz_candidate(raw, 1)) == 1


def test_rejects_unknown_field() -> None:
    payload = json.loads(_quiz())
    payload["questions"][0]["unexpected"] = True
    with pytest.raises(InvalidCandidateException, match="unexpected field"):
        parse_quiz_candidate(json.dumps(payload), 1)


def test_rejects_wrong_count() -> None:
    with pytest.raises(InvalidCandidateException, match="exactly 2 items"):
        parse_quiz_candidate(_quiz(1), 2)


def test_rejects_two_correct_options() -> None:
    payload = json.loads(_quiz())
    payload["questions"][0]["options"][1]["is_correct"] = True
    with pytest.raises(InvalidCandidateException, match="exactly one correct"):
        parse_quiz_candidate(json.dumps(payload), 1)


def test_rejects_duplicate_options_after_normalize() -> None:
    payload = json.loads(_quiz())
    payload["questions"][0]["options"][1]["content"] = "  đúng  "
    with pytest.raises(InvalidCandidateException, match="duplicate options"):
        parse_quiz_candidate(json.dumps(payload), 1)


def test_rejects_duplicate_questions() -> None:
    payload = json.loads(_quiz(2))
    payload["questions"][1]["content"] = "  câu HỎI 0 "
    with pytest.raises(InvalidCandidateException, match="duplicates an earlier question"):
        parse_quiz_candidate(json.dumps(payload), 2)


def test_rejects_non_json() -> None:
    with pytest.raises(InvalidCandidateException, match="not valid JSON"):
        parse_quiz_candidate("xin chào", 1)


def test_card_candidate_roundtrip() -> None:
    raw = json.dumps(
        {"flashcards": [{"front_text": "Mặt trước", "back_text": "Mặt sau"}]},
        ensure_ascii=False,
    )
    cards = parse_card_candidate(raw, 1)
    assert cards[0].front_text == "Mặt trước"


def test_normalize_folds_case_and_spaces() -> None:
    assert normalize("  Đây   Là  Câu ") == "đây là câu"


def test_mock_client_produces_valid_quiz_for_prompt() -> None:
    prompt = build_quiz_prompt(
        "Trái đất quay quanh mặt trời. Nước sôi ở 100 độ C. Học sinh cần thực hành.",
        2,
        Difficulty.EASY,
    )
    raw = MockAIClient().generate(prompt)
    questions = parse_quiz_candidate(raw, 2)
    assert len(questions) == 2
    assert all(len(question.options) == 4 for question in questions)


def test_mock_client_produces_valid_flashcards() -> None:
    prompt = build_flashcard_prompt("Một câu đủ dài để làm flashcard. Câu thứ hai cũng vậy.", 3)
    raw = MockAIClient().generate(prompt)
    cards = parse_card_candidate(raw, 3)
    assert len(cards) == 3
