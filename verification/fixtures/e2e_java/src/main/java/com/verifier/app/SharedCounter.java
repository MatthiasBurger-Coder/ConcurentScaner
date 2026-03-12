package com.verifier.app;

public class SharedCounter {
    private int value;

    public SharedCounter(int initial) {
        this.value = initial;
    }

    public int incrementWithPause() {
        int before = value;
        sleepQuietly(25);
        value = before + 1;
        return value;
    }

    public int readWithPause() {
        int snapshot = value;
        sleepQuietly(25);
        return snapshot;
    }

    private static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}
