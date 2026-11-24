package vn.edu.learningai.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CardWriteRequest(
    @NotBlank @Size(max = 4000) String frontText,
    @NotBlank @Size(max = 4000) String backText,
    Long generationId
) {
}
