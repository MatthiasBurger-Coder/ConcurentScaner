package com.verifier.app;

import java.util.concurrent.CountDownLatch;

public class Main {
    public static void main(String[] args) throws Exception {
        int concurrencyLevel = readEnvInt("STRESS_CONCURRENCY_LEVEL", 2);
        int operationsPerThread = readEnvInt("STRESS_OPS_PER_THREAD", 20);
        int pauseMillis = readEnvInt("STRESS_PAUSE_MS", 25);
        int writerThreads = Math.max(1, concurrencyLevel / 2);
        int readerThreads = Math.max(1, concurrencyLevel - writerThreads);

        SharedCounter counter = new SharedCounter(0, pauseMillis);
        CountDownLatch startGate = new CountDownLatch(1);
        Thread[] workers = new Thread[writerThreads + readerThreads];

        for (int i = 0; i < writerThreads; i++) {
            String threadName = "writer-thread-" + i;
            workers[i] = new Thread(() -> {
                await(startGate);
                for (int j = 0; j < operationsPerThread; j++) {
                    counter.incrementWithPause();
                }
            }, threadName);
        }

        for (int i = 0; i < readerThreads; i++) {
            String threadName = "reader-thread-" + i;
            workers[writerThreads + i] = new Thread(() -> {
                await(startGate);
                for (int j = 0; j < operationsPerThread; j++) {
                    counter.readWithPause();
                }
            }, threadName);
        }

        for (Thread worker : workers) {
            worker.start();
        }
        startGate.countDown();
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("MAIN_DONE");
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }

    private static int readEnvInt(String name, int defaultValue) {
        String raw = System.getenv(name);
        if (raw == null || raw.isBlank()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(raw.trim());
        } catch (NumberFormatException ignored) {
            return defaultValue;
        }
    }
}
