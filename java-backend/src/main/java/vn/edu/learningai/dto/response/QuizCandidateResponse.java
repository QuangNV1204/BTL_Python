package vn.edu.learningai.dto.response;

import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record QuizCandidateResponse(
    String generationId,
    String lessonId,
    Boolean sourceTruncated,
    QuizCandidate candidate
) {
}
