package com.technicallyvu.scope.settings

import android.content.SharedPreferences
import androidx.compose.runtime.Immutable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** A per-driver rotation/mirror override, applied when that driver's session starts. */
@Immutable
data class DriverDefault(val rotation: Int, val mirror: Boolean)

/**
 * [Immutable] because [defaults] is a `kotlin.collections.Map`, which the Compose compiler infers
 * as unstable — which would make the whole class unstable and `SettingsScreen` non-skippable, so
 * the settings subtree would recompose with `ScopeScreen` at the stream's frame rate. Every field
 * here is a val holding an immutable value and the map is only ever replaced, never mutated, so
 * the promise holds.
 */
@Immutable
data class Settings(
    val denoise: Boolean = true,
    val denoiseStrength: Float = 0.6f,
    /** Cosmetic luma unsharp mask, applied after the denoiser. Off by default; it adds no detail. */
    val sharpen: Boolean = false,
    val sharpenStrength: Float = 0.5f,
    val doublePressWindowMs: Int = 1500,
    val haptics: Boolean = true,
    val keepScreenOn: Boolean = true,
    val showStats: Boolean = false,
    val tipsDismissed: Boolean = false,
    val pairVisible: Boolean = false,
    val pairVisibleVideo: Boolean = false,
    /** Align mode: phone preview behind the uv image, uv drawn at [alignW]/[alignX]/[alignY] (fractions of the view) with [alignAlpha]. */
    val alignMode: Boolean = false,
    val alignW: Float = 0.37f,
    val alignX: Float = 0.5f,
    val alignY: Float = 0.5f,
    val alignAlpha: Float = 0.55f,
    /** Record the phone's microphone (3.5 mm jack when plugged) into the paired video. */
    val pairAudio: Boolean = false,
    val defaults: Map<String, DriverDefault> = emptyMap(),
)

/**
 * SharedPreferences-backed settings store. Loaded once at construction; [flow] is updated on
 * every [update]. Values are clamped both on load (so a stale/malformed value left by an older
 * build never reaches the rest of the app) and on write.
 *
 * Deliberately free of any Compose/Android UI type beyond [SharedPreferences] itself, so a plain
 * JVM unit test can drive it with a fake `SharedPreferences` implementation.
 */
class AppSettings(private val prefs: SharedPreferences) {
    private val _flow = MutableStateFlow(load())
    val flow: StateFlow<Settings> = _flow

    /**
     * Applies [transform] to the current settings, clamps the result, publishes it, and persists it.
     *
     * `synchronized` because the read-modify-write must not interleave: every caller today is on
     * Main, but the class is otherwise thread-agnostic (the session worker already reads [flow]),
     * and an update lost here is a preference the user set and never got back. It also keeps
     * [persist] calls in the same order as the values they publish. [transform] is a tiny pure
     * `copy()` at every call site, so holding the lock across it costs nothing.
     */
    fun update(transform: (Settings) -> Settings) = synchronized(this) {
        val next = clamp(transform(_flow.value))
        _flow.value = next
        persist(next)
    }

    private fun load(): Settings = clamp(
        Settings(
            denoise = prefs.getBoolean(KEY_DENOISE, true),
            denoiseStrength = prefs.getFloat(KEY_DENOISE_STRENGTH, 0.6f),
            sharpen = prefs.getBoolean(KEY_SHARPEN, false),
            sharpenStrength = prefs.getFloat(KEY_SHARPEN_STRENGTH, 0.5f),
            doublePressWindowMs = prefs.getInt(KEY_DOUBLE_PRESS_WINDOW_MS, 1500),
            haptics = prefs.getBoolean(KEY_HAPTICS, true),
            keepScreenOn = prefs.getBoolean(KEY_KEEP_SCREEN_ON, true),
            showStats = prefs.getBoolean(KEY_SHOW_STATS, false),
            tipsDismissed = prefs.getBoolean(KEY_TIPS_DISMISSED, false),
            pairVisible = prefs.getBoolean(KEY_PAIR_VISIBLE, false),
            pairVisibleVideo = prefs.getBoolean(KEY_PAIR_VISIBLE_VIDEO, false),
            alignMode = prefs.getBoolean(KEY_ALIGN_MODE, false),
            alignW = prefs.getFloat(KEY_ALIGN_W, 0.37f),
            alignX = prefs.getFloat(KEY_ALIGN_X, 0.5f),
            alignY = prefs.getFloat(KEY_ALIGN_Y, 0.5f),
            alignAlpha = prefs.getFloat(KEY_ALIGN_ALPHA, 0.55f),
            pairAudio = prefs.getBoolean(KEY_PAIR_AUDIO, false),
            defaults = parseDefaults(prefs.getString(KEY_DEFAULTS, null)),
        ),
    )

    private fun persist(s: Settings) {
        prefs.edit()
            .putBoolean(KEY_DENOISE, s.denoise)
            .putFloat(KEY_DENOISE_STRENGTH, s.denoiseStrength)
            .putBoolean(KEY_SHARPEN, s.sharpen)
            .putFloat(KEY_SHARPEN_STRENGTH, s.sharpenStrength)
            .putInt(KEY_DOUBLE_PRESS_WINDOW_MS, s.doublePressWindowMs)
            .putBoolean(KEY_HAPTICS, s.haptics)
            .putBoolean(KEY_KEEP_SCREEN_ON, s.keepScreenOn)
            .putBoolean(KEY_SHOW_STATS, s.showStats)
            .putBoolean(KEY_TIPS_DISMISSED, s.tipsDismissed)
            .putBoolean(KEY_PAIR_VISIBLE, s.pairVisible)
            .putBoolean(KEY_PAIR_VISIBLE_VIDEO, s.pairVisibleVideo)
            .putBoolean(KEY_ALIGN_MODE, s.alignMode)
            .putFloat(KEY_ALIGN_W, s.alignW)
            .putFloat(KEY_ALIGN_X, s.alignX)
            .putFloat(KEY_ALIGN_Y, s.alignY)
            .putFloat(KEY_ALIGN_ALPHA, s.alignAlpha)
            .putBoolean(KEY_PAIR_AUDIO, s.pairAudio)
            .putString(KEY_DEFAULTS, serializeDefaults(s.defaults))
            .apply()
    }

    companion object {
        const val KEY_DENOISE = "denoise"
        const val KEY_DENOISE_STRENGTH = "denoise_strength"
        const val KEY_SHARPEN = "sharpen"
        const val KEY_SHARPEN_STRENGTH = "sharpen_strength"
        const val KEY_DOUBLE_PRESS_WINDOW_MS = "double_press_window_ms"
        const val KEY_HAPTICS = "haptics"
        const val KEY_KEEP_SCREEN_ON = "keep_screen_on"
        const val KEY_SHOW_STATS = "show_stats"
        const val KEY_TIPS_DISMISSED = "tips_dismissed"
        const val KEY_PAIR_VISIBLE = "pair_visible"
        const val KEY_PAIR_VISIBLE_VIDEO = "pair_visible_video"
        const val KEY_ALIGN_MODE = "align_mode"
        const val KEY_ALIGN_W = "align_w"
        const val KEY_ALIGN_X = "align_x"
        const val KEY_ALIGN_Y = "align_y"
        const val KEY_ALIGN_ALPHA = "align_alpha"
        const val KEY_PAIR_AUDIO = "pair_audio"
        const val KEY_DEFAULTS = "driver_defaults"

        private const val ENTRY_SEPARATOR = ";"
        private const val FIELD_SEPARATOR = ":"
        private val DRIVER_ID_RE = Regex("[a-z0-9-]+")
        private val VALID_ROTATIONS = setOf(0, 90, 180, 270)

        private fun clampStrength(v: Float): Float = v.coerceIn(0.2f, 1.0f)
        /** The sharpener accepts a gentler floor than the denoiser: `Sharpener.MIN_STRENGTH`. */
        private fun clampSharpenStrength(v: Float): Float = v.coerceIn(0.1f, 1.0f)
        private fun clampWindow(v: Int): Int = v.coerceIn(500, 5000)

        /** Snaps any int to the nearest member of [VALID_ROTATIONS], wrapping modulo 360. */
        private fun clampRotation(v: Int): Int {
            val snapped = (Math.round(v / 90.0).toInt() * 90) % 360
            return if (snapped < 0) snapped + 360 else snapped
        }

        private fun clamp(s: Settings): Settings = s.copy(
            alignW = s.alignW.coerceIn(0.05f, 2.0f), alignX = s.alignX.coerceIn(-1f, 2f), alignY = s.alignY.coerceIn(-1f, 2f), alignAlpha = s.alignAlpha.coerceIn(0f, 1f),
            denoiseStrength = clampStrength(s.denoiseStrength),
            sharpenStrength = clampSharpenStrength(s.sharpenStrength),
            doublePressWindowMs = clampWindow(s.doublePressWindowMs),
            defaults = s.defaults.mapValues { (_, d) -> DriverDefault(clampRotation(d.rotation), d.mirror) },
        )

        /**
         * Parses the `driverId:rotation:mirror;...` serialisation. Any entry that does not have
         * exactly 3 fields, has a driver id with characters outside `[a-z0-9-]`, a non-integer
         * rotation, or a mirror value other than "true"/"false" is dropped; the rest of the map
         * still parses. A completely malformed string simply yields an empty map.
         */
        private fun parseDefaults(raw: String?): Map<String, DriverDefault> {
            if (raw.isNullOrEmpty()) return emptyMap()
            val result = LinkedHashMap<String, DriverDefault>()
            for (entry in raw.split(ENTRY_SEPARATOR)) {
                if (entry.isEmpty()) continue
                val parts = entry.split(FIELD_SEPARATOR)
                if (parts.size != 3) continue
                val (id, rotStr, mirrorStr) = parts
                if (!DRIVER_ID_RE.matches(id)) continue
                val rotation = rotStr.toIntOrNull() ?: continue
                val mirror = when (mirrorStr) {
                    "true" -> true
                    "false" -> false
                    else -> continue
                }
                result[id] = DriverDefault(rotation, mirror)
            }
            return result
        }

        /**
         * The inverse of [parseDefaults], and deliberately symmetric with it: an id outside
         * [DRIVER_ID_RE] is dropped here rather than written and then silently lost on the next
         * load — or, if it contained a [FIELD_SEPARATOR] or an [ENTRY_SEPARATOR], written and then
         * *corrupting its neighbour* on the next load. Escaping was the alternative; dropping keeps
         * one regex as the single definition of a legal id, and nothing but a driver id from the
         * registry ever reaches this map.
         */
        private fun serializeDefaults(defaults: Map<String, DriverDefault>): String =
            defaults.entries
                .filter { DRIVER_ID_RE.matches(it.key) }
                .joinToString(ENTRY_SEPARATOR) { (id, d) -> "$id$FIELD_SEPARATOR${d.rotation}$FIELD_SEPARATOR${d.mirror}" }
    }
}
