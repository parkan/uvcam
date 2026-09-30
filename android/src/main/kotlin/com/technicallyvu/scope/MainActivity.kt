package com.technicallyvu.scope

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.activity.result.contract.ActivityResultContracts
import android.Manifest
import android.content.pm.PackageManager
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import com.technicallyvu.scope.media.VisibleCamera
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import com.technicallyvu.scope.settings.AppSettings
import com.technicallyvu.scope.ui.ScopeScreen
import com.technicallyvu.scope.ui.ScopeViewModel
import com.technicallyvu.scope.ui.theme.ScopeTheme

class MainActivity : ComponentActivity() {
    // The one settings store: created here, owned by the view model (which outlives a rotation, and
    // keeps the instance it was given).
    private val vm: ScopeViewModel by viewModels {
        ScopeViewModel.Factory(application, AppSettings(getSharedPreferences(PREFS_NAME, MODE_PRIVATE)))
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                    val device = IntentCompat.getParcelableExtra(intent, UsbManager.EXTRA_DEVICE, UsbDevice::class.java)
                    device?.let { vm.onDeviceDetached(it.deviceName) }
                }
                ACTION_USB_PERMISSION -> vm.onPermissionResult(intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false))
            }
        }
    }

    private val visibleCamera by lazy { VisibleCamera(this) }
    private val cameraPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) bindVisibleCamera() else vm.appSettingsPublic.update { it.copy(pairVisible = false, pairVisibleVideo = false) }
    }

    private val audioPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (!granted) vm.appSettingsPublic.update { it.copy(pairAudio = false) }
    }

    /** Tasker sends extras as strings; accept either form. */
    private fun handleTrigger(intent: Intent?) {
        when (intent?.action) {
            ACTION_START_RECORDING -> vm.onTrigger(true, intent.extras?.get("duration")?.toString()?.toIntOrNull() ?: 60)
            ACTION_STOP_RECORDING -> vm.onTrigger(false, 0)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleTrigger(intent)
    }

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun bindVisibleCamera() {
        visibleCamera.bind(this, display?.rotation ?: 0)
        vm.visibleCamera = visibleCamera
        vm.displayRotation = { display?.rotation ?: 0 }
    }

    private fun unbindVisibleCamera() {
        vm.visibleCamera = null
        visibleCamera.unbind()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        // the pair-visible setting owns the back camera: on -> ask once and bind, off -> release
        lifecycleScope.launch {
            vm.appSettingsPublic.flow.map { it.pairVisible || it.pairVisibleVideo }.distinctUntilChanged().collect { on ->
                when {
                    !on -> unbindVisibleCamera()
                    hasCameraPermission() -> bindVisibleCamera()
                    else -> cameraPermission.launch(Manifest.permission.CAMERA)
                }
            }
        }
        lifecycleScope.launch {
            vm.appSettingsPublic.flow.map { it.pairAudio }.distinctUntilChanged().collect { on ->
                if (on && ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    audioPermission.launch(Manifest.permission.RECORD_AUDIO)
                }
            }
        }
        val filter = IntentFilter().apply {
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
            addAction(ACTION_USB_PERMISSION)
        }
        ContextCompat.registerReceiver(this, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)
        setContent {
            ScopeTheme {
                // The flag follows the "keep screen on while streaming" preference: the view model
                // combines it with the connection state, so this only recomposes when the answer
                // actually flips, not on every frame.
                val keepScreenOn by vm.keepScreenOn.collectAsState()
                LaunchedEffect(keepScreenOn) {
                    if (keepScreenOn) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }
                // armed: screen stays on (see keepScreenOn) but as dark as the panel allows
                val armed by remember { vm.ui.map { it.sentry != null }.distinctUntilChanged() }.collectAsState(false)
                LaunchedEffect(armed) {
                    window.attributes = window.attributes.apply { screenBrightness = if (armed) 0.01f else WindowManager.LayoutParams.BRIGHTNESS_OVERRIDE_NONE }
                }
                ScopeScreen(vm, onRequestPermission = ::requestUsbPermission)
            }
        }
        // launched by a trigger while not running: refused as disarmed, but logged like any other
        handleTrigger(intent)
    }

    private fun requestUsbPermission(device: UsbDevice) {
        val usb = getSystemService(UsbManager::class.java)
        val intent = Intent(ACTION_USB_PERMISSION).setPackage(packageName)
        // FLAG_MUTABLE: the system fills in EXTRA_DEVICE/EXTRA_PERMISSION_GRANTED on this intent.
        val pi = PendingIntent.getBroadcast(this, 0, intent, PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        usb.requestPermission(device, pi)
    }

    override fun onDestroy() {
        unbindVisibleCamera()
        unregisterReceiver(receiver)
        super.onDestroy()
    }

    companion object {
        const val ACTION_USB_PERMISSION = "com.technicallyvu.scope.USB_PERMISSION"
        const val ACTION_START_RECORDING = "id.corvid.uvcam.START_RECORDING"
        const val ACTION_STOP_RECORDING = "id.corvid.uvcam.STOP_RECORDING"
        /** SharedPreferences file backing [AppSettings]. */
        const val PREFS_NAME = "scope_settings"
    }
}
