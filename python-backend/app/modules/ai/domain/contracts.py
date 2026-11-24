
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

MIN_OPTIONS = 2
MAX_OPTIONS = 6
MAX_QUESTION_LENGTH = 4000
MAX_OPTION_LENGTH = 1000
MAX_CARD_SIDE_LENGTH = 4000

QUIZ_ROOT_FIELDS = frozenset({"questions"})
QUESTION_FIELDS = frozenset({"content", "options", "explanation"})
OPTION_FIELDS = frozenset({"content", "is_correct"})
CARD_ROOT_FIELDS = frozenset({"flashcards"})
CARD_FIELDS = frozenset({"front_text", "back_text"})


@dataclass(frozen=True)
class OptionCandidate:
    content: str
    is_correct: bool


@dataclass(frozen=True)
class QuestionCandidate:
    content: str
    options: list[OptionCandidate]
    explanation: str | None


@dataclass(frozen=True)
class CardCandidate:
    front_text: str
    back_text: str


@dataclass(frozen=True)
class QuizCandidate:
    questions: list[QuestionCandidate]


@dataclass(frozen=True)
class FlashcardCandidate:
    flashcards: list[CardCandidate]


class AiFailureReason(str, Enum):
    TIMEOUT = "TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class AIClientException(Exception):

    def __init__(self, reason: AiFailureReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class AIClient:

    def generate(self, prompt: str) -> str:
        raise NotImplementedError

    def provider(self) -> str:
        raise NotImplementedError

    def model(self) -> str:
        raise NotImplementedError
