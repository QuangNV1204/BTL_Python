package vn.edu.learningai.ai;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.ai")
public record AiProperties(
    String provider,
    String baseUrl,
    String model,
    String apiKey,
    Integer timeoutSeconds,
    Integer maxOutputTokens,
    Integer maxSourceChars
) {
}
