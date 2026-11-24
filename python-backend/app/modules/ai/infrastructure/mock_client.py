
from __future__ import annotations

import json
import re

from app.modules.ai.domain.contracts import (
    AIClient,
    OptionCandidate,
)

_TASK = re.compile(r"^TASK: (QUIZ|FLASHCARD)$", re.MULTILINE)
_COUNT = re.compile(r"^COUNT: (\d+)$", re.MULTILINE)
_SOURCE = re.compile(r"<source>\n(.*)\n</source>", re.DOTALL)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MAX_SENTENCE = 300

_DISTRACTORS = (
    "Bài học không đề cập đến nội dung này.",
    "Nhận định này trái với nội dung bài học.",
    "Nội dung này chỉ đúng trong trường hợp đặc biệt, không phải ý của bài học.",
)


class MockAIClient(AIClient):
    def generate(self, prompt: str) -> str:
        task = _find(_TASK, prompt, "QUIZ")
        count = int(_find(_COUNT, prompt, "1"))
        sentences = _sentences(_find(_SOURCE, prompt, ""))

        if task == "FLASHCARD":
            payload = {"flashcards": _cards(sentences, count)}
        else:
            payload = {"questions": _questions(sentences, count)}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def provider(self) -> str:
        return "mock"

    def model(self) -> str:
        return "mock-v1"


def _questions(sentences: list[str], count: int) -> list[dict]:
    result: list[dict] = []
    for index in range(count):
        fact = sentences[index % len(sentences)]
        options: list[OptionCandidate] = [
            OptionCandidate(text, False) for text in _DISTRACTORS
        ]
        options.insert(index % (len(_DISTRACTORS) + 1), OptionCandidate(fact, True))
        result.append(
            {
                "content": f"Câu {index + 1}: Theo nội dung bài học, phát biểu nào sau đây là đúng?",
                "options": [
                    {"content": option.content, "is_correct": option.is_correct}
                    for option in options
                ],
                "explanation": f'Bài học có nêu: "{fact}"',
            }
        )
    return result


def _cards(sentences: list[str], count: int) -> list[dict]:
    return [
        {
            "front_text": f"Ý chính số {index + 1} của bài học là gì?",
            "back_text": sentences[index % len(sentences)],
        }
        for index in range(count)
    ]


def _sentences(source: str) -> list[str]:
    unique: dict[str, None] = {}
    for part in _SENTENCE_SPLIT.split(source):
        text = part.strip()
        if len(text) < 15:
            continue
        if len(text) > _MAX_SENTENCE:
            text = text[:_MAX_SENTENCE] + "…"
        unique.setdefault(text, None)
    if not unique:
        whole = source.strip()
        unique[whole[:_MAX_SENTENCE] if whole else "Nội dung bài học."] = None
    return list(unique)


def _find(pattern: re.Pattern[str], text: str, fallback: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else fallback
