package vn.edu.learningai.ai;

public interface AIClient {

    String generate(String prompt);

    String provider();

    String model();
}
