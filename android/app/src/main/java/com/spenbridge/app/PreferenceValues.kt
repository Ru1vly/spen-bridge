package com.spenbridge.app

import android.content.SharedPreferences

fun SharedPreferences.stringOrDefault(key: String, fallback: String): String =
    try { getString(key, fallback) ?: fallback } catch (_: ClassCastException) { fallback }
fun SharedPreferences.intOrDefault(key: String, fallback: Int): Int =
    try { getInt(key, fallback) } catch (_: ClassCastException) { fallback }
fun SharedPreferences.booleanOrDefault(key: String, fallback: Boolean): Boolean =
    try { getBoolean(key, fallback) } catch (_: ClassCastException) { fallback }
