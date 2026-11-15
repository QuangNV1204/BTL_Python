package vn.edu.learningai.dto.request;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import tools.jackson.databind.json.JsonMapper;
import vn.edu.learningai.exception.ApiException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SubmitAttemptRequestTest {
    private final JsonMapper json = JsonMapper.builder().build();

    @ParameterizedTest
    @ValueSource(strings = {
        "{\"answers\":[]}",
        "{\"answers\":[{\"question_id\":\"1\",\"selected_option_id\":null}]}",
        "{\"answers\":[{\"question_id\":\"1\",\"selected_option_id\":\"2\"}]}"
    })
    void acceptsStrictAnswerPayload(String body) {
        assertThat(json.readValue(body, SubmitAttemptRequest.class).answers()).isNotNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "{}", "[]", "{\"answers\":null}", "{\"answers\":{}}",
        "{\"answers\":[],\"score\":100}",
        "{\"answers\":[{}]}",
        "{\"answers\":[{\"question_id\":\"1\"}]}",
        "{\"answers\":[{\"question_id\":1,\"selected_option_id\":null}]}",
        "{\"answers\":[{\"question_id\":\"0\"}]}",
        "{\"answers\":[{\"question_id\":\"1\",\"selected_option_id\":2}]}",
        "{\"answers\":[{\"question_id\":\"1\",\"is_correct\":true}]}"
    })
    void rejectsMalformedAndServerOwnedFields(String body) {
        assertThatThrownBy(() -> json.readValue(body, SubmitAttemptRequest.class))
            .hasRootCauseInstanceOf(ApiException.class);
    }
}
