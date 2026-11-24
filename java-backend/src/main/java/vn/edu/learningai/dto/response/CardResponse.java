package vn.edu.learningai.dto.response;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import vn.edu.learningai.common.enums.FlashcardStatus;

import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CardResponse(
    String id,
    String lessonId,
    String frontText,
    String backText,
    FlashcardStatus status,
    Boolean generatedByAi,
    Instant createdAt
) {
}
