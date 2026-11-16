"""Prompt gửi AI, sao nguyên AiPromptBuilder.java.

Ba dòng đầu (TASK/COUNT/DIFFICULTY) là header cố định: model đọc như yêu cầu và
MockAIClient đọc để sinh đúng loại/số lượng. Đổi nội dung prompt thì tăng
*_PROMPT_VERSION (ghi vào ai_generations.prompt_version để tra vết).
"""

from __future__ import annotations

from app.shared.domain.enums import Difficulty

QUIZ_PROMPT_VERSION = "quiz-v1"
FLASHCARD_PROMPT_VERSION = "flashcard-v1"


def build_quiz_prompt(source_text: str, count: int, difficulty: Difficulty) -> str:
    return (
        "TASK: QUIZ\n"
        f"COUNT: {count}\n"
        f"DIFFICULTY: {difficulty.value}\n"
        "\n"
        f"Write exactly {count} multiple-choice questions that test understanding of the lesson in <source>.\n"
        f"Difficulty {difficulty.value}: EASY = recall of facts stated in the lesson, MEDIUM = understanding and simple "
        "application, HARD = analysis or combining several ideas.\n"
        "Rules:\n"
        "- Use only information from the lesson. Write in the same language as the lesson.\n"
        '- Each question has 2 to 6 options and exactly one option with "is_correct": true.\n'
        "- No duplicate questions, no duplicate options within a question, no empty text.\n"
        "- Question content at most 4000 characters, each option at most 1000 characters.\n"
        '- "explanation" briefly says why the correct option is right.\n'
        "Output exactly this JSON shape and nothing else:\n"
        '{"questions":[{"content":"...","options":[{"content":"...","is_correct":true},'
        '{"content":"...","is_correct":false}],"explanation":"..."}]}\n'
        "\n"
        "<source>\n"
        f"{_sanitize(source_text)}\n"
        "</source>\n"
    )


def build_flashcard_prompt(source_text: str, count: int) -> str:
    return (
        "TASK: FLASHCARD\n"
        f"COUNT: {count}\n"
        "\n"
        f"Write exactly {count} flashcards for the key ideas of the lesson in <source>.\n"
        "Rules:\n"
        "- Use only information from the lesson. Write in the same language as the lesson.\n"
        '- "front_text" is a short question or term, "back_text" is a concise answer or definition.\n'
        "- No duplicate cards, no empty text, each side at most 4000 characters.\n"
        "Output exactly this JSON shape and nothing else:\n"
        '{"flashcards":[{"front_text":"...","back_text":"..."}]}\n'
        "\n"
        "<source>\n"
        f"{_sanitize(source_text)}\n"
        "</source>\n"
    )


def _sanitize(source_text: str) -> str:
    """Không để nội dung bài học tự đóng thẻ source (chống prompt injection đơn giản)."""
    return source_text.replace("</source>", "</ source>").replace("<source>", "< source>")
