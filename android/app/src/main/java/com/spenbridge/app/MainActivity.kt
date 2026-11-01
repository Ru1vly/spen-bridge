package com.spenbridge.app

import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.content.res.ColorStateList
import android.os.Bundle
import android.view.MotionEvent
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

class MainActivity : AppCompatActivity(), PenEventSender.StatusListener {

    private lateinit var penSurfaceView: PenSurfaceView
    private lateinit var topBar: LinearLayout
    private lateinit var statusContainer: LinearLayout
    private lateinit var statusIndicator: View
    private lateinit var statusText: TextView
    private lateinit var barSpacer: View
    private lateinit var btnRotate: Button
    private lateinit var btnSettings: Button
    private lateinit var btnCollapse: Button
    private lateinit var btnExpand: Button

    private var penPresent = false
    private val restoreChrome = Runnable { penPresent = false; updateChrome() }

    private fun updateChrome() {
        topBar.visibility = if (!penPresent && !isBarCollapsed) View.VISIBLE else View.INVISIBLE
        btnExpand.visibility = if (!penPresent && isBarCollapsed) View.VISIBLE else View.INVISIBLE
        // Tablet mode has no visible text, even while idle.
        statusContainer.visibility = View.GONE
    }

    private fun observePen(event: MotionEvent) {
        if ((0 until event.pointerCount).none {
            event.getToolType(it) == MotionEvent.TOOL_TYPE_STYLUS ||
                event.getToolType(it) == MotionEvent.TOOL_TYPE_ERASER }) return
        penSurfaceView.removeCallbacks(restoreChrome)
        penPresent = true
        updateChrome()
        if (event.actionMasked in listOf(MotionEvent.ACTION_HOVER_EXIT, MotionEvent.ACTION_CANCEL)) penSurfaceView.postDelayed(restoreChrome, 700)
    }

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        observePen(event)
        return super.dispatchTouchEvent(event)
    }

    override fun dispatchGenericMotionEvent(event: MotionEvent): Boolean {
        observePen(event)
        return super.dispatchGenericMotionEvent(event)
    }

    private var sender: PenEventSender? = null
    private var sidebarOnLeft: Boolean = true
    private var isBarCollapsed: Boolean = false

    private val settingsLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                applySettings()
            }
        }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) applySystemBarAppearance()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (android.os.Build.VERSION.SDK_INT >= 28) {
            window.attributes = window.attributes.apply {
                layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
            }
        }

        // Immersive sticky full screen
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowInsetsControllerCompat(window, window.decorView)
        controller.isAppearanceLightStatusBars = resources.getBoolean(R.bool.light_system_bars)
        controller.isAppearanceLightNavigationBars = resources.getBoolean(R.bool.light_system_bars)
        controller.hide(WindowInsetsCompat.Type.systemBars())
        controller.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE

        setContentView(R.layout.activity_main)
        // Keep overlay controls out of cutouts and gesture regions even in immersive mode.
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.mainRoot)) { view, insets ->
            val safe = insets.getInsetsIgnoringVisibility(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom)
            insets
        }

        penSurfaceView = findViewById(R.id.penSurfaceView)
        topBar = findViewById(R.id.topBar)
        statusContainer = findViewById(R.id.statusContainer)
        statusIndicator = findViewById(R.id.statusIndicator)
        statusText = findViewById(R.id.statusText)
        barSpacer = findViewById(R.id.barSpacer)
        btnRotate = findViewById(R.id.btnRotate)
        btnSettings = findViewById(R.id.btnSettings)
        btnCollapse = findViewById(R.id.btnCollapse)
        btnExpand = findViewById(R.id.btnExpand)

        val openSettings = {
            settingsLauncher.launch(Intent(this, SettingsActivity::class.java)
                .putExtra("surface_width", penSurfaceView.width)
                .putExtra("surface_height", penSurfaceView.height)
                .putExtra("connection_status", statusText.contentDescription?.toString().orEmpty()))
        }
        btnSettings.setOnClickListener { openSettings() }
        statusContainer.setOnClickListener { openSettings() }

        btnRotate.setOnClickListener {
            handleRotate()
        }

        btnRotate.setOnLongClickListener {
            toggleOrientationMode()
            true
        }

        btnCollapse.setOnClickListener {
            collapseBar()
        }

        btnExpand.setOnClickListener {
            expandBar()
        }

        applySettings()
        initSender()
    }

    private fun handleRotate() {
        val currentOrientation = resources.configuration.orientation
        if (currentOrientation == Configuration.ORIENTATION_LANDSCAPE) {
            // In landscape mode, flip 180 degrees (standard <-> reverse landscape)
            requestedOrientation = if (requestedOrientation == ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE) {
                ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            } else {
                ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE
            }
        } else {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        }
    }

    private fun toggleOrientationMode() {
        val currentOrientation = resources.configuration.orientation
        requestedOrientation = if (currentOrientation == Configuration.ORIENTATION_LANDSCAPE) {
            ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        } else {
            ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        }
    }

    private fun collapseBar() {
        isBarCollapsed = true
        updateChrome()
    }

    private fun expandBar() {
        isBarCollapsed = false
        updateChrome()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        updateBarOrientation(newConfig.orientation)
    }

    private fun dpToPx(dp: Int): Int {
        return (dp * resources.displayMetrics.density).toInt()
    }

    private fun updateBarOrientation(orientation: Int) {
        val isLandscape = (orientation == Configuration.ORIENTATION_LANDSCAPE) || resources.configuration.fontScale > 1.3f

        if (isLandscape) {
            // Move toolbar to the side in landscape mode so it does not block drawing area
            val barParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = if (sidebarOnLeft) (Gravity.START or Gravity.CENTER_VERTICAL) else (Gravity.END or Gravity.CENTER_VERTICAL)
                val m = dpToPx(8)
                setMargins(m, m, m, m)
            }
            topBar.layoutParams = barParams
            topBar.orientation = LinearLayout.VERTICAL
            statusContainer.orientation = LinearLayout.HORIZONTAL
            barSpacer.visibility = View.GONE

            btnRotate.text = ""
            btnSettings.text = ""
            btnCollapse.text = ""

            val expandParams = FrameLayout.LayoutParams(
                dpToPx(48),
                dpToPx(48)
            ).apply {
                gravity = if (sidebarOnLeft) (Gravity.START or Gravity.CENTER_VERTICAL) else (Gravity.END or Gravity.CENTER_VERTICAL)
                val m = dpToPx(10)
                setMargins(m, m, m, m)
            }
            btnExpand.layoutParams = expandParams
            btnExpand.text = ""

        } else {
            // Reachable bottom toolbar in portrait
            val barParams = FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply {
                gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
                val m = dpToPx(8)
                setMargins(m, m, m, m)
            }
            topBar.layoutParams = barParams
            topBar.orientation = LinearLayout.HORIZONTAL
            statusContainer.orientation = LinearLayout.HORIZONTAL
            barSpacer.visibility = View.GONE

            btnRotate.text = ""
            btnSettings.text = ""
            btnCollapse.text = ""

            val expandParams = FrameLayout.LayoutParams(
                dpToPx(48),
                dpToPx(48)
            ).apply {
                gravity = Gravity.BOTTOM or Gravity.START
                val m = dpToPx(10)
                setMargins(m, m, m, m)
            }
            btnExpand.layoutParams = expandParams
            btnExpand.text = ""
        }

        statusContainer.layoutParams = FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
            val margin = dpToPx(12)
            setMargins(margin, margin, margin, margin)
        }
        statusText.maxWidth = dpToPx(minOf(320, resources.configuration.screenWidthDp - 80).coerceAtLeast(100))
        btnSettings.contentDescription = getString(R.string.settings_title)
        btnRotate.contentDescription = getString(R.string.rotate_description)
        btnCollapse.contentDescription = getString(R.string.hide_controls_description)
        btnExpand.contentDescription = getString(R.string.show_controls_description)
        updateChrome()
    }

    private fun initSender() {
        val prefs = getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val host = prefs.stringOrDefault(SettingsActivity.KEY_SERVER_IP, SettingsActivity.DEFAULT_IP)
        val port = prefs.intOrDefault(SettingsActivity.KEY_SERVER_PORT, SettingsActivity.DEFAULT_PORT)

        sender = PenEventSender(applicationContext, host, port, this,
            prefs.stringOrDefault(SettingsActivity.KEY_FINGERPRINT, ""),
            prefs.stringOrDefault(SettingsActivity.KEY_PAIRING_CODE, "")).also {
            penSurfaceView.sender = it
        }
    }

    private fun applySettings() {
        penSurfaceView.cancelInput()
        val prefs = getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val host = prefs.stringOrDefault(SettingsActivity.KEY_SERVER_IP, SettingsActivity.DEFAULT_IP)
        val port = prefs.intOrDefault(SettingsActivity.KEY_SERVER_PORT, SettingsActivity.DEFAULT_PORT)

        // Custom Tablet Area Settings
        val modeStr = prefs.stringOrDefault(SettingsActivity.KEY_AREA_MODE, SettingsActivity.MODE_FULL)
        penSurfaceView.areaMode = when (modeStr) {
            SettingsActivity.MODE_FULL -> PenSurfaceView.AreaMode.FULL
            SettingsActivity.MODE_16_10 -> PenSurfaceView.AreaMode.ASPECT_16_10
            SettingsActivity.MODE_21_9 -> PenSurfaceView.AreaMode.ASPECT_21_9
            SettingsActivity.MODE_CUSTOM -> PenSurfaceView.AreaMode.CUSTOM
            else -> PenSurfaceView.AreaMode.ASPECT_16_9
        }

        penSurfaceView.customWidthPercent = prefs.intOrDefault(SettingsActivity.KEY_AREA_WIDTH, 100)
        penSurfaceView.customHeightPercent = prefs.intOrDefault(SettingsActivity.KEY_AREA_HEIGHT, 100)
        penSurfaceView.customOffsetXPercent = prefs.intOrDefault(SettingsActivity.KEY_AREA_OFFSET_X, 50)
        penSurfaceView.customOffsetYPercent = prefs.intOrDefault(SettingsActivity.KEY_AREA_OFFSET_Y, 50)

        penSurfaceView.rejectFingerTouches = prefs.booleanOrDefault(SettingsActivity.KEY_REJECT_TOUCH, true)

        sidebarOnLeft = prefs.booleanOrDefault(SettingsActivity.KEY_SIDEBAR_ON_LEFT, true)

        val forceLandscape = prefs.booleanOrDefault(SettingsActivity.KEY_FORCE_LANDSCAPE, true)
        if (forceLandscape) {
            if (requestedOrientation != ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE &&
                requestedOrientation != ActivityInfo.SCREEN_ORIENTATION_REVERSE_LANDSCAPE) {
                requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            }
        } else {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_USER
        }

        updateBarOrientation(resources.configuration.orientation)
        sender?.updateEndpoint(host, port,
            prefs.stringOrDefault(SettingsActivity.KEY_FINGERPRINT, ""),
            prefs.stringOrDefault(SettingsActivity.KEY_PAIRING_CODE, ""))
    }

    override fun onStatusChanged(status: PenEventSender.Status, message: String) {
        runOnUiThread {
            if (isDestroyed || isFinishing || !lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) return@runOnUiThread
            if (sender?.currentStatus != status) return@runOnUiThread
            penSurfaceView.cancelInput()
            if (status == PenEventSender.Status.CONNECTED) sender?.resumeCapture(sender!!.currentGeneration)
            statusText.text = when (status) {
                PenEventSender.Status.PAIRING_REQUIRED -> getString(R.string.status_pairing_short)
                PenEventSender.Status.COOLDOWN -> getString(R.string.status_retrying_short)
                PenEventSender.Status.ERROR -> getString(R.string.status_error_short)
                PenEventSender.Status.DISCONNECTED -> getString(R.string.status_disconnected)
                else -> message
            }
            statusText.tooltipText = message
            statusText.contentDescription = message
            statusContainer.contentDescription = getString(R.string.open_connection_settings, message)
            val colorRes = when (status) {
                PenEventSender.Status.CONNECTED -> R.color.status_connected
                PenEventSender.Status.CONNECTING -> R.color.status_connecting
                PenEventSender.Status.DISCONNECTED,
                PenEventSender.Status.PAIRING_REQUIRED,
                PenEventSender.Status.COOLDOWN,
                PenEventSender.Status.ERROR -> R.color.status_disconnected
            }
            statusIndicator.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, colorRes))
        }
    }

    override fun onStart() {
        super.onStart()
        applySettings()
        statusText.setText(R.string.status_connecting)
        sender?.start()
    }

    override fun onStop() {
        penSurfaceView.cancelInput()
        sender?.stop()
        statusText.setText(R.string.status_disconnected)
        statusIndicator.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.status_disconnected))
        penSurfaceView.removeCallbacks(restoreChrome)
        penPresent = false
        super.onStop()
    }

    override fun onDestroy() {
        super.onDestroy()
        sender?.stop()
    }
}
