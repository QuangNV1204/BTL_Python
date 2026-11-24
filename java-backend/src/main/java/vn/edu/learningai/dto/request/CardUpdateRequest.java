package vn.edu.learningai.dto.request;

import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CardUpdateRequest(
    @Size(max = 4000) @Pattern(regexp = "(?s).*\\S.*", message = "must not be blank") String frontText,
    @Size(max = 4000) @Pattern(regexp = "(?s).*\\S.*", message = "must not be blank") String backText
) {
}
