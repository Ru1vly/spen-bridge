package com.spenbridge.app

import android.content.Context
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.button.MaterialButton
import java.net.DatagramSocket
import java.net.Socket
import java.util.concurrent.Executors

/** Nearby discovery and a one-time desktop approval. No credential entry. */
class PairingActivity : AppCompatActivity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val lock = Any()
    private var generation = 0L
    private var datagram: DatagramSocket? = null
    private var rawSocket: Socket? = null
    private var visible = true
    private lateinit var status: TextView
    private lateinit var list: LinearLayout
    private lateinit var progress: View
    private lateinit var refresh: View
    private lateinit var verification: View

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_pairing)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        controller.isAppearanceLightStatusBars = resources.getBoolean(R.bool.light_system_bars)
        controller.isAppearanceLightNavigationBars = resources.getBoolean(R.bool.light_system_bars)
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.pairingRoot)) { view, insets ->
            val safe = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(safe.left, safe.top, safe.right, safe.bottom)
            insets
        }
        val content = findViewById<View>(R.id.pairingContent)
        (content.parent as View).addOnLayoutChangeListener { parent, _, _, _, _, _, _, _, _ ->
            val width = minOf(parent.width, (840 * resources.displayMetrics.density).toInt())
            if (width > 0 && content.layoutParams.width != width) content.layoutParams = content.layoutParams.apply { this.width = width }
        }
        ViewCompat.setAccessibilityHeading(findViewById(R.id.pairingAppTitle), true)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.pairingTitle), true)
        status = findViewById(R.id.pairingStatus)
        list = findViewById(R.id.nearbyDesktopList)
        progress = findViewById(R.id.pairingProgress)
        refresh = findViewById(R.id.pairingRefresh)
        verification = findViewById(R.id.pairingVerification)
        findViewById<Button>(R.id.pairingBack).setOnClickListener { finish() }
        findViewById<Button>(R.id.pairingCancel).setOnClickListener { finish() }
        refresh.setOnClickListener { search() }
        search()
    }

    private fun cancelWork(): Long {
        val sockets: Pair<DatagramSocket?, Socket?>
        val token: Long
        synchronized(lock) {
            generation++
            token = generation
            sockets = datagram to rawSocket
            datagram = null
            rawSocket = null
        }
        sockets.first?.close()
        try { sockets.second?.close() } catch (_: java.io.IOException) { }
        return token
    }

    private fun current(token: Long): Boolean = synchronized(lock) { visible && token == generation }
    private fun update(token: Long, action: () -> Unit) = runOnUiThread { if (current(token) && !isFinishing) action() }

    private fun search() {
        val token = cancelWork()
        list.removeAllViews()
        list.visibility = View.VISIBLE
        verification.visibility = View.GONE
        progress.visibility = View.VISIBLE
        refresh.visibility = View.GONE
        status.setText(R.string.pairing_searching)
        var count = 0
        worker.execute {
            try {
                DesktopDiscovery.search({ socket ->
                    synchronized(lock) { if (!visible || token != generation) false else { datagram = socket;true } }
                }) { desktop ->
                    update(token) {
                        count++
                        status.setText(R.string.pairing_choose_desktop)
                        val button = MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle)
                        button.text = desktop.name
                        button.isAllCaps = false
                        button.minHeight = (52 * resources.displayMetrics.density).toInt()
                        button.setOnClickListener { connect(desktop) }
                        list.addView(button, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
                    }
                }
                update(token) {
                    progress.visibility = View.GONE
                    refresh.visibility = View.VISIBLE
                    if (count == 0) status.setText(R.string.pairing_nothing_found)
                }
            } catch (_: Exception) {
                update(token) { progress.visibility = View.GONE;refresh.visibility = View.VISIBLE;status.setText(R.string.pairing_discovery_failed) }
            }
        }
    }

    private fun connect(desktop: NearbyDesktop) {
        val token = cancelWork()
        list.visibility = View.GONE
        refresh.visibility = View.GONE
        verification.visibility = View.GONE
        progress.visibility = View.VISIBLE
        status.text = getString(R.string.pairing_connecting, desktop.name)
        worker.execute {
            try {
                val name = "${Build.MANUFACTURER} ${Build.MODEL}".take(80)
                val paired = DesktopPairingClient.pair(desktop, name, { socket ->
                    synchronized(lock) { if (!visible || token != generation) false else { rawSocket = socket;true } }
                }) { number ->
                    update(token) {
                        progress.visibility = View.GONE
                        verification.visibility = View.VISIBLE
                        val view = findViewById<TextView>(R.id.pairingNumber)
                        view.text = number.chunked(3).joinToString(" ")
                        view.contentDescription = getString(R.string.pairing_number_accessible, number.toList().joinToString(" "))
                        status.text = getString(R.string.pairing_waiting_approval, desktop.name)
                    }
                }
                update(token) {
                    getSharedPreferences(SettingsActivity.PREFS_NAME, Context.MODE_PRIVATE).edit()
                        .putString(SettingsActivity.KEY_SERVER_IP, paired.host)
                        .putInt(SettingsActivity.KEY_SERVER_PORT, paired.port)
                        .putString(SettingsActivity.KEY_FINGERPRINT, paired.fingerprint)
                        .putString(SettingsActivity.KEY_PAIRING_CODE, paired.code)
                        .putString(SettingsActivity.KEY_DESKTOP_NAME, paired.name).apply()
                    Toast.makeText(this, getString(R.string.pairing_complete, paired.name), Toast.LENGTH_SHORT).show()
                    setResult(RESULT_OK)
                    finish()
                }
            } catch (_: Exception) {
                update(token) {
                    progress.visibility = View.GONE
                    verification.visibility = View.GONE
                    refresh.visibility = View.VISIBLE
                    status.setText(R.string.pairing_failed)
                }
            }
        }
    }

    override fun onStop() {
        synchronized(lock) { visible = false }
        cancelWork()
        super.onStop()
    }

    override fun onRestart() {
        super.onRestart()
        synchronized(lock) { visible = true }
        search()
    }

    override fun onDestroy() {
        cancelWork()
        worker.shutdownNow()
        super.onDestroy()
    }
}
