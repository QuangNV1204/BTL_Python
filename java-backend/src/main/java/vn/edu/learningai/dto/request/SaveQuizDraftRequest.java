package vn.edu.learningai.dto.request;

import com.fasterxml.jackson.annotation.JsonCreator;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;
import vn.edu.learningai.exception.ApiException;
import vn.edu.learningai.exception.ErrorCode;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public record SaveQuizDraftRequest(String requestId, String title, List<Item> questions) {
    public record Item(Long id, WriteQuestionRequest question) {}

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static SaveQuizDraftRequest fromJson(JsonNode body) {
        fields(body, Set.of("request_id", "title", "questions"));
        var key = body.get("request_id");
        if (key == null || !key.isString() || !key.stringValue().matches(
                "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")) {
            throw invalid("request_id must be a UUID");
        }
        var title = body.get("title");
        if (title == null || !title.isString() || title.stringValue().isBlank()
                || title.stringValue().codePointCount(0, title.stringValue().length()) > 200) {
            throw invalid("title must contain 1 to 200 characters");
        }
        var values = body.get("questions");
        if (values == null || !values.isArray() || values.size() > 200) {
            throw invalid("questions must be an array of at most 200 items");
        }
        var items = new ArrayList<Item>();
        var ids = new HashSet<Long>();
        var positions = new HashSet<Integer>();
        for (var value : values) {
            fields(value, Set.of("id", "content", "explanation", "order_index", "options", "generation_id"));
            Long id = null;
            if (value.has("id") && !value.get("id").isNull()) {
                var raw = value.get("id");
                if (!raw.isString() || !raw.stringValue().matches("[1-9][0-9]{0,18}")) throw invalid("Invalid question id");
                try { id = Long.parseLong(raw.stringValue()); }
                catch (NumberFormatException e) { throw invalid("Question id exceeds signed BIGINT"); }
                if (!ids.add(id)) throw invalid("Duplicate question id");
            }
            ObjectNode question = ((ObjectNode) value).deepCopy();
            question.remove("id");
            var write = WriteQuestionRequest.fromJson(question);
            if (!positions.add(write.orderIndex())) throw invalid("Duplicate question order_index");
            items.add(new Item(id, write));
        }
        for (int i = 0; i < items.size(); i++) {
            if (items.get(i).question().orderIndex() != i) throw invalid("Question order_index must match array position");
        }
        return new SaveQuizDraftRequest(key.stringValue().toLowerCase(java.util.Locale.ROOT),
            title.stringValue(), List.copyOf(items));
    }

    private static void fields(JsonNode body, Set<String> allowed) {
        if (body == null || !body.isObject()) throw invalid("Expected an object");
        for (var name : body.propertyNames()) if (!allowed.contains(name)) throw invalid("Unknown field: " + name);
    }
    private static ApiException invalid(String message) { return new ApiException(ErrorCode.VALIDATION_ERROR, message); }
}
