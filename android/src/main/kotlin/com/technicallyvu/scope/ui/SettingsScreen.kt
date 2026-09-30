package com.technicallyvu.scope.ui

import androidx.activity.compose.BackHandler
import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.technicallyvu.scope.R
import com.technicallyvu.scope.settings.DriverDefault
import com.technicallyvu.scope.settings.Settings
import kotlin.math.roundToInt

/**
 * Ends of the double-press window slider, in milliseconds, and its step.
 *
 * Deliberately 0.5–3.0 s rather than the spec's and plan's 1.0–2.5 s: the session already accepts
 * 500 ms–5 s, and both ends of the narrower range were reachable in testing — a fast double-tap
 * lands under 1.0 s and a deliberate, gloved one can run past 2.5 s. See docs/phase3b-notes.md.
 */
private const val WINDOW_MIN_MS = 500f
private const val WINDOW_MAX_MS = 3_000f
private const val WINDOW_STEP_MS = 100

/** Ends of the denoise strength slider. */
private const val STRENGTH_MIN = 0.2f
private const val STRENGTH_MAX = 1.0f

/** Ends of the sharpening strength slider (`Sharpener.MIN_STRENGTH`..`MAX_STRENGTH`). */
private const val SHARPEN_MIN = 0.1f
private const val SHARPEN_MAX = 1.0f

/** Minimum touch target for a whole settings row. */
private val RowHeight = 56.dp

/**
 * Every persisted preference, in five groups. The screen is stateless apart from the two things
 * that are genuinely local: which slider is mid-drag, and whether the reset confirmation is up.
 * [onChange] is handed a complete [Settings]; the store clamps and persists it, and the new value
 * comes back through [settings].
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    settings: Settings,
    onChange: (Settings) -> Unit,
    onBack: () -> Unit,
    onAbout: () -> Unit,
    onArm: (Int) -> Unit = {},
) {
    BackHandler(enabled = true, onBack = onBack)
    var confirmingReset by remember { mutableStateOf(false) }

    Scaffold(
        // The app is edge-to-edge (and targetSdk 36 enforces it anyway), and the theme opts into
        // drawing into the display cutout, so safeDrawing rather than the Scaffold's systemBars
        // default: the bar keeps clear of the status bar and a notch, and `insets` below keeps the
        // last row clear of the gesture bar.
        contentWindowInsets = WindowInsets.safeDrawing,
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.settings_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.action_back))
                    }
                },
                windowInsets = WindowInsets.safeDrawing.only(WindowInsetsSides.Horizontal + WindowInsetsSides.Top),
            )
        },
    ) { insets ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(insets)
                .verticalScroll(rememberScrollState())
                .padding(bottom = 24.dp),
        ) {
            GroupHeader(R.string.settings_group_image)
            SwitchRow(
                label = stringResource(R.string.settings_denoise_label),
                checked = settings.denoise,
                onCheckedChange = { onChange(settings.copy(denoise = it)) },
            )
            SliderRow(
                label = stringResource(R.string.settings_denoise_strength_label),
                // 0.6 -> "60 %". Rounded for display only; the stored value keeps its precision.
                value = settings.denoiseStrength,
                valueLabel = { stringResource(R.string.settings_percent_format, (it * 100).roundToInt()) },
                range = STRENGTH_MIN..STRENGTH_MAX,
                steps = 0,
                enabled = settings.denoise,
                onCommit = { onChange(settings.copy(denoiseStrength = it)) },
            )
            SwitchRow(
                label = stringResource(R.string.settings_sharpen_label),
                checked = settings.sharpen,
                onCheckedChange = { onChange(settings.copy(sharpen = it)) },
            )
            SliderRow(
                label = stringResource(R.string.settings_sharpen_strength_label),
                value = settings.sharpenStrength,
                valueLabel = { stringResource(R.string.settings_percent_format, (it * 100).roundToInt()) },
                range = SHARPEN_MIN..SHARPEN_MAX,
                steps = 0,
                enabled = settings.sharpen,
                onCommit = { onChange(settings.copy(sharpenStrength = it)) },
            )
            HelperText(stringResource(R.string.settings_sharpen_help))

            GroupHeader(R.string.settings_group_cable_button)
            SliderRow(
                label = stringResource(R.string.settings_double_press_window_label),
                value = settings.doublePressWindowMs.toFloat(),
                valueLabel = { stringResource(R.string.settings_seconds_format, it / 1000f) },
                range = WINDOW_MIN_MS..WINDOW_MAX_MS,
                // Discrete stops between (not counting) the two ends: 500..3000 in 100 ms steps.
                steps = ((WINDOW_MAX_MS - WINDOW_MIN_MS) / WINDOW_STEP_MS).toInt() - 1,
                onCommit = { onChange(settings.copy(doublePressWindowMs = it.roundToInt())) },
            )
            HelperText(stringResource(R.string.settings_double_press_window_help))

            GroupHeader(R.string.settings_group_feedback)
            SwitchRow(
                label = stringResource(R.string.settings_haptics_label),
                checked = settings.haptics,
                onCheckedChange = { onChange(settings.copy(haptics = it)) },
            )
            SwitchRow(
                label = stringResource(R.string.settings_pair_visible_label),
                checked = settings.pairVisible,
                onCheckedChange = { onChange(settings.copy(pairVisible = it)) },
            )
            HelperText(stringResource(R.string.settings_pair_visible_help))
            SwitchRow(
                label = stringResource(R.string.settings_pair_visible_video_label),
                checked = settings.pairVisibleVideo,
                onCheckedChange = { onChange(settings.copy(pairVisibleVideo = it)) },
            )
            HelperText(stringResource(R.string.settings_pair_visible_video_help))
            SwitchRow(
                label = stringResource(R.string.settings_pair_audio_label),
                checked = settings.pairAudio,
                onCheckedChange = { onChange(settings.copy(pairAudio = it)) },
            )
            HelperText(stringResource(R.string.settings_pair_audio_help))
            SwitchRow(
                label = stringResource(R.string.settings_keep_screen_on_label),
                checked = settings.keepScreenOn,
                onCheckedChange = { onChange(settings.copy(keepScreenOn = it)) },
            )
            SwitchRow(
                label = stringResource(R.string.settings_show_stats_label),
                checked = settings.showStats,
                onCheckedChange = { onChange(settings.copy(showStats = it)) },
            )
            // Only offers itself once the tips have actually been dismissed; Task 5 shows the card.
            if (settings.tipsDismissed) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                    TextButton(onClick = { onChange(settings.copy(tipsDismissed = false)) }) {
                        Text(stringResource(R.string.settings_show_tips_again))
                    }
                }
            }

            GroupHeader(R.string.settings_group_sentry)
            HelperText(stringResource(R.string.settings_sentry_help))
            Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
                for (m in listOf(30, 60, 90, 120)) {
                    TextButton(onClick = { onArm(m) }) { Text(stringResource(R.string.settings_arm_format, m)) }
                }
            }

            GroupHeader(R.string.settings_group_devices)
            if (settings.defaults.isEmpty()) {
                HelperText(stringResource(R.string.settings_devices_empty))
            } else {
                settings.defaults.entries.sortedBy { it.key }.forEach { (driverId, default) ->
                    DeviceRow(
                        driverId = driverId,
                        default = default,
                        onForget = { onChange(settings.copy(defaults = settings.defaults - driverId)) },
                    )
                }
            }
            OutlinedButton(
                onClick = { confirmingReset = true },
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            ) { Text(stringResource(R.string.settings_reset_all)) }

            GroupHeader(R.string.settings_group_about)
            TextRow(label = stringResource(R.string.settings_about_row), onClick = onAbout)
        }
    }

    if (confirmingReset) {
        AlertDialog(
            onDismissRequest = { confirmingReset = false },
            title = { Text(stringResource(R.string.settings_reset_title)) },
            text = { Text(stringResource(R.string.settings_reset_body)) },
            confirmButton = {
                TextButton(onClick = { confirmingReset = false; onChange(Settings()) }) {
                    Text(stringResource(R.string.action_reset))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmingReset = false }) { Text(stringResource(R.string.action_cancel)) }
            },
        )
    }
}

@Composable
private fun GroupHeader(@StringRes label: Int) {
    HorizontalDivider(Modifier.padding(top = 8.dp))
    Text(
        stringResource(label),
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 4.dp),
    )
}

@Composable
private fun HelperText(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
    )
}

/**
 * A label and a switch that are one accessibility node, not two: `toggleable` on the [Row] with a
 * null `onCheckedChange` on the [Switch] means TalkBack announces "<label>, switch, on" instead of
 * an unlabelled "switch, on", and the whole 56 dp row is the touch target rather than the thumb.
 */
@Composable
private fun SwitchRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = RowHeight)
            .toggleable(value = checked, role = Role.Switch, onValueChange = onCheckedChange)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
        Switch(checked = checked, onCheckedChange = null)
    }
}

@Composable
private fun TextRow(label: String, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
        TextButton(onClick = onClick, modifier = Modifier.heightIn(min = 48.dp)) { Text(label) }
    }
}

/**
 * A labelled slider whose value is only written when the drag ends: a settings write hits
 * SharedPreferences and, through the store, the running session, and neither wants one call per
 * pixel of travel. [draft] holds the in-flight value so the thumb still follows the finger.
 */
@Composable
private fun SliderRow(
    label: String,
    value: Float,
    valueLabel: @Composable (Float) -> String,
    range: ClosedFloatingPointRange<Float>,
    steps: Int,
    onCommit: (Float) -> Unit,
    enabled: Boolean = true,
) {
    var draft by remember { mutableStateOf<Float?>(null) }
    val shown = draft ?: value
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            val tint = LocalContentColor.current.copy(alpha = if (enabled) 1f else 0.38f)
            Text(label, style = MaterialTheme.typography.bodyLarge, color = tint)
            Text(valueLabel(shown), style = MaterialTheme.typography.bodyLarge, color = tint)
        }
        Slider(
            value = shown,
            onValueChange = { draft = it },
            onValueChangeFinished = { draft?.let(onCommit); draft = null },
            valueRange = range,
            steps = steps,
            enabled = enabled,
            modifier = Modifier.heightIn(min = 48.dp),
        )
    }
}

/** One remembered per-device orientation, with the button that forgets it. */
@Composable
private fun DeviceRow(driverId: String, default: DriverDefault, onForget: () -> Unit) {
    // Never the driver id, and never `core`'s own displayName: both are engineering labels, and
    // one of them carries a vendor-derived word. See driverNameRes.
    val name = driverDisplayName(driverId)
    val summary =
        if (default.mirror) stringResource(R.string.settings_device_rotation_mirrored_format, default.rotation)
        else stringResource(R.string.settings_device_rotation_format, default.rotation)
    val forgetCd = stringResource(R.string.cd_forget_device_format, name)
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = RowHeight)
            .padding(start = 16.dp, end = 8.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(name, style = MaterialTheme.typography.bodyLarge)
            Text(summary, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        TextButton(
            onClick = onForget,
            modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = forgetCd },
        ) { Text(stringResource(R.string.settings_forget)) }
    }
}
