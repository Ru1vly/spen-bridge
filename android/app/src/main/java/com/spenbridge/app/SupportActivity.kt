package com.spenbridge.app

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/** A quiet, user-opened support page. Export only explicitly allowed fields. */
class SupportActivity : AppCompatActivity() {
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applySystemBarAppearance()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_support)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.supportPageTitle), true)
        val column = findViewById<android.widget.LinearLayout>(R.id.supportContent)
        val maxWidth = (720 * resources.displayMetrics.density).toInt()
        (column.parent as android.view.View).addOnLayoutChangeListener { parent, _, _, _, _, _, _, _, _ ->
            val desiredWidth = minOf(parent.width, maxWidth)
            if (desiredWidth > 0 && column.layoutParams.width != desiredWidth)
                column.layoutParams = column.layoutParams.apply { width = desiredWidth }
        }
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = resources.getBoolean(R.bool.light_system_bars)
            isAppearanceLightNavigationBars = resources.getBoolean(R.bool.light_system_bars)
        }
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { view, insets ->
            val safe = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom)
            insets
        }
        findViewById<Button>(R.id.btnSupportBack).setOnClickListener { finish() }
        val prefs = getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val mode = prefs.stringOrDefault(SettingsActivity.KEY_AREA_MODE, SettingsActivity.MODE_FULL)
        val version = packageManager.getPackageInfo(packageName, 0).versionName ?: "1.0.0"
        val report = getString(R.string.diagnostic_report, version, android.os.Build.VERSION.RELEASE, mode)
        findViewById<TextView>(R.id.diagnosticPreview).text = report
        findViewById<Button>(R.id.btnCopyReport).setOnClickListener {
            (getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                .setPrimaryClip(ClipData.newPlainText(getString(R.string.support_title), report))
            findViewById<TextView>(R.id.supportFeedback).setText(R.string.report_copied)
        }
    }
}
