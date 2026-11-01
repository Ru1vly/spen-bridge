package com.spenbridge.app

import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowInsetsControllerCompat

/** Apply after focus/attachment too, when a system theme transition has finished. */
internal fun AppCompatActivity.applySystemBarAppearance() {
    WindowInsetsControllerCompat(window, window.decorView).apply {
        isAppearanceLightStatusBars = resources.getBoolean(R.bool.light_system_bars)
        isAppearanceLightNavigationBars = resources.getBoolean(R.bool.light_system_bars)
    }
}
