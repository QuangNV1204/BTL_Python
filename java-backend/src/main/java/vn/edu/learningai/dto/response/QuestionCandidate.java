package vn.edu.learningai.dto.response;

import java.util.List;

public record QuestionCandidate(String content, List<OptionCandidate> options, String explanation) {
}
