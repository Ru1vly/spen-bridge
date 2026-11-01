package com.spenbridge.app

import android.app.Activity
import android.app.Instrumentation
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import androidx.core.content.ContextCompat
import com.google.android.material.slider.Slider
import java.io.File

/** Native checks on an emulator, or explicitly opted-in isolated audit application on a device. */
class UiUxAuditInstrumentation : Instrumentation() {
    private var isolatedDevice = false
    private var talkBack = false
    private var livePen = false
    private var orientation: Int? = null
    private val automation get() = getUiAutomation(if (talkBack) android.app.UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES else 0)
    override fun onCreate(arguments: Bundle?) {
        super.onCreate(arguments)
        isolatedDevice = arguments?.getString("isolated_device") == "true"
        talkBack = arguments?.getString("talkback") == "true"
        livePen = arguments?.getString("live_pen") == "true"
        orientation = when (arguments?.getString("orientation")) {
            "landscape" -> android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            "portrait" -> android.content.pm.ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            else -> null
        }
        start()
    }
    override fun callActivityOnCreate(activity: Activity, state: Bundle?) {
        // Only the explicit test process gets lock-screen visibility; production activities do not.
        orientation?.let { activity.requestedOrientation = it }
        if (Build.VERSION.SDK_INT >= 27) {
            activity.setShowWhenLocked(true)
            activity.setTurnScreenOn(true)
        } else activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            android.view.WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON)
        activity.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        super.callActivityOnCreate(activity, state)
    }
    override fun callActivityOnResume(activity: Activity) {
        super.callActivityOnResume(activity)
        orientation?.let { activity.requestedOrientation = it }
    }
    override fun onStart() {
        val result = Bundle()
        if (Build.HARDWARE !in listOf("ranchu", "goldfish") &&
            !(isolatedDevice && targetContext.packageName.endsWith(".uiaudit"))) {
            result.putString("error", "Requires an emulator or the isolated audit app with isolated_device=true")
            finish(Activity.RESULT_CANCELED, result)
            return
        }
        if (livePen) {
            if (!targetContext.packageName.endsWith(".uiaudit")) {
                result.putString("error", "Live recording requires the isolated audit application")
                finish(Activity.RESULT_CANCELED, result)
            } else runLivePen()
            return
        }
        val prefs = targetContext.getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val original = prefs.all.toMap()
        val activities = mutableListOf<Activity>()
        var originalClipboard: android.content.ClipData? = null
        var clipboardCaptured = false
        var outcome = Activity.RESULT_CANCELED
        try {
            check(prefs.edit().clear().putBoolean(SettingsActivity.KEY_FORCE_LANDSCAPE, false).commit())
            var settings = startActivitySync(Intent(targetContext, SettingsActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as SettingsActivity
            activities.add(settings)
            waitForIdleSync()
            capture("settings-index")
            onUi {
                settings.findViewById<Button>(R.id.btnConnectionPage).performClick()
                settings.findViewById<Button>(R.id.btnApplyConnection).performClick()
                check(!prefs.contains(SettingsActivity.KEY_FINGERPRINT))
            }
            capture("settings-connection")
            onUi {
                val editor = settings.findViewById<com.google.android.material.textfield.TextInputEditText>(R.id.editFingerprint)
                editor.requestFocus()
                (targetContext.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                    .showSoftInput(editor, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
            }
            awaitUi("Keyboard did not appear") {
                androidx.core.view.ViewCompat.getRootWindowInsets(settings.window.decorView)
                    ?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) == true
            }
            onUi {
                val editor = settings.findViewById<View>(R.id.editFingerprint)
                editor.requestRectangleOnScreen(android.graphics.Rect(0,0,editor.width,editor.height),true)
                val visible = android.graphics.Rect()
                check(editor.getGlobalVisibleRect(visible) && visible.height() >= editor.height-2) { "Focused connection field is clipped by the keyboard" }
                val keyboard = androidx.core.view.ViewCompat.getRootWindowInsets(editor)!!
                    .getInsets(androidx.core.view.WindowInsetsCompat.Type.ime()).bottom
                check(visible.bottom <= settings.window.decorView.height-keyboard+2) { "Keyboard covers connection input" }
                (targetContext.getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                    .hideSoftInputFromWindow(editor.windowToken,0)
                editor.clearFocus()
            }
            awaitUi("Keyboard did not close") {
                androidx.core.view.ViewCompat.getRootWindowInsets(settings.window.decorView)
                    ?.isVisible(androidx.core.view.WindowInsetsCompat.Type.ime()) == false
            }
            result.putString("keyboard_insets","PASS: focused input remains fully visible above the actual Android keyboard")
            onUi {
                settings.findViewById<Button>(R.id.btnBack).performClick()
                settings.findViewById<Button>(R.id.btnInputPage).performClick()
            }
            capture("settings-input")
            onUi {
                settings.findViewById<Button>(R.id.btnBack).performClick()
                settings.findViewById<Button>(R.id.btnAreaPage).performClick()
            }
            awaitUi("Area preview was not laid out") {
                val preview = settings.findViewById<AreaPreviewView>(R.id.areaPreview)
                preview.width > 0 && preview.height > 0 && preview.isShown
            }
            onUi {
                settings.findViewById<android.widget.RadioButton>(R.id.rbAreaCustom).isChecked = true
                settings.findViewById<Slider>(R.id.sliderWidth).value = 60f
                settings.findViewById<Slider>(R.id.sliderHeight).value = 40f
                val preview = settings.findViewById<AreaPreviewView>(R.id.areaPreview)
                check(preview.areaWidth == 60 && preview.areaHeight == 40)
                check(!settings.findViewById<android.widget.RadioButton>(R.id.rbAreaFull).isChecked)
                settings.findViewById<Slider>(R.id.sliderHeight).value = 70f
                val time = SystemClock.uptimeMillis()
                val x = preview.width / 2f; val y = preview.height / 2f
                val delta = 40f * settings.resources.displayMetrics.density
                for ((action, px) in listOf(MotionEvent.ACTION_DOWN to x,
                        MotionEvent.ACTION_MOVE to (x + delta), MotionEvent.ACTION_UP to (x + delta))) {
                    val motion = MotionEvent.obtain(time, SystemClock.uptimeMillis(), action, px, y, 0)
                    check(preview.dispatchTouchEvent(motion))
                    motion.recycle()
                }
                check(settings.findViewById<Slider>(R.id.sliderOffsetX).value > 50f) { "Native preview drag did not update the slider" }
                settings.findViewById<Button>(R.id.btnAlignCenter).performClick()
                check(preview.offsetX == 50 && preview.offsetY == 50)
                settings.findViewById<Slider>(R.id.sliderWidth).value = 20f
                settings.findViewById<Slider>(R.id.sliderHeight).value = 20f
                for ((action, px) in listOf(MotionEvent.ACTION_DOWN to x,
                        MotionEvent.ACTION_MOVE to (x+delta), MotionEvent.ACTION_UP to (x+delta))) {
                    val motion = MotionEvent.obtain(time,SystemClock.uptimeMillis(),action,px,y,0)
                    check(preview.dispatchTouchEvent(motion)); motion.recycle()
                }
                check(preview.areaWidth==20 && preview.areaHeight==20 && preview.offsetX>50) { "Minimum area center could not be dragged independently of its handle" }
                settings.findViewById<Button>(R.id.btnAlignCenter).performClick()
                settings.findViewById<Button>(R.id.btnResetArea).performClick()
                check(preview.mode == SettingsActivity.MODE_FULL)
                check(!prefs.contains(SettingsActivity.KEY_AREA_MODE)) { "Reset persisted without Apply" }
                settings.findViewById<android.widget.RadioButton>(R.id.rbAreaCustom).isChecked = true
                settings.findViewById<Slider>(R.id.sliderWidth).value = 60f
                settings.findViewById<Slider>(R.id.sliderHeight).value = 40f
                settings.findViewById<Button>(R.id.btnSave).performClick()
                check(prefs.getInt(SettingsActivity.KEY_AREA_WIDTH, 0) == 60)
                check(prefs.getInt(SettingsActivity.KEY_AREA_HEIGHT, 0) == 40)
                check(!prefs.contains(SettingsActivity.KEY_FINGERPRINT))
                check(settings.findViewById<Slider>(R.id.sliderOffsetX).contentDescription.isNotBlank())
            }
            capture("settings-area")
            onUi {
                val slider = settings.findViewById<Slider>(R.id.sliderWidth)
                slider.requestRectangleOnScreen(android.graphics.Rect(0, 0, slider.width, slider.height), true)
                val provider = slider.accessibilityNodeProvider ?: error("Slider has no accessible range provider")
                val node = provider.createAccessibilityNodeInfo(0) ?: error("Slider range is inaccessible")
                check(node.rangeInfo != null)
                check(node.contentDescription.toString().contains("width", ignoreCase = true))
                val progress = Bundle().apply { putFloat(android.view.accessibility.AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE, 70f) }
                check(provider.performAction(0, android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, progress))
                check(slider.value == 70f && settings.findViewById<AreaPreviewView>(R.id.areaPreview).areaWidth == 70)
                if (talkBack) {
                    val manager = targetContext.getSystemService(Context.ACCESSIBILITY_SERVICE) as android.view.accessibility.AccessibilityManager
                    check(manager.isEnabled && manager.isTouchExplorationEnabled) { "TalkBack touch exploration is not active" }
                    check(provider.createAccessibilityNodeInfo(0)?.isAccessibilityFocused == true ||
                        provider.performAction(0, android.view.accessibility.AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null))
                    check(provider.createAccessibilityNodeInfo(0)?.isAccessibilityFocused == true)
                    result.putString("talkback_focus", "PASS: actual touch exploration active and named slider receives accessibility focus")
                }
                slider.value = 60f
                settings.findViewById<android.widget.RadioButton>(R.id.rbArea169).isChecked = true
                val height = settings.findViewById<Slider>(R.id.sliderHeight)
                check(!height.isEnabled && height.value == 60f)
                val heightProvider = height.accessibilityNodeProvider ?: error("Height range provider missing")
                check(!heightProvider.performAction(0, android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.id, progress))
                check(height.value == 60f)
                settings.findViewById<android.widget.RadioButton>(R.id.rbAreaCustom).isChecked = true
                height.value = 40f
            }
            result.putString("accessibility_range", "PASS: named range node and nonvisual set-progress action update the live preview")
            onUi {
                settings.findViewById<Slider>(R.id.sliderWidth).value = 55f
                settings.findViewById<com.google.android.material.textfield.TextInputEditText>(R.id.editFingerprint).setText("audit-draft")
            }
            val monitor = addMonitor(SettingsActivity::class.java.name, null, false)
            onUi { settings.recreate() }
            settings = waitForMonitorWithTimeout(monitor, 10000) as? SettingsActivity ?: error("Settings did not recreate")
            removeMonitor(monitor)
            activities.add(settings)
            waitForIdleSync()
            onUi {
                check(settings.findViewById<Slider>(R.id.sliderWidth).value == 55f) { "Area draft lost during recreation" }
                check(settings.findViewById<AreaPreviewView>(R.id.areaPreview).areaWidth == 55)
                check(settings.findViewById<com.google.android.material.textfield.TextInputEditText>(R.id.editFingerprint).text.toString() == "audit-draft")
                check(prefs.getInt(SettingsActivity.KEY_AREA_WIDTH, 0) == 60) { "Unapplied edit changed persisted mapping" }
                settings.findViewById<Button>(R.id.btnCancelSettings).performClick()
            }
            waitForIdleSync()
            val discard = automation.rootInActiveWindow?.findAccessibilityNodeInfosByViewId("android:id/button1")?.firstOrNull()
                ?: error("Discard confirmation is inaccessible")
            check(discard.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK))
            waitForIdleSync()
            check(prefs.getInt(SettingsActivity.KEY_AREA_WIDTH, 0) == 60)
            result.putString("settings_flows", "PASS: native drag, center/reset, explicit Apply, recreation drafts, and discard")
            val support = startActivitySync(Intent(targetContext, SupportActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as SupportActivity
            activities.add(support)
            waitForIdleSync()
            capture("settings-support")
            onUi {
                val locked = (targetContext.getSystemService(Context.KEYGUARD_SERVICE) as android.app.KeyguardManager).isDeviceLocked
                if (!locked) {
                    val clipboard = targetContext.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                    originalClipboard = clipboard.primaryClip
                    val canRestore = originalClipboard?.let { clip ->
                        (0 until clip.itemCount).all { clip.getItemAt(it).uri == null && clip.getItemAt(it).intent == null }
                    } ?: true
                    if (canRestore) {
                        clipboardCaptured = true
                        support.findViewById<Button>(R.id.btnCopyReport).performClick()
                        val copied = clipboard.primaryClip?.getItemAt(0)?.text?.toString().orEmpty()
                        check(copied.contains("Pairing credentials, addresses and logs are excluded."))
                        result.putString("clipboard_readback", "PASS")
                    } else result.putString("clipboard_readback", "Skipped to preserve a non-text clipboard item")
                } else result.putString("clipboard_readback", "Skipped under keyguard to preserve the existing clipboard")
                support.finish()
                settings.finish()
            }
            SystemClock.sleep(2500) // Let the OS-owned clipboard confirmation leave the screen.
            val main = startActivitySync(Intent(targetContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            activities.add(main)
            waitForIdleSync()
            onUi {
                val time = SystemClock.uptimeMillis()
                val properties = MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_STYLUS }
                val coordinates = MotionEvent.PointerCoords().apply { x = 200f; y = 200f }
                val hover = MotionEvent.obtain(time, time, MotionEvent.ACTION_HOVER_ENTER, 1,
                    arrayOf(properties), arrayOf(coordinates), 0, 0, 1f, 1f, 1, 0, InputDevice.SOURCE_STYLUS, 0)
                main.dispatchGenericMotionEvent(hover)
                hover.recycle()
                for (id in listOf(R.id.topBar, R.id.btnExpand, R.id.statusContainer))
                    check(main.findViewById<View>(id).visibility != View.VISIBLE)
                val root = main.findViewById<View>(R.id.mainRoot)
                val bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
                root.draw(Canvas(bitmap))
                val color = ContextCompat.getColor(main, R.color.canvas_bg)
                for (x in 0 until bitmap.width step 8) for (y in 0 until bitmap.height step 8)
                    check(bitmap.getPixel(x,y) == color) { "Tablet mode painted an element" }
                bitmap.recycle()
            }
            injectStylus(main, MotionEvent.ACTION_HOVER_ENTER)
            for ((x, y) in listOf(.02f to .02f, .98f to .02f, .98f to .98f, .02f to .98f)) {
                injectStylus(main, MotionEvent.ACTION_HOVER_MOVE, x, y)
                onUi { assertChromeHidden(main) }
            }
            injectStylus(main, MotionEvent.ACTION_HOVER_EXIT)
            SystemClock.sleep(100)
            injectStylus(main, MotionEvent.ACTION_DOWN)
            SystemClock.sleep(850)
            onUi { assertChromeHidden(main) }
            injectStylus(main, MotionEvent.ACTION_MOVE)
            injectPalm(main, true)
            onUi { assertChromeHidden(main) }
            injectPalm(main, false)
            injectStylus(main, MotionEvent.ACTION_UP)
            injectStylus(main, MotionEvent.ACTION_HOVER_ENTER)
            onUi { assertChromeHidden(main) }
            val field = MainActivity::class.java.getDeclaredField("sender").apply { isAccessible = true }
            val sender = field.get(main) as PenEventSender
            sender.stop()
            waitForIdleSync()
            onUi { assertChromeHidden(main) }
            sender.start()
            waitForIdleSync()
            onUi { assertChromeHidden(main) }
            injectStylus(main, MotionEvent.ACTION_DOWN)
            injectStylus(main, MotionEvent.ACTION_CANCEL)
            injectStylus(main, MotionEvent.ACTION_HOVER_ENTER)
            SystemClock.sleep(850)
            onUi { assertChromeHidden(main) }
            capture("tablet-hover")
            injectStylus(main, MotionEvent.ACTION_HOVER_EXIT)
            SystemClock.sleep(900)
            onUi { check(main.findViewById<View>(R.id.topBar).visibility == View.VISIBLE) { "Controls did not return after proximity exit" } }
            injectStylus(main, MotionEvent.ACTION_HOVER_ENTER)
            onUi { assertChromeHidden(main) }
            result.putString("stylus_dispatch", "PASS: system-injected edge hover, contact/move/up, palm pointers, cancel, transport stop/start, and delayed restore")
            result.putString("ui_ux_checks", "PASS: local apply without pairing, shared preview, accessible sliders, hidden chrome, blank surface")
            outcome = Activity.RESULT_OK
        } catch (error: Throwable) {
            result.putString("error", error.stackTraceToString())
        } finally {
            if (clipboardCaptured) onUi {
                val clipboard = targetContext.getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                originalClipboard?.let { clipboard.setPrimaryClip(it) } ?: run {
                    if (Build.VERSION.SDK_INT >= 28) clipboard.clearPrimaryClip()
                    else clipboard.setPrimaryClip(android.content.ClipData.newPlainText("", ""))
                }
            }
            onUi { activities.forEach { if (!it.isFinishing) it.finish() } }
            val editor = prefs.edit().clear()
            original.forEach { (key,value) -> when(value) {
                is String -> editor.putString(key,value)
                is Int -> editor.putInt(key,value)
                is Boolean -> editor.putBoolean(key,value)
                is Float -> editor.putFloat(key,value)
                is Long -> editor.putLong(key,value)
                is Set<*> -> editor.putStringSet(key,value.filterIsInstance<String>().toSet())
            } }
            editor.commit()
        }
        finish(outcome, result)
    }
    private fun assertChromeHidden(main: MainActivity) {
        for (id in listOf(R.id.topBar, R.id.btnExpand, R.id.statusContainer))
            check(main.findViewById<View>(id).visibility != View.VISIBLE) { "Chrome visible during pen use" }
    }
    private fun injectStylus(main: MainActivity, action: Int, nx: Float = .5f, ny: Float = .5f) {
        waitForIdleSync()
        check(automation.rootInActiveWindow?.packageName == targetContext.packageName) { "Test app lost input focus" }
        var x = 0f; var y = 0f
        onUi {
            val view = main.findViewById<View>(R.id.penSurfaceView)
            val origin = IntArray(2); view.getLocationOnScreen(origin)
            x = origin[0] + view.width * nx; y = origin[1] + view.height * ny
        }
        val time = SystemClock.uptimeMillis()
        val properties = MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_STYLUS }
        val coords = MotionEvent.PointerCoords().apply { this.x = x; this.y = y; pressure = if (action == MotionEvent.ACTION_DOWN || action == MotionEvent.ACTION_MOVE) .5f else 0f }
        val event = MotionEvent.obtain(time, time, action, 1, arrayOf(properties), arrayOf(coords), 0, 0, 1f, 1f, 1, 0, InputDevice.SOURCE_STYLUS, 0)
        try { check(automation.injectInputEvent(event, true)) { "System rejected stylus input" } }
        finally { event.recycle() }
        waitForIdleSync()
    }
    private fun injectPalm(main: MainActivity, down: Boolean) {
        val origin = IntArray(2); var x = 0f; var y = 0f
        onUi {
            val view = main.findViewById<View>(R.id.penSurfaceView); view.getLocationOnScreen(origin)
            x = origin[0] + view.width / 2f; y = origin[1] + view.height / 2f
        }
        val properties = arrayOf(
            MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_STYLUS },
            MotionEvent.PointerProperties().apply { id = 1; toolType = MotionEvent.TOOL_TYPE_FINGER })
        val coords = arrayOf(MotionEvent.PointerCoords().apply { this.x=x; this.y=y; pressure=.5f },
            MotionEvent.PointerCoords().apply { this.x=x+20; this.y=y+20; pressure=.5f })
        val time = SystemClock.uptimeMillis()
        val action = (if (down) MotionEvent.ACTION_POINTER_DOWN else MotionEvent.ACTION_POINTER_UP) or
            (1 shl MotionEvent.ACTION_POINTER_INDEX_SHIFT)
        val event = MotionEvent.obtain(time,time,action,2,properties,coords,0,0,1f,1f,1,0,InputDevice.SOURCE_STYLUS,0)
        try { check(automation.injectInputEvent(event,true)) }
        finally { event.recycle() }
        waitForIdleSync()
    }

    private fun runLivePen() {
        val result = Bundle()
        val prefs = targetContext.getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE)
        val original = prefs.all.toMap()
        val actions = linkedMapOf<String,Int>()
        val devices = linkedSetOf<String>()
        var violations = 0
        var lastAction = -1
        var lastTime = 0L
        var captured = false
        var idleRestored = false
        var main: MainActivity? = null
        var passed = false
        try {
            check(prefs.edit().clear().putBoolean(SettingsActivity.KEY_FORCE_LANDSCAPE,false).commit())
            val activity = startActivitySync(Intent(targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) as MainActivity
            main = activity
            waitForIdleSync()
            awaitUi("Live surface did not receive focus") { activity.hasWindowFocus() }
            onUi {
                val surface = activity.findViewById<View>(R.id.penSurfaceView)
                fun observe(event: MotionEvent) {
                    val device = InputDevice.getDevice(event.deviceId) ?: return
                    val pen = (0 until event.pointerCount).any { event.getToolType(it) in listOf(MotionEvent.TOOL_TYPE_STYLUS,MotionEvent.TOOL_TYPE_ERASER) }
                    if (!pen || !device.name.contains("pen",ignoreCase=true)) return
                    val name = MotionEvent.actionToString(event.actionMasked)
                    actions[name]=(actions[name]?:0)+1; devices.add(device.name)
                    lastAction=event.actionMasked; lastTime=SystemClock.uptimeMillis()
                    if (listOf(R.id.topBar,R.id.btnExpand,R.id.statusContainer).any { activity.findViewById<View>(it).visibility==View.VISIBLE }) violations++
                }
                surface.setOnHoverListener { _,event -> observe(event); false }
                surface.setOnTouchListener { _,event -> observe(event); false }
            }
            sendStatus(1,Bundle().apply { putString("live_pen_status","READY: isolated blank surface; waiting for actual hardware pen") })
            val end = SystemClock.uptimeMillis()+60000
            while (SystemClock.uptimeMillis()<end) {
                var any=false; var complete=false
                onUi {
                    any=actions.isNotEmpty()
                    complete=(actions["ACTION_DOWN"]?:0)>0 && (actions["ACTION_UP"]?:0)>0 &&
                        (actions["ACTION_HOVER_EXIT"]?:0)>0 && ((actions["ACTION_HOVER_ENTER"]?:0)>0 || (actions["ACTION_HOVER_MOVE"]?:0)>0)
                    if (lastAction==MotionEvent.ACTION_HOVER_EXIT && SystemClock.uptimeMillis()-lastTime>900)
                        idleRestored=activity.findViewById<View>(R.id.topBar).visibility==View.VISIBLE || activity.findViewById<View>(R.id.btnExpand).visibility==View.VISIBLE
                }
                if (any && !captured) { capture("live-hardware-pen"); captured=true }
                if (complete && idleRestored) { passed=violations==0; break }
                SystemClock.sleep(100)
            }
            onUi {
                result.putString("hardware_devices",devices.joinToString())
                result.putString("hardware_actions",org.json.JSONObject(actions as Map<*,*>).toString())
                result.putInt("chrome_violations",violations)
                result.putBoolean("idle_restored",idleRestored)
                result.putString("live_pen",if(passed) "PASS: actual hardware hover/contact/up/exit, hidden chrome, and idle restore" else "NOT VERIFIED: complete physical stroke was not observed")
            }
        } catch (error: Throwable) { result.putString("error",error.stackTraceToString()) }
        finally {
            onUi { main?.findViewById<View>(R.id.penSurfaceView)?.apply { setOnHoverListener(null); setOnTouchListener(null) }; main?.finish() }
            val editor=prefs.edit().clear()
            original.forEach { (key,value) -> when(value) {
                is String -> editor.putString(key,value); is Int -> editor.putInt(key,value)
                is Boolean -> editor.putBoolean(key,value); is Float -> editor.putFloat(key,value)
                is Long -> editor.putLong(key,value); is Set<*> -> editor.putStringSet(key,value.filterIsInstance<String>().toSet())
            } }; editor.commit()
        }
        finish(if(passed) Activity.RESULT_OK else Activity.RESULT_CANCELED,result)
    }

    private fun awaitUi(message: String, predicate: () -> Boolean) {
        repeat(50) {
            var ready = false
            onUi { ready = predicate() }
            if (ready) return
            SystemClock.sleep(100)
        }
        error(message)
    }
    private fun onUi(block: () -> Unit) {
        var failure: Throwable? = null
        runOnMainSync { try { block() } catch (error: Throwable) { failure = error } }
        failure?.let { throw it }
    }
    private fun capture(name: String) {
        waitForIdleSync()
        var appVisible = false
        repeat(30) {
            if (automation.rootInActiveWindow?.packageName == targetContext.packageName) appVisible = true
            if (!appVisible) SystemClock.sleep(100)
        }
        check(appVisible) { "Test app is not the active visible window; screen capture refused" }
        SystemClock.sleep(400) // Allow native state transitions and system-bar appearance to settle.
        val bitmap = automation.takeScreenshot() ?: error("Screenshot unavailable")
        orientation?.let { expected ->
            check((bitmap.width > bitmap.height) == (expected == android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)) {
                "Captured window orientation does not match the requested test"
            }
        }
        val dir = File(targetContext.filesDir, "ui-ux-audit").apply { mkdirs() }
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        bitmap.recycle()
    }
}
