"""Mã lỗi và HTTP status tương ứng, giữ đúng ErrorCode của java-backend."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"

    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    INVALID_EMAIL_VERIFICATION_TOKEN = "INVALID_EMAIL_VERIFICATION_TOKEN"
    INVALID_PASSWORD_RESET_TOKEN = "INVALID_PASSWORD_RESET_TOKEN"
    EMAIL_SEND_FAILED = "EMAIL_SEND_FAILED"

    ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"

    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    ENROLLMENT_REQUIRED = "ENROLLMENT_REQUIRED"
    NOT_FOUND = "NOT_FOUND"
    INVALID_STATE = "INVALID_STATE"
    INVALID_QUIZ = "INVALID_QUIZ"
    INVALID_ANSWER = "INVALID_ANSWER"
    RESOURCE_IN_USE = "RESOURCE_IN_USE"

    COURSE_NOT_FREE = "COURSE_NOT_FREE"
    LESSON_DELETE_BLOCKED = "LESSON_DELETE_BLOCKED"

    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    AI_OUTPUT_INVALID = "AI_OUTPUT_INVALID"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    AI_TIMEOUT = "AI_TIMEOUT"
    SOURCE_TEXT_EMPTY = "SOURCE_TEXT_EMPTY"
    STORAGE_ERROR = "STORAGE_ERROR"
    UNCATEGORIZED_EXCEPTION = "UNCATEGORIZED_EXCEPTION"

    USER_NOT_FOUND = "USER_NOT_FOUND"
    EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"


# ErrorCode → (HTTP status, message mặc định), sao nguyên ErrorCode.java.
ERROR_SPEC: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.VALIDATION_ERROR: (400, "Invalid data"),
    ErrorCode.EMAIL_NOT_VERIFIED: (403, "Email has not been verified"),
    ErrorCode.INVALID_EMAIL_VERIFICATION_TOKEN: (400, "Verification link is invalid or expired"),
    ErrorCode.INVALID_PASSWORD_RESET_TOKEN: (400, "Password reset link is invalid or expired"),
    ErrorCode.EMAIL_SEND_FAILED: (503, "Could not send verification email"),
    ErrorCode.ACCOUNT_INACTIVE: (403, "Account is inactive"),
    ErrorCode.UNAUTHENTICATED: (401, "Authentication required or credentials are invalid"),
    ErrorCode.FORBIDDEN: (403, "Forbidden"),
    ErrorCode.ENROLLMENT_REQUIRED: (403, "Course enrollment is required"),
    ErrorCode.NOT_FOUND: (404, "Resource not found"),
    ErrorCode.INVALID_STATE: (409, "Invalid state for this operation"),
    ErrorCode.INVALID_QUIZ: (409, "Quiz content is invalid for publication"),
    ErrorCode.INVALID_ANSWER: (400, "Quiz answer is invalid"),
    ErrorCode.RESOURCE_IN_USE: (409, "Resource is in use"),
    ErrorCode.COURSE_NOT_FREE: (409, "Only free courses can be enrolled"),
    ErrorCode.LESSON_DELETE_BLOCKED: (409, "Lesson has learning history and cannot be deleted"),
    ErrorCode.FILE_TOO_LARGE: (413, "Uploaded file is too large"),
    ErrorCode.UNSUPPORTED_FILE_TYPE: (415, "Unsupported file type"),
    ErrorCode.AI_OUTPUT_INVALID: (502, "AI output is invalid"),
    ErrorCode.AI_PROVIDER_ERROR: (502, "AI provider error"),
    ErrorCode.AI_TIMEOUT: (504, "AI provider timed out"),
    ErrorCode.SOURCE_TEXT_EMPTY: (422, "Source text is empty"),
    ErrorCode.STORAGE_ERROR: (500, "Could not store or read the file"),
    ErrorCode.UNCATEGORIZED_EXCEPTION: (500, "Uncategorized error"),
    ErrorCode.USER_NOT_FOUND: (400, "User not found"),
    ErrorCode.EMAIL_ALREADY_EXISTS: (409, "Email already exists"),
}


def status_of(code: ErrorCode) -> int:
    return ERROR_SPEC[code][0]


def default_message(code: ErrorCode) -> str:
    return ERROR_SPEC[code][1]
