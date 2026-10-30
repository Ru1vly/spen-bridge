package com.spenbridge.app

import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.widget.doAfterTextChanged
import com.google.android.material.slider.Slider
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputEditText

class SettingsActivity : AppCompatActivity() {

    companion object {
        const val PREFS_NAME = "SPenBridgePrefs"
        const val KEY_SERVER_IP = "server_ip"
        const val KEY_SERVER_PORT = "server_port"
        const val KEY_FINGERPRINT = "desktop_fingerprint"
        const val KEY_PAIRING_CODE = "pairing_code"
        const val KEY_REJECT_TOUCH = "reject_touch"
        const val KEY_SHOW_PREVIEW = "show_preview"
        const val KEY_FORCE_LANDSCAPE = "force_landscape"

        // Tablet Active Area Settings
        const val KEY_AREA_MODE = "area_mode"
        const val KEY_AREA_WIDTH = "area_width"
        const val KEY_AREA_HEIGHT = "area_height"
        const val KEY_AREA_OFFSET_X = "area_offset_x"
        const val KEY_AREA_OFFSET_Y = "area_offset_y"
        const val KEY_AREA_SHOW_BORDER = "area_show_border"
        const val KEY_AREA_SHOW_SHADE = "area_show_shade"

        // Sidebar Position
        const val KEY_SIDEBAR_ON_LEFT = "sidebar_on_left"

        const val MODE_16_9 = "16:9"
        const val MODE_FULL = "full"
        const val MODE_16_10 = "16:10"
        const val MODE_21_9 = "21:9"
        const val MODE_CUSTOM = "custom"

        const val DEFAULT_IP = "127.0.0.1"
        const val DEFAULT_PORT = 40118
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        val editIp = findViewById<TextInputEditText>(R.id.editServerIp)
        val editPort = findViewById<TextInputEditText>(R.id.editServerPort)
        val editFingerprint = findViewById<TextInputEditText>(R.id.editFingerprint)
        val editPairingCode = findViewById<TextInputEditText>(R.id.editPairingCode)

        val rgAreaMode = findViewById<RadioGroup>(R.id.rgAreaMode)
        val rbArea169 = findViewById<RadioButton>(R.id.rbArea169)
        val rbAreaFull = findViewById<RadioButton>(R.id.rbAreaFull)
        val rbArea1610 = findViewById<RadioButton>(R.id.rbArea1610)
        val rbArea219 = findViewById<RadioButton>(R.id.rbArea219)
        val rbAreaCustom = findViewById<RadioButton>(R.id.rbAreaCustom)

        val layoutCustomArea = findViewById<LinearLayout>(R.id.layoutCustomArea)
        val tvWidthLabel = findViewById<TextView>(R.id.tvWidthLabel)
        val sliderWidth = findViewById<Slider>(R.id.sliderWidth)
        val tvHeightLabel = findViewById<TextView>(R.id.tvHeightLabel)
        val sliderHeight = findViewById<Slider>(R.id.sliderHeight)
        val tvOffsetXLabel = findViewById<TextView>(R.id.tvOffsetXLabel)
        val sliderOffsetX = findViewById<Slider>(R.id.sliderOffsetX)
        val tvOffsetYLabel = findViewById<TextView>(R.id.tvOffsetYLabel)
        val sliderOffsetY = findViewById<Slider>(R.id.sliderOffsetY)

        val btnAlignLeft = findViewById<Button>(R.id.btnAlignLeft)
        val btnAlignCenter = findViewById<Button>(R.id.btnAlignCenter)
        val btnAlignRight = findViewById<Button>(R.id.btnAlignRight)

        val switchShowBorder = findViewById<SwitchMaterial>(R.id.switchShowBorder)
        val switchShowShade = findViewById<SwitchMaterial>(R.id.switchShowShade)
        val switchSidebarLeft = findViewById<SwitchMaterial>(R.id.switchSidebarLeft)
        val switchForceLandscape = findViewById<SwitchMaterial>(R.id.switchForceLandscape)
        val switchShowPreview = findViewById<SwitchMaterial>(R.id.switchShowPreview)
        val switchRejectTouch = findViewById<SwitchMaterial>(R.id.switchRejectTouch)
        val btnSave = findViewById<Button>(R.id.btnSave)

        // Populate initial values
        editIp.setText(prefs.stringOrDefault(KEY_SERVER_IP, DEFAULT_IP))
        editPort.setText(String.format(java.util.Locale.ROOT, "%d", prefs.intOrDefault(KEY_SERVER_PORT, DEFAULT_PORT)))
        editFingerprint.setText(prefs.stringOrDefault(KEY_FINGERPRINT, ""))
        editPairingCode.setText(prefs.stringOrDefault(KEY_PAIRING_CODE, ""))
        val usbHint = findViewById<TextView>(R.id.usbModeHint)
        fun updateUsbHint() {
            val port = editPort.text?.toString()?.toIntOrNull()
            usbHint.text = if (port != null && port in 1..65535) getString(R.string.usb_mode_hint, port)
                           else getString(R.string.invalid_port)
        }
        editPort.doAfterTextChanged { updateUsbHint() }
        updateUsbHint()

        val savedMode = prefs.stringOrDefault(KEY_AREA_MODE, MODE_16_9)
        when (savedMode) {
            MODE_FULL -> rbAreaFull.isChecked = true
            MODE_16_10 -> rbArea1610.isChecked = true
            MODE_21_9 -> rbArea219.isChecked = true
            MODE_CUSTOM -> rbAreaCustom.isChecked = true
            else -> rbArea169.isChecked = true
        }

        val savedWidth = prefs.intOrDefault(KEY_AREA_WIDTH, 100).coerceIn(20, 100)
        val savedHeight = prefs.intOrDefault(KEY_AREA_HEIGHT, 100).coerceIn(20, 100)
        val savedOffsetX = prefs.intOrDefault(KEY_AREA_OFFSET_X, 50).coerceIn(0, 100)
        val savedOffsetY = prefs.intOrDefault(KEY_AREA_OFFSET_Y, 50).coerceIn(0, 100)

        sliderWidth.value = savedWidth.toFloat()
        tvWidthLabel.text = getString(R.string.area_width_label, savedWidth)

        sliderHeight.value = savedHeight.toFloat()
        tvHeightLabel.text = getString(R.string.area_height_label, savedHeight)

        sliderOffsetX.value = savedOffsetX.toFloat()
        tvOffsetXLabel.text = getString(R.string.area_offset_x_label, savedOffsetX)

        sliderOffsetY.value = savedOffsetY.toFloat()
        tvOffsetYLabel.text = getString(R.string.area_offset_y_label, savedOffsetY)

        // Show/hide or dim custom sliders based on mode
        fun updateCustomLayoutVisibility(mode: String) {
            layoutCustomArea.visibility = if (mode == MODE_FULL) View.GONE else View.VISIBLE
        }
        updateCustomLayoutVisibility(savedMode)

        rgAreaMode.setOnCheckedChangeListener { _, checkedId ->
            val mode = when (checkedId) {
                R.id.rbAreaFull -> MODE_FULL
                R.id.rbArea1610 -> MODE_16_10
                R.id.rbArea219 -> MODE_21_9
                R.id.rbAreaCustom -> MODE_CUSTOM
                else -> MODE_16_9
            }
            updateCustomLayoutVisibility(mode)
        }

        sliderWidth.addOnChangeListener { _, value, _ ->
            tvWidthLabel.text = getString(R.string.area_width_label, value.toInt())
        }
        sliderHeight.addOnChangeListener { _, value, _ ->
            tvHeightLabel.text = getString(R.string.area_height_label, value.toInt())
        }
        sliderOffsetX.addOnChangeListener { _, value, _ ->
            tvOffsetXLabel.text = getString(R.string.area_offset_x_label, value.toInt())
        }
        sliderOffsetY.addOnChangeListener { _, value, _ ->
            tvOffsetYLabel.text = getString(R.string.area_offset_y_label, value.toInt())
        }

        btnAlignCenter.setOnClickListener {
            sliderOffsetX.value = 50f
            sliderOffsetY.value = 50f
        }
        btnAlignLeft.setOnClickListener {
            sliderOffsetX.value = 0f
        }
        btnAlignRight.setOnClickListener {
            sliderOffsetX.value = 100f
        }

        switchShowBorder.isChecked = prefs.booleanOrDefault(KEY_AREA_SHOW_BORDER, true)
        switchShowShade.isChecked = prefs.booleanOrDefault(KEY_AREA_SHOW_SHADE, true)
        switchSidebarLeft.isChecked = prefs.booleanOrDefault(KEY_SIDEBAR_ON_LEFT, true)
        switchForceLandscape.isChecked = prefs.booleanOrDefault(KEY_FORCE_LANDSCAPE, true)
        switchShowPreview.isChecked = prefs.booleanOrDefault(KEY_SHOW_PREVIEW, true)
        switchRejectTouch.isChecked = prefs.booleanOrDefault(KEY_REJECT_TOUCH, true)

        btnSave.setOnClickListener {
            val ip = editIp.text?.toString()?.trim().orEmpty()
            val port = editPort.text?.toString()?.toIntOrNull()
            val fingerprint = PairingProtocol.normalizeFingerprint(editFingerprint.text?.toString().orEmpty())
            val pairingCode = editPairingCode.text?.toString().orEmpty().filterNot { it.isWhitespace() }
            editIp.error = if (ConnectionEndpoint.validHost(ip)) null else getString(R.string.invalid_host)
            editPort.error = if (port != null && port in 1..65535) null else getString(R.string.invalid_port)
            editFingerprint.error = if (PairingProtocol.validFingerprint(fingerprint)) null else getString(R.string.invalid_fingerprint)
            editPairingCode.error = if (PairingProtocol.validCode(pairingCode)) null else getString(R.string.invalid_pairing_code)
            if (editIp.error != null || editPort.error != null || editFingerprint.error != null || editPairingCode.error != null) return@setOnClickListener

            val selectedMode = when (rgAreaMode.checkedRadioButtonId) {
                R.id.rbAreaFull -> MODE_FULL
                R.id.rbArea1610 -> MODE_16_10
                R.id.rbArea219 -> MODE_21_9
                R.id.rbAreaCustom -> MODE_CUSTOM
                else -> MODE_16_9
            }

            prefs.edit()
                .putString(KEY_SERVER_IP, ip)
                .putInt(KEY_SERVER_PORT, port!!)
                .putString(KEY_FINGERPRINT, fingerprint)
                .putString(KEY_PAIRING_CODE, pairingCode)
                .putString(KEY_AREA_MODE, selectedMode)
                .putInt(KEY_AREA_WIDTH, sliderWidth.value.toInt())
                .putInt(KEY_AREA_HEIGHT, sliderHeight.value.toInt())
                .putInt(KEY_AREA_OFFSET_X, sliderOffsetX.value.toInt())
                .putInt(KEY_AREA_OFFSET_Y, sliderOffsetY.value.toInt())
                .putBoolean(KEY_AREA_SHOW_BORDER, switchShowBorder.isChecked)
                .putBoolean(KEY_AREA_SHOW_SHADE, switchShowShade.isChecked)
                .putBoolean(KEY_SIDEBAR_ON_LEFT, switchSidebarLeft.isChecked)
                .putBoolean(KEY_FORCE_LANDSCAPE, switchForceLandscape.isChecked)
                .putBoolean(KEY_SHOW_PREVIEW, switchShowPreview.isChecked)
                .putBoolean(KEY_REJECT_TOUCH, switchRejectTouch.isChecked)
                .apply()

            setResult(RESULT_OK)
            finish()
        }
    }
}
