package com.verifier.app;

public record UserRecord(String id, int priority) {
    public UserRecord {
        if (priority < 0) {
            throw new IllegalArgumentException("priority");
        }
    }
}
