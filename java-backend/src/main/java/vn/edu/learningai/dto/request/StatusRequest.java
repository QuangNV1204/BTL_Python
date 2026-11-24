package vn.edu.learningai.dto.request;

import jakarta.validation.constraints.NotNull;
import vn.edu.learningai.common.enums.FlashcardStatus;

public record StatusRequest(@NotNull FlashcardStatus status) {
}
