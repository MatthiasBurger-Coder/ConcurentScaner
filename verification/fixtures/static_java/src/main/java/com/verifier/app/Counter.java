package com.verifier.app;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.List;

public class Counter {
    private int value;
    private final AtomicInteger hits = new AtomicInteger();

    public Counter(int start) {
        this.value = start;
    }

    public int incrementAndGet() {
        int before = value;
        value = before + 1;
        hits.incrementAndGet();
        return value;
    }

    public int read() {
        return value;
    }
}
