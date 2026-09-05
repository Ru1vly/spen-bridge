package com.spenonlinux.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

class MainActivity : AppCompatActivity(), PenEventSender.StatusListener {

    private lateinit var penSurfaceView: PenSurfaceView
    private lateinit var statusIndicator: View
    private lateinit var statusText: TextView
    private lateinit var btnSettings: Button
    private lateinit var topBar: View

    private var sender: PenEventSender? = null

    private val settingsLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                applySettings()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Immersive sticky full screen
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE

        setContentView(R.layout.activity_main)

        penSurfaceView = findViewById(R.id.penSurfaceView)
        statusIndicator = findViewById(R.id.statusIndicator)
        statusText = findViewById(R.id.statusText)
        btnSettings = findViewById(R.id.btnSettings)
        topBar = findViewById(R.id.topBar)

        btnSettings.setOnClickListener {
            val intent = Intent(this, SettingsActivity::class.java)
            settingsLauncher.launch(intent)
        }

        initSender()
    }

    private fun initSender() {
        val prefs = getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val host = prefs.getString(SettingsActivity.KEY_SERVER_IP, SettingsActivity.DEFAULT_IP)
            ?: SettingsActivity.DEFAULT_IP
        val port = prefs.getInt(SettingsActivity.KEY_SERVER_PORT, SettingsActivity.DEFAULT_PORT)

        penSurfaceView.rejectFingerTouches =
            prefs.getBoolean(SettingsActivity.KEY_REJECT_TOUCH, true)
        penSurfaceView.showLocalPreview =
            prefs.getBoolean(SettingsActivity.KEY_SHOW_PREVIEW, true)

        sender = PenEventSender(host, port, this).also {
            penSurfaceView.sender = it
            it.start()
        }
    }

    private fun applySettings() {
        val prefs = getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val host = prefs.getString(SettingsActivity.KEY_SERVER_IP, SettingsActivity.DEFAULT_IP)
            ?: SettingsActivity.DEFAULT_IP
        val port = prefs.getInt(SettingsActivity.KEY_SERVER_PORT, SettingsActivity.DEFAULT_PORT)

        penSurfaceView.rejectFingerTouches =
            prefs.getBoolean(SettingsActivity.KEY_REJECT_TOUCH, true)
        penSurfaceView.showLocalPreview =
            prefs.getBoolean(SettingsActivity.KEY_SHOW_PREVIEW, true)

        sender?.updateEndpoint(host, port)
    }

    override fun onStatusChanged(status: PenEventSender.Status, message: String) {
        runOnUiThread {
            statusText.text = message
            val colorRes = when (status) {
                PenEventSender.Status.CONNECTED -> R.color.status_connected
                PenEventSender.Status.CONNECTING -> R.color.status_connecting
                PenEventSender.Status.DISCONNECTED,
                PenEventSender.Status.ERROR -> R.color.status_disconnected
            }
            statusIndicator.setBackgroundColor(ContextCompat.getColor(this, colorRes))
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        sender?.stop()
    }
}
