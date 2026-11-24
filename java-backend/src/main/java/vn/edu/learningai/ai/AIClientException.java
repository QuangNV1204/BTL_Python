package vn.edu.learningai.ai;

import lombok.Getter;

@Getter
public class AIClientException extends RuntimeException {

    public enum Reason {
        TIMEOUT,
        PROVIDER_ERROR,
        INVALID_OUTPUT
    }

    private final Reason reason;

    public AIClientException(Reason reason, String message) {
        super(message);
        this.reason = reason;
    }

    public AIClientException(Reason reason, String message, Throwable cause) {
        super(message, cause);
        this.reason = reason;
    }
}
