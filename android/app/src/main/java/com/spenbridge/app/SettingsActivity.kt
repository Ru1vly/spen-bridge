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
    private var settingsSection = -1

    companion object {
        const val PREFS_NAME = "SPenBridgePrefs"
        const val KEY_SERVER_IP = "server_ip"
        const val KEY_SERVER_PORT = "server_port"
        const val KEY_FINGERPRINT = "desktop_fingerprint"
        const val KEY_PAIRING_CODE = "pairing_code"
        const val KEY_DESKTOP_NAME = "desktop_name"
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

        const val DEFAULT_IP = ""
        const val DEFAULT_PORT = 40118
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applySystemBarAppearance()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        val shortWindow = resources.configuration.screenHeightDp < 480
        val sidePreview = shortWindow && resources.configuration.screenWidthDp >= 600
        val detailBody = findViewById<LinearLayout>(R.id.detailBody)
        detailBody.orientation = if (sidePreview) LinearLayout.HORIZONTAL else LinearLayout.VERTICAL
        findViewById<View>(R.id.previewHost).layoutParams = LinearLayout.LayoutParams(
            if (sidePreview) 0 else LinearLayout.LayoutParams.MATCH_PARENT,
            if (sidePreview) LinearLayout.LayoutParams.MATCH_PARENT else LinearLayout.LayoutParams.WRAP_CONTENT,
            if (sidePreview) 1f else 0f)
        findViewById<View>(R.id.settingsScroll).layoutParams = LinearLayout.LayoutParams(
            if (sidePreview) 0 else LinearLayout.LayoutParams.MATCH_PARENT,
            if (sidePreview) LinearLayout.LayoutParams.MATCH_PARENT else 0,
            if (sidePreview) 1.5f else 1f)
        findViewById<View>(R.id.areaPreview).layoutParams = findViewById<View>(R.id.areaPreview).layoutParams.apply {
            height = if (sidePreview) 0 else ((if (shortWindow) 80 else 160) * resources.displayMetrics.density).toInt()
            (this as LinearLayout.LayoutParams).weight = if (sidePreview) 1f else 0f
        }
        findViewById<TextView>(R.id.settingsAppTitle).setText(R.string.settings_title)
        androidx.core.view.ViewCompat.setAccessibilityHeading(findViewById(R.id.settingsAppTitle), true)
        val sections = listOf(R.id.connectionSection, R.id.areaSection, R.id.controlsSection)
        val titles = listOf(R.string.settings_connect_tab, R.string.settings_area_tab, R.string.settings_controls_tab)
        fun showSection(index: Int) {
            settingsSection = index
            sections.forEachIndexed { position, id ->
                findViewById<View>(id).visibility = if (position == index) View.VISIBLE else View.GONE
            }
            findViewById<View>(R.id.previewHost).visibility = if (index == 1) View.VISIBLE else View.GONE
            detailBody.visibility = if (index == -1) View.GONE else View.VISIBLE
            findViewById<View>(R.id.settingsIndex).visibility = if (index == -1) View.VISIBLE else View.GONE
            findViewById<View>(R.id.settingsScroll).visibility = if (index == -1) View.GONE else View.VISIBLE
            findViewById<View>(R.id.settingsActions).visibility = if (index == 1 || index == 2) View.VISIBLE else View.GONE
            findViewById<TextView>(R.id.settingsAppTitle).setText(if (index == -1) R.string.settings_title else titles[index])
            findViewById<android.widget.ScrollView>(R.id.settingsScroll).scrollTo(0, 0)
        }
        listOf(R.id.btnConnectionPage, R.id.btnAreaPage, R.id.btnInputPage).forEachIndexed { index, id ->
            findViewById<Button>(id).setOnClickListener { showSection(index) }
        }
        settingsSection = savedInstanceState?.getInt("settings_section", -1)?.coerceIn(-1, 2) ?: -1
        showSection(settingsSection)
        findViewById<Button>(R.id.btnBack).setOnClickListener { onBackPressedDispatcher.onBackPressed() }
        // Center a readable settings column on tablets, while filling compact screens.
        val content = findViewById<LinearLayout>(R.id.settingsContent)
        val maxWidth = (840 * resources.displayMetrics.density).toInt()
        (content.parent as View).addOnLayoutChangeListener { parent, _, _, _, _, _, _, _, _ ->
            val desiredWidth = minOf(parent.width, maxWidth)
            if (desiredWidth > 0 && content.layoutParams.width != desiredWidth) {
                content.layoutParams = content.layoutParams.apply { width = desiredWidth }
            }
        }
        val scroll = findViewById<View>(R.id.settingsScroll)
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        androidx.core.view.WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = resources.getBoolean(R.bool.light_system_bars)
            isAppearanceLightNavigationBars = resources.getBoolean(R.bool.light_system_bars)
        }
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { view, insets ->
            val safe = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars()
                or androidx.core.view.WindowInsetsCompat.Type.displayCutout()
                or androidx.core.view.WindowInsetsCompat.Type.ime())
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom)
            val typing = insets.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime())
            findViewById<View>(R.id.settingsActions).visibility = if (!typing && settingsSection in 1..2) View.VISIBLE else View.GONE
            findViewById<View>(R.id.settingsAppBar).visibility = if (typing && shortWindow) View.GONE else View.VISIBLE
            insets
        }

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

        val switchSidebarLeft = findViewById<SwitchMaterial>(R.id.switchSidebarLeft)
        val switchForceLandscape = findViewById<SwitchMaterial>(R.id.switchForceLandscape)
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

        val savedMode = prefs.stringOrDefault(KEY_AREA_MODE, MODE_FULL)
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

        val preview = findViewById<AreaPreviewView>(R.id.areaPreview)
        preview.surfaceWidth = intent.getIntExtra("surface_width", 0)
        preview.surfaceHeight = intent.getIntExtra("surface_height", 0)
        fun selectedMode() = when (rgAreaMode.checkedRadioButtonId) {
            R.id.rbAreaFull -> MODE_FULL
            R.id.rbArea1610 -> MODE_16_10
            R.id.rbArea219 -> MODE_21_9
            R.id.rbAreaCustom -> MODE_CUSTOM
            else -> MODE_16_9
        }
        var updatingPreview = false
        fun updatePreview() {
            if (updatingPreview) return
            updatingPreview = true
            val mode = selectedMode()
            val locked = mode != MODE_CUSTOM && mode != MODE_FULL
            if (locked) sliderHeight.value = sliderWidth.value
            sliderHeight.isEnabled = !locked
            layoutCustomArea.visibility = if (mode == MODE_FULL) View.GONE else View.VISIBLE
            tvWidthLabel.text = getString(R.string.area_width_label, sliderWidth.value.toInt())
            tvHeightLabel.text = getString(R.string.area_height_label, sliderHeight.value.toInt())
            tvOffsetXLabel.text = getString(R.string.area_offset_x_label, sliderOffsetX.value.toInt())
            tvOffsetYLabel.text = getString(R.string.area_offset_y_label, sliderOffsetY.value.toInt())
            preview.mode = mode
            preview.areaWidth = sliderWidth.value.toInt()
            preview.areaHeight = sliderHeight.value.toInt()
            preview.offsetX = sliderOffsetX.value.toInt()
            preview.offsetY = sliderOffsetY.value.toInt()
            preview.landscape = switchForceLandscape.isChecked
            preview.refresh()
            findViewById<TextView>(R.id.areaPreviewHint).setText(
                if (mode == MODE_FULL) R.string.area_full_hint else R.string.area_preview_hint)
            val modeName = when (mode) {
                MODE_FULL -> getString(R.string.area_mode_full)
                MODE_CUSTOM -> getString(R.string.area_mode_custom)
                else -> mode
            }
            findViewById<TextView>(R.id.areaPreviewSummary).text = if (mode == MODE_FULL) modeName else
                getString(R.string.area_preview_summary, modeName, preview.areaWidth, preview.areaHeight)
            updatingPreview = false
        }
        rgAreaMode.setOnCheckedChangeListener { _, _ -> updatePreview() }
        listOf(sliderWidth, sliderHeight, sliderOffsetX, sliderOffsetY).forEach {
            it.addOnChangeListener { _, _, _ -> updatePreview() }
        }
        preview.onEdit = { w, h, x, y ->
            updatingPreview = true
            sliderWidth.value = w.toFloat()
            sliderHeight.value = h.toFloat()
            sliderOffsetX.value = x.toFloat()
            sliderOffsetY.value = y.toFloat()
            updatingPreview = false
            updatePreview()
        }
        findViewById<Button>(R.id.btnResetArea).setOnClickListener {
            rbAreaFull.isChecked = true
            sliderWidth.value = 100f; sliderHeight.value = 100f
            sliderOffsetX.value = 50f; sliderOffsetY.value = 50f
            updatePreview()
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

        switchSidebarLeft.isChecked = prefs.booleanOrDefault(KEY_SIDEBAR_ON_LEFT, true)
        switchForceLandscape.isChecked = prefs.booleanOrDefault(KEY_FORCE_LANDSCAPE, true)
        switchRejectTouch.isChecked = prefs.booleanOrDefault(KEY_REJECT_TOUCH, true)

        switchForceLandscape.setOnCheckedChangeListener { _, _ -> updatePreview() }
        updatePreview()
        val feedback = findViewById<TextView>(R.id.settingsFeedback)
        val connectionFeedback = findViewById<TextView>(R.id.connectionFeedback)
        val advanced = findViewById<View>(R.id.advancedConnection)
        advanced.visibility = if (savedInstanceState?.getBoolean("advanced_visible") == true) View.VISIBLE else View.GONE
        findViewById<Button>(R.id.btnAdvancedConnection).setOnClickListener {
            advanced.visibility = if (advanced.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }
        fun connectionSummary() {
            val pairingSummary = getString(
                if (PairingProtocol.validFingerprint(prefs.stringOrDefault(KEY_FINGERPRINT, "")) &&
                    PairingProtocol.validCode(prefs.stringOrDefault(KEY_PAIRING_CODE, "")))
                    R.string.connection_paired else R.string.connection_not_paired)
            val status = intent.getStringExtra("connection_status").orEmpty()
            findViewById<TextView>(R.id.connectionSummary).text =
                if (status.isEmpty()) pairingSummary else "$status\n\n$pairingSummary"
        }
        connectionSummary()
        fun connectionDraft() = listOf(editIp.text.toString(), editPort.text.toString(),
            editFingerprint.text.toString(), editPairingCode.text.toString())
        fun localDraft() = listOf(selectedMode(), sliderWidth.value.toInt().toString(),
            sliderHeight.value.toInt().toString(), sliderOffsetX.value.toInt().toString(),
            sliderOffsetY.value.toInt().toString(), switchSidebarLeft.isChecked.toString(),
            switchForceLandscape.isChecked.toString(), switchRejectTouch.isChecked.toString())
        var connectionBaseline = connectionDraft()
        var localBaseline = localDraft()
        listOf(editIp, editPort, editFingerprint, editPairingCode).forEach { field ->
            field.doAfterTextChanged { connectionFeedback.text = "" }
        }
        listOf(sliderWidth, sliderHeight, sliderOffsetX, sliderOffsetY).forEach { slider ->
            slider.addOnChangeListener { _, _, _ -> feedback.text = "" }
        }
        listOf(switchSidebarLeft, switchRejectTouch).forEach { toggle ->
            toggle.setOnCheckedChangeListener { _, _ -> feedback.text = "" }
        }
        switchForceLandscape.setOnCheckedChangeListener { _, _ -> feedback.text = ""; updatePreview() }

        val pairingLauncher = registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                editIp.setText(prefs.stringOrDefault(KEY_SERVER_IP, DEFAULT_IP))
                editPort.setText(prefs.intOrDefault(KEY_SERVER_PORT, DEFAULT_PORT).toString())
                editFingerprint.setText(prefs.stringOrDefault(KEY_FINGERPRINT, ""))
                editPairingCode.setText(prefs.stringOrDefault(KEY_PAIRING_CODE, ""))
                connectionBaseline = connectionDraft()
                connectionFeedback.setText(R.string.connection_applied)
                intent.removeExtra("connection_status")
                connectionSummary()
                setResult(RESULT_OK)
            }
        }
        findViewById<Button>(R.id.btnFindDesktop).setOnClickListener {
            pairingLauncher.launch(android.content.Intent(this, PairingActivity::class.java))
        }
        findViewById<Button>(R.id.btnApplyConnection).setOnClickListener {
            val ip = editIp.text?.toString()?.trim().orEmpty()
            val port = editPort.text?.toString()?.toIntOrNull()
            val fingerprint = PairingProtocol.normalizeFingerprint(editFingerprint.text?.toString().orEmpty())
            val pairingCode = editPairingCode.text?.toString().orEmpty().filterNot { it.isWhitespace() }
            editIp.error = if (ip.isEmpty() || (ConnectionEndpoint.validHost(ip) &&
                !ConnectionEndpoint(ip, 1, "", "").isLoopback())) null else getString(R.string.invalid_host)
            editPort.error = if (port != null && port in 1..65535) null else getString(R.string.invalid_port)
            editFingerprint.error = if (PairingProtocol.validFingerprint(fingerprint)) null else getString(R.string.invalid_fingerprint)
            editPairingCode.error = if (PairingProtocol.validCode(pairingCode)) null else getString(R.string.invalid_pairing_code)
            val invalid = listOf(editIp, editPort, editFingerprint, editPairingCode).firstOrNull { it.error != null }
            if (invalid != null) {
                advanced.visibility = View.VISIBLE
                invalid.requestFocus()
                scroll.post { invalid.requestRectangleOnScreen(android.graphics.Rect(0, 0, invalid.width, invalid.height), false) }
                return@setOnClickListener
            }
            prefs.edit().putString(KEY_SERVER_IP, ip).putInt(KEY_SERVER_PORT, port!!)
                .putString(KEY_FINGERPRINT, fingerprint).putString(KEY_PAIRING_CODE, pairingCode).apply()
            connectionBaseline = connectionDraft()
            connectionFeedback.setText(R.string.connection_applied)
            intent.removeExtra("connection_status")
            connectionSummary()
            setResult(RESULT_OK)
        }
        btnSave.setOnClickListener {
            prefs.edit()
                .putString(KEY_AREA_MODE, selectedMode())
                .putInt(KEY_AREA_WIDTH, sliderWidth.value.toInt())
                .putInt(KEY_AREA_HEIGHT, sliderHeight.value.toInt())
                .putInt(KEY_AREA_OFFSET_X, sliderOffsetX.value.toInt())
                .putInt(KEY_AREA_OFFSET_Y, sliderOffsetY.value.toInt())
                .putBoolean(KEY_SIDEBAR_ON_LEFT, switchSidebarLeft.isChecked)
                .putBoolean(KEY_FORCE_LANDSCAPE, switchForceLandscape.isChecked)
                .putBoolean(KEY_REJECT_TOUCH, switchRejectTouch.isChecked).apply()
            localBaseline = localDraft()
            feedback.setText(R.string.local_applied)
            setResult(RESULT_OK)
        }
        onBackPressedDispatcher.addCallback(this, object : androidx.activity.OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (settingsSection != -1) { showSection(-1); return }
                if (localDraft() == localBaseline && connectionDraft() == connectionBaseline) { finish(); return }
                com.google.android.material.dialog.MaterialAlertDialogBuilder(this@SettingsActivity)
                    .setTitle(R.string.discard_title).setMessage(R.string.discard_message)
                    .setNegativeButton(R.string.keep_editing, null)
                    .setPositiveButton(R.string.discard) { _, _ -> finish() }.show()
            }
        })
        findViewById<Button>(R.id.btnCancelSettings).setOnClickListener {
            showSection(-1)
            onBackPressedDispatcher.onBackPressed()
        }
        findViewById<Button>(R.id.btnSupport).setOnClickListener {
            startActivity(android.content.Intent(this, SupportActivity::class.java))
        }
    }

    override fun onPostCreate(savedInstanceState: Bundle?) {
        super.onPostCreate(savedInstanceState)
        val width = findViewById<Slider>(R.id.sliderWidth)
        // Rebind the preview after framework view-state restoration.
        width.value = width.value
        val preview = findViewById<AreaPreviewView>(R.id.areaPreview)
        preview.areaWidth = width.value.toInt()
        preview.areaHeight = findViewById<Slider>(R.id.sliderHeight).value.toInt()
        preview.offsetX = findViewById<Slider>(R.id.sliderOffsetX).value.toInt()
        preview.offsetY = findViewById<Slider>(R.id.sliderOffsetY).value.toInt()
        preview.refresh()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putInt("settings_section", settingsSection)
        outState.putBoolean("advanced_visible", findViewById<View>(R.id.advancedConnection).visibility == View.VISIBLE)
        super.onSaveInstanceState(outState)
    }

}
