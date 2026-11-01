package com.spenbridge.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Shell/DUMP-authorized commands only, present exclusively in debug builds. */
class InputTraceReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val result = try {
            when (intent.action) {
                "com.spenbridge.app.TRACE_START" -> InputTrace.start(context, intent.getIntExtra("seconds", 30))
                "com.spenbridge.app.TRACE_STOP" -> InputTrace.stop()
                "com.spenbridge.app.TRACE_STATUS" -> InputTrace.status()
                "com.spenbridge.app.SYNTHETIC_START" -> SyntheticInputDiagnostic.start(context, requireNotNull(intent.getStringExtra("config")))
                "com.spenbridge.app.SYNTHETIC_STATUS" -> SyntheticInputDiagnostic.status()
                else -> "error:action"
            }
        } catch (_: Exception) { "error:request" }
        setResultData(result)
    }
}
