package vn.edu.learningai.dto.request;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import vn.edu.learningai.common.enums.Difficulty;
import vn.edu.learningai.common.enums.SourceType;

public record GenerationRequest(
    @NotNull Long lessonId,
    @NotNull SourceType sourceType,
    Long documentId,
    @NotNull @Min(1) @Max(10) Integer count,
    Difficulty difficulty
) {
}
