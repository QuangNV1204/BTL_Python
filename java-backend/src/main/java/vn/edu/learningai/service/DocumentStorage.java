package vn.edu.learningai.service;

import org.springframework.core.io.Resource;
import org.springframework.web.multipart.MultipartFile;

public interface DocumentStorage {
    String newKey(MultipartFile file);

    void store(String storageKey, MultipartFile file);

    default String store(MultipartFile file) {
        String key = newKey(file);
        store(key, file);
        return key;
    }

    Resource load(String storageKey);

    void delete(String storageKey);
}
