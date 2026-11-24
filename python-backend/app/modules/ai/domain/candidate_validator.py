
from __future__ import annotations

import json
import unicodedata
from typing import Any

from app.modules.ai.domain.contracts import (
    CARD_FIELDS,
    CARD_ROOT_FIELDS,
    MAX_CARD_SIDE_LENGTH,
    MAX_OPTION_LENGTH,
    MAX_OPTIONS,
    MAX_QUESTION_LENGTH,
    MIN_OPTIONS,
    OPTION_FIELDS,
    QUESTION_FIELDS,
    QUIZ_ROOT_FIELDS,
    CardCandidate,
    OptionCandidate,
    QuestionCandidate,
)
from app.shared.error.exceptions import InvalidCandidateException


def _invalid(reason: str) -> InvalidCandidateException:
    return InvalidCandidateException(reason)


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).lower().split())


def _strip_code_fence(text: str) -> str:
    if text.startswith("```") and text.endswith("```") and len(text) > 6:
        newline = text.find("\n")
        if newline > 0:
            return text[newline + 1 : -3].strip()
    return text


def _parse_root(raw: str | None, allowed: frozenset[str]) -> dict[str, Any]:
    if raw is None or not raw.strip():
        raise _invalid("empty output")
    try:
        root = json.loads(_strip_code_fence(raw.strip()))
    except (json.JSONDecodeError, ValueError) as exc:
        raise _invalid("output is not valid JSON") from exc
    return _require_object(root, "root", allowed)


def _require_object(node: Any, path: str, allowed: frozenset[str]) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise _invalid(f"{path} must be an object")
    for name in node:
        if name not in allowed:
            raise _invalid(f"{path} has unexpected field '{name}'")
    return node


def _require_array(root: dict[str, Any], field: str, count: int) -> list[Any]:
    items = root.get(field)
    if not isinstance(items, list):
        raise _invalid(f"{field} must be an array")
    if len(items) != count:
        raise _invalid(f"{field} must contain exactly {count} items, got {len(items)}")
    return items


def _require_text(
    node: dict[str, Any], field: str, path: str, max_length: int, *, nullable: bool = False
) -> str | None:
    value = node.get(field)
    if nullable and value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(f"{path}.{field} must be a string")
    text = value.strip()
    if not nullable and (not text or len(text) > max_length):
        raise _invalid(f"{path}.{field} must be 1-{max_length} characters")
    if nullable and len(text) > max_length:
        raise _invalid(f"{path}.{field} must be at most {max_length} characters")
    return text or None


def check_question(content: str, options: list[OptionCandidate], path: str) -> None:
    if not content or not content.strip() or len(content) > MAX_QUESTION_LENGTH:
        raise _invalid(f"{path}.content must be 1-{MAX_QUESTION_LENGTH} characters")
    if len(options) < MIN_OPTIONS or len(options) > MAX_OPTIONS:
        raise _invalid(f"{path} must have {MIN_OPTIONS}-{MAX_OPTIONS} options")
    correct = sum(1 for option in options if option.is_correct)
    if correct != 1:
        raise _invalid(f"{path} must have exactly one correct option, found {correct}")
    seen: set[str] = set()
    for option in options:
        if not option.content or not option.content.strip() or len(option.content) > MAX_OPTION_LENGTH:
            raise _invalid(f"{path} option content must be 1-{MAX_OPTION_LENGTH} characters")
        key = normalize(option.content)
        if key in seen:
            raise _invalid(f"{path} has duplicate options")
        seen.add(key)


def parse_quiz_candidate(raw: str | None, count: int) -> list[QuestionCandidate]:
    root = _parse_root(raw, QUIZ_ROOT_FIELDS)
    items = _require_array(root, "questions", count)

    questions: list[QuestionCandidate] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        path = f"questions[{index}]"
        node = _require_object(item, path, QUESTION_FIELDS)
        content = _require_text(node, "content", path, MAX_QUESTION_LENGTH)
        explanation = _require_text(node, "explanation", path, MAX_QUESTION_LENGTH, nullable=True)

        option_nodes = node.get("options")
        if not isinstance(option_nodes, list):
            raise _invalid(f"{path}.options must be an array")
        options: list[OptionCandidate] = []
        for option_index, option_item in enumerate(option_nodes):
            option_path = f"{path}.options[{option_index}]"
            option_node = _require_object(option_item, option_path, OPTION_FIELDS)
            option_content = _require_text(
                option_node, "content", option_path, MAX_OPTION_LENGTH
            )
            correct = option_node.get("is_correct")
            if not isinstance(correct, bool):
                raise _invalid(f"{option_path}.is_correct must be a boolean")
            options.append(OptionCandidate(option_content, correct))

        check_question(content, options, path)

        key = normalize(content)
        if key in seen:
            raise _invalid(f"{path} duplicates an earlier question")
        seen.add(key)
        questions.append(QuestionCandidate(content, options, explanation))
    return questions


def parse_card_candidate(raw: str | None, count: int) -> list[CardCandidate]:
    root = _parse_root(raw, CARD_ROOT_FIELDS)
    items = _require_array(root, "flashcards", count)

    cards: list[CardCandidate] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        path = f"flashcards[{index}]"
        node = _require_object(item, path, CARD_FIELDS)
        front = _require_text(node, "front_text", path, MAX_CARD_SIDE_LENGTH)
        back = _require_text(node, "back_text", path, MAX_CARD_SIDE_LENGTH)
        key = normalize(front)
        if key in seen:
            raise _invalid(f"{path} duplicates an earlier card")
        seen.add(key)
        cards.append(CardCandidate(front, back))
    return cards
