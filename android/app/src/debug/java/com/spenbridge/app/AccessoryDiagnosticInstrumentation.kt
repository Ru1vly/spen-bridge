package com.spenbridge.app

import android.app.Activity
import android.app.Instrumentation
import android.os.Build
import android.os.Bundle
import org.json.JSONObject
import java.io.File

/** Emulator-only runner. Instrumentation restarts its target process. */
class AccessoryDiagnosticInstrumentation : Instrumentation() {
    private var config: String? = null
    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        config = arguments?.getString("config")
        start()
    }
    override fun onStart() {
        val result = Bundle()
        try {
            if (Build.VERSION.SDK_INT < 30) error("Accessory self-test requires API 30")
            check(Build.HARDWARE in listOf("ranchu", "goldfish")) {
                "Accessory self-test is restricted to an emulator"
            }
            val tlsConfig = config?.let {
                val file = File(it).canonicalFile
                check(file.path.startsWith(targetContext.cacheDir.canonicalPath + File.separator))
                check(file.length() in 1..4096)
                JSONObject(file.readText())
            }
            result.putString("diagnostics", AccessoryTransportSelfTest.run(targetContext, tlsConfig).toString())
            finish(Activity.RESULT_OK, result)
        } catch (error: Throwable) {
            result.putString("diagnostic_error", generateSequence(error) { it.cause }
                .joinToString(" / ") { it.javaClass.simpleName + ":" + (it.message ?: "") })
            finish(Activity.RESULT_CANCELED, result)
        }
    }
}
