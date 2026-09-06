package com.spenonlinux.app

import android.content.Context
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.slider.Slider
import com.google.android.material.switchmaterial.SwitchMaterial
import com.google.android.material.textfield.TextInputEditText

class SettingsActivity : AppCompatActivity() {

    companion object {
        const val PREFS_NAME = "SPenOnLinuxPrefs"
        const val KEY_SERVER_IP = "server_ip"
        const val KEY_SERVER_PORT = "server_port"
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

        const val DEFAULT_IP = "192.168.1.7"
        const val DEFAULT_PORT = 40118
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

        val editIp = findViewById<TextInputEditText>(R.id.editServerIp)
        val editPort = findViewById<TextInputEditText>(R.id.editServerPort)

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
        editIp.setText(prefs.getString(KEY_SERVER_IP, DEFAULT_IP))
        editPort.setText(prefs.getInt(KEY_SERVER_PORT, DEFAULT_PORT).toString())

        val savedMode = prefs.getString(KEY_AREA_MODE, MODE_16_9) ?: MODE_16_9
        when (savedMode) {
            MODE_FULL -> rbAreaFull.isChecked = true
            MODE_16_10 -> rbArea1610.isChecked = true
            MODE_21_9 -> rbArea219.isChecked = true
            MODE_CUSTOM -> rbAreaCustom.isChecked = true
            else -> rbArea169.isChecked = true
        }

        val savedWidth = prefs.getInt(KEY_AREA_WIDTH, 100).coerceIn(20, 100)
        val savedHeight = prefs.getInt(KEY_AREA_HEIGHT, 100).coerceIn(20, 100)
        val savedOffsetX = prefs.getInt(KEY_AREA_OFFSET_X, 50).coerceIn(0, 100)
        val savedOffsetY = prefs.getInt(KEY_AREA_OFFSET_Y, 50).coerceIn(0, 100)

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

        switchShowBorder.isChecked = prefs.getBoolean(KEY_AREA_SHOW_BORDER, true)
        switchShowShade.isChecked = prefs.getBoolean(KEY_AREA_SHOW_SHADE, true)
        switchSidebarLeft.isChecked = prefs.getBoolean(KEY_SIDEBAR_ON_LEFT, true)
        switchForceLandscape.isChecked = prefs.getBoolean(KEY_FORCE_LANDSCAPE, true)
        switchShowPreview.isChecked = prefs.getBoolean(KEY_SHOW_PREVIEW, true)
        switchRejectTouch.isChecked = prefs.getBoolean(KEY_REJECT_TOUCH, true)

        btnSave.setOnClickListener {
            val ip = editIp.text?.toString()?.trim() ?: DEFAULT_IP
            val port = editPort.text?.toString()?.toIntOrNull() ?: DEFAULT_PORT

            val selectedMode = when (rgAreaMode.checkedRadioButtonId) {
                R.id.rbAreaFull -> MODE_FULL
                R.id.rbArea1610 -> MODE_16_10
                R.id.rbArea219 -> MODE_21_9
                R.id.rbAreaCustom -> MODE_CUSTOM
                else -> MODE_16_9
            }

            prefs.edit()
                .putString(KEY_SERVER_IP, ip)
                .putInt(KEY_SERVER_PORT, port)
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
