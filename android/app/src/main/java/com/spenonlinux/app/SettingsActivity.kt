package com.spenonlinux.app

import android.content.Context
import android.os.Bundle
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputEditText

class SettingsActivity : AppCompatActivity() {

    companion object {
        const val PREFS_NAME = "SPenOnLinuxPrefs"
        const val KEY_SERVER_IP = "server_ip"
        const val KEY_SERVER_PORT = "server_port"
        const val KEY_REJECT_TOUCH = "reject_touch"
        const val KEY_SHOW_PREVIEW = "show_preview"

        const val DEFAULT_IP = "192.168.1.100"
        const val DEFAULT_PORT = 40118
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        val editIp = findViewById<TextInputEditText>(R.id.editServerIp)
        val editPort = findViewById<TextInputEditText>(R.id.editServerPort)
        val switchReject = findViewById<SwitchMaterial>(R.id.switchRejectTouch)
        val switchPreview = findViewById<SwitchMaterial>(R.id.switchShowPreview)
        val btnSave = findViewById<Button>(R.id.btnSave)

        editIp.setText(prefs.getString(KEY_SERVER_IP, DEFAULT_IP))
        editPort.setText(prefs.getInt(KEY_SERVER_PORT, DEFAULT_PORT).toString())
        switchReject.isChecked = prefs.getBoolean(KEY_REJECT_TOUCH, true)
        switchPreview.isChecked = prefs.getBoolean(KEY_SHOW_PREVIEW, true)

        btnSave.setOnClickListener {
            val ip = editIp.text?.toString()?.trim() ?: DEFAULT_IP
            val port = editPort.text?.toString()?.toIntOrNull() ?: DEFAULT_PORT

            prefs.edit()
                .putString(KEY_SERVER_IP, ip)
                .putInt(KEY_SERVER_PORT, port)
                .putBoolean(KEY_REJECT_TOUCH, switchReject.isChecked)
                .putBoolean(KEY_SHOW_PREVIEW, switchPreview.isChecked)
                .apply()

            setResult(RESULT_OK)
            finish()
        }
    }
}
