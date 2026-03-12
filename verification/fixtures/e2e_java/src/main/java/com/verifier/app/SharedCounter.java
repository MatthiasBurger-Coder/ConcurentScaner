package com.verifier.app;

public class SharedCounter {
    private int value;
    private final long pauseMillis;

    public SharedCounter(int initial) {
        this(initial, 25);
    }

    public SharedCounter(int initial, long pauseMillis) {
        this.value = initial;
        this.pauseMillis = Math.max(0, pauseMillis);
    }

    public int incrementWithPause() {
        int before = value;
        sleepQuietly(pauseMillis);
        value = before + 1;
        return value;
    }

    public int readWithPause() {
        int snapshot = value;
        sleepQuietly(pauseMillis);
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
