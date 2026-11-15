package vn.edu.learningai.dto.request;

import com.fasterxml.jackson.annotation.JsonCreator;
import tools.jackson.databind.JsonNode;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public record SubmitAttemptRequest(List<Answer> answers) {
    private static final Set<String> ALLOWED_FIELDS = Set.of("answers");
    private static final Set<String> ALLOWED_ANSWER_FIELDS = Set.of("question_id", "selected_option_id");

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static SubmitAttemptRequest fromJson(JsonNode body) {
        if (body == null || !body.isObject() || body.size() != 1 || !body.has("answers")) {
            throw invalid("Only answers is allowed and required");
        }
        body.propertyNames().forEach(name -> {
            if (!ALLOWED_FIELDS.contains(name)) throw invalid("Unknown field: " + name);
        });
        JsonNode values = body.get("answers");
        if (!values.isArray()) throw invalid("answers must be an array");
        List<Answer> result = new ArrayList<>();
        for (JsonNode value : values) {
            if (!value.isObject() || !value.has("question_id") || !value.has("selected_option_id")) {
                throw invalid("Each answer requires question_id and selected_option_id");
            }
            value.propertyNames().forEach(name -> {
                if (!ALLOWED_ANSWER_FIELDS.contains(name)) throw invalid("Unknown answer field: " + name);
            });
            String questionId = positiveId(value.get("question_id"), "question_id");
            JsonNode optionNode = value.get("selected_option_id");
            String optionId = optionNode == null || optionNode.isNull() ? null
                : positiveId(optionNode, "selected_option_id");
            result.add(new Answer(questionId, optionId));
        }
        return new SubmitAttemptRequest(List.copyOf(result));
    }

    public record Answer(String questionId, String selectedOptionId) {}

    private static String positiveId(JsonNode value, String field) {
        if (value == null || !value.isString() || !value.stringValue().matches("[1-9][0-9]{0,18}")) {
            throw invalid(field + " must be a positive BIGINT string");
        }
        try {
            Long.parseLong(value.stringValue());
            return value.stringValue();
        } catch (NumberFormatException exception) {
            throw invalid(field + " exceeds the signed BIGINT range");
        }
    }

    private static ApiException invalid(String message) {
        return new ApiException(ErrorCode.VALIDATION_ERROR, message);
    }
}
