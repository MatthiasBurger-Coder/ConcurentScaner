package com.example.byteman;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.Instant;

public final class RuntimeTraceHelper {
    private static final Object LOCK = new Object();

    private RuntimeTraceHelper() {
    }

    public static void onMethodEnter(String className, String methodName) {
        writeEvent("METHOD_ENTER", className, methodName, null, null);
    }

    public static void onMethodExit(String className, String methodName) {
        writeEvent("METHOD_EXIT", className, methodName, null, null);
    }

    public static void beforeFieldAccess(String className, String methodName, String fieldName, boolean isWrite) {
        writeEvent("FIELD_BEFORE", className, methodName, fieldName, isWrite);
    }

    public static void afterFieldAccess(String className, String fieldName, boolean isWrite) {
        writeEvent("FIELD_AFTER", className, "<unknown>", fieldName, isWrite);
    }

    public static void detectDeadlockNow() {
        writeEvent("DEADLOCK_CHECK", "<runtime>", "<runtime>", null, null);
    }

    private static void writeEvent(
        String event,
        String className,
        String methodName,
        String fieldName,
        Boolean isWrite
    ) {
        StringBuilder line = new StringBuilder();
        line.append("BTM_EVT");
        line.append(" ts=").append(Instant.now());
        line.append(" event=").append(event);
        line.append(" thread=").append(Thread.currentThread().getName());
        line.append(" tid=").append(Thread.currentThread().getId());
        line.append(" class=").append(className);
        line.append(" method=").append(methodName);
        if (fieldName != null) {
            line.append(" field=").append(fieldName);
        }
        if (isWrite != null) {
            line.append(" write=").append(isWrite);
        }
        appendLine(line.toString());
    }

    private static void appendLine(String message) {
        String runtimePath = System.getProperty("byteman.runtime.log", "Byteman.runtime.log");
        Path target = Paths.get(runtimePath);
        synchronized (LOCK) {
            try {
                Path parent = target.getParent();
                if (parent != null) {
                    Files.createDirectories(parent);
                }
                Files.writeString(
                    target,
                    message + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND
                );
            } catch (IOException error) {
                System.err.println("RuntimeTraceHelper log write failed: " + error.getMessage());
            }
        }
    }
}
