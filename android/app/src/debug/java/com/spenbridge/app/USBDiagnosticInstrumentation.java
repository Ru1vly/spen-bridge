package com.spenbridge.app;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.PrintStream;

/** ADB-invoked, debug-only synthetic transport diagnostic. No UI or OS input. */
public final class USBDiagnosticInstrumentation extends Instrumentation {
    private String config;
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        config = arguments == null ? null : arguments.getString("config");
        start();
    }
    @Override public void onStart() {
        Bundle result = new Bundle();
        PrintStream previous = System.out;
        try {
            if (config == null) throw new IllegalArgumentException("Missing private diagnostic config");
            File allowed = getTargetContext().getCacheDir().getCanonicalFile();
            File input = new File(config).getCanonicalFile();
            if (!input.getPath().startsWith(allowed.getPath() + File.separator))
                throw new IllegalArgumentException("Diagnostic config must be in app-private cache");
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            System.setOut(new PrintStream(bytes, true, "UTF-8"));
            USBLatencyProbe.main(new String[]{input.getPath()});
            result.putString("diagnostics", bytes.toString("UTF-8").trim());
            finish(Activity.RESULT_OK, result);
        } catch (Exception error) {
            result.putString("diagnostic_error", error.getClass().getSimpleName());
            finish(Activity.RESULT_CANCELED, result);
        } finally {
            System.setOut(previous);
        }
    }
}
