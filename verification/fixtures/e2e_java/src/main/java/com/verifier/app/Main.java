package com.verifier.app;

import java.util.concurrent.CountDownLatch;

public class Main {
    public static void main(String[] args) throws Exception {
        SharedCounter counter = new SharedCounter(0);
        CountDownLatch startGate = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            await(startGate);
            for (int i = 0; i < 20; i++) {
                counter.incrementWithPause();
            }
        }, "writer-thread");

        Thread reader = new Thread(() -> {
            await(startGate);
            for (int i = 0; i < 20; i++) {
                counter.readWithPause();
            }
        }, "reader-thread");

        writer.start();
        reader.start();
        startGate.countDown();
        writer.join();
        reader.join();
        System.out.println("MAIN_DONE");
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }
}
