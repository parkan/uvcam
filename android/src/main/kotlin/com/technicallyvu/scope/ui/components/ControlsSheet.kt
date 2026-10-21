package com.technicallyvu.scope.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledIconToggleButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.technicallyvu.scope.R

private val ButtonSize = 56.dp

/**
 * Every on-screen control, as a translucent sheet across the bottom (compact, two fixed rows of
 * four) or a scrolling vertical rail on the end side (wide). The caller places and fades it; the
 * sheet itself only decides which buttons are live.
 *
 * Each control calls [onInteract] before its own action so using a control restarts the caller's
 * auto-hide timer instead of racing it.
 *
 * Every parameter is a stable primitive rather than the whole `UiState`: that state carries a new
 * `Bitmap` and new `StreamStats` on every frame, so taking it here would recompose eight buttons and
 * five hand-drawn glyphs at the stream frame rate. With these the sheet skips on the frames where
 * nothing it cares about changed.
 *
 * @param streaming a live stream *and* a live frame — after an unplug the last bitmap is dropped,
 * and a stale one must never leave Snapshot/Record enabled.
 */
@Composable
fun ControlsSheet(
    streaming: Boolean,
    recording: Boolean,
    recordingStarting: Boolean,
    denoise: Boolean,
    showStats: Boolean,
    wide: Boolean,
    onInteract: () -> Unit,
    onSnapshot: () -> Unit,
    onToggleRecording: () -> Unit,
    onRotate: () -> Unit,
    onToggleMirror: () -> Unit,
    onToggleDenoise: () -> Unit,
    align: Boolean,
    onToggleAlign: () -> Unit,
    onToggleStats: () -> Unit,
    onSettings: () -> Unit,
    onAbout: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // Row 1: the things done to a picture. Row 2: the things done to the app.
    val rowOne: @Composable () -> Unit = {
        GlyphButton(
            contentDescription = stringResource(R.string.cd_snapshot),
            enabled = streaming,
            onClick = { onInteract(); onSnapshot() },
        ) { tint -> cameraGlyph(tint) }

        // Record/Stop. Disabled during the start transition too: the recorder is not published yet,
        // so a second tap could only race the one in flight. The description flips with the
        // button's role, so TalkBack never says "start" on a stop.
        val recordCd = if (recording) stringResource(R.string.cd_stop) else stringResource(R.string.cd_record)
        IconButton(
            onClick = { onInteract(); onToggleRecording() },
            enabled = streaming && !recordingStarting,
            modifier = Modifier.size(ButtonSize).semantics { contentDescription = recordCd },
        ) {
            val enabled = streaming && !recordingStarting
            val tint = if (enabled) RecordRed else LocalContentColor.current
            when {
                recordingStarting -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = RecordRed)
                recording -> Canvas(Modifier.size(24.dp)) { stopGlyph(tint) }
                else -> Canvas(Modifier.size(24.dp)) { drawCircle(tint, radius = size.minDimension * 0.30f) }
            }
        }

        IconButton(
            onClick = { onInteract(); onRotate() },
            enabled = !recording,
            modifier = Modifier.size(ButtonSize),
        ) {
            Icon(Icons.Filled.Refresh, contentDescription = stringResource(R.string.cd_rotate))
        }

        GlyphButton(
            contentDescription = stringResource(R.string.cd_mirror),
            enabled = !recording,
            onClick = { onInteract(); onToggleMirror() },
        ) { tint -> mirrorGlyph(tint) }
    }

    val rowTwo: @Composable () -> Unit = {
        GlyphToggleButton(
            contentDescription = stringResource(R.string.cd_denoise),
            checked = denoise,
            onCheckedChange = { onInteract(); onToggleDenoise() },
        ) { tint -> denoiseGlyph(tint) }

        GlyphToggleButton(
            contentDescription = stringResource(R.string.cd_align),
            checked = align,
            onCheckedChange = { onInteract(); onToggleAlign() },
        ) { tint -> alignGlyph(tint) }

        GlyphToggleButton(
            contentDescription = stringResource(R.string.cd_stats),
            checked = showStats,
            onCheckedChange = { onInteract(); onToggleStats() },
        ) { tint -> statsGlyph(tint) }

        // Disabled while recording for the same reason as About below: the settings screen replaces
        // the live view, and with it the REC badge.
        IconButton(
            onClick = { onInteract(); onSettings() },
            enabled = !recording,
            modifier = Modifier.size(ButtonSize),
        ) {
            Icon(Icons.Filled.Settings, contentDescription = stringResource(R.string.cd_settings))
        }

        // Disabled while recording: About replaces the live view, and with it the REC badge — the
        // only on-screen sign that a clip is still being written.
        IconButton(
            onClick = { onInteract(); onAbout() },
            enabled = !recording,
            modifier = Modifier.size(ButtonSize),
        ) {
            Icon(Icons.Filled.Info, contentDescription = stringResource(R.string.cd_about))
        }
    }

    val shape = if (wide) {
        RoundedCornerShape(topStart = 20.dp, bottomStart = 20.dp)
    } else {
        RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    }
    Surface(
        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.85f),
        // Explicit: `contentColorFor` matches the *exact* colour-scheme role, and a translucent copy
        // of `surface` is not `surface`, so the default would fall back to LocalContentColor — black
        // — and every plain IconButton glyph would vanish into the sheet in dark mode.
        contentColor = MaterialTheme.colorScheme.onSurface,
        shape = shape,
        modifier = modifier,
    ) {
        if (wide) {
            Column(
                // Eight 56 dp buttons are taller than a short landscape window; scroll rather than clip.
                Modifier
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 4.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) { rowOne(); rowTwo() }
        } else {
            // Two fixed rows of four rather than a FlowRow. FlowRow wrapped on available width, so
            // the same eight buttons broke 7 + 1 at 411 dp and 6 + 2 at 360 dp — a lone Settings or
            // About stranded on a second line reads as a layout bug rather than a design. Four per
            // row is 4 × 56 = 224 dp of buttons, which fits inside the 352 dp a 360 dp phone leaves
            // after this padding (and inside 312 dp on a 320 dp device), so the split is the same
            // everywhere and SpaceEvenly just widens the gaps on a bigger screen.
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically,
                ) { rowOne() }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                    verticalAlignment = Alignment.CenterVertically,
                ) { rowTwo() }
            }
        }
    }
}

@Composable
private fun GlyphButton(
    contentDescription: String,
    enabled: Boolean = true,
    onClick: () -> Unit,
    glyph: DrawScope.(Color) -> Unit,
) {
    val cd = contentDescription
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.size(ButtonSize).semantics { this.contentDescription = cd },
    ) {
        val tint = LocalContentColor.current
        Canvas(Modifier.size(24.dp)) { glyph(tint) }
    }
}

@Composable
private fun GlyphToggleButton(
    contentDescription: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    glyph: DrawScope.(Color) -> Unit,
) {
    val cd = contentDescription
    FilledIconToggleButton(
        checked = checked,
        onCheckedChange = onCheckedChange,
        modifier = Modifier.size(ButtonSize).semantics { this.contentDescription = cd },
    ) {
        val tint = LocalContentColor.current
        Canvas(Modifier.size(24.dp)) { glyph(tint) }
    }
}

// ---- glyphs ----
// The material-icons-core set has no camera, mirror, denoise or record icon, so these five are
// drawn by hand at a common weight (stroke ≈ 8 % of the box) to sit consistently beside the three
// real icons (Refresh, Settings, Info).

/** A camera body with a lens ring and a viewfinder bump. */
private fun DrawScope.cameraGlyph(tint: Color) {
    val w = size.width
    val h = size.height
    val stroke = Stroke(width = w * 0.08f)
    drawRect(tint, topLeft = Offset(w * 0.34f, h * 0.14f), size = Size(w * 0.28f, h * 0.10f))
    drawRoundRect(
        tint,
        topLeft = Offset(w * 0.06f, h * 0.26f),
        size = Size(w * 0.88f, h * 0.58f),
        cornerRadius = CornerRadius(w * 0.12f, w * 0.12f),
        style = stroke,
    )
    drawCircle(tint, radius = w * 0.17f, center = Offset(w / 2f, h * 0.55f), style = stroke)
}

/** The stop square, matched in visual weight to the record circle. */
private fun DrawScope.stopGlyph(tint: Color) {
    val side = size.minDimension * 0.54f
    drawRoundRect(
        tint,
        topLeft = Offset((size.width - side) / 2f, (size.height - side) / 2f),
        size = Size(side, side),
        cornerRadius = CornerRadius(side * 0.15f, side * 0.15f),
    )
}

/**
 * An object and its reflection: two triangles across a dashed mirror line, the left one solid and
 * the right one outlined.
 *
 * Both are symmetric about the horizontal centre line, with their vertical edges facing the axis
 * and their apexes pointing outwards. The earlier version put both apexes at the bottom outer
 * corners, which made the pair narrow at the top and wide at the bottom — it read as a road
 * vanishing into the distance rather than as a reflection.
 */
private fun DrawScope.mirrorGlyph(tint: Color) {
    val w = size.width
    val h = size.height
    val cx = w / 2f
    val cy = h / 2f
    // Vertical edges sit just clear of the axis; apexes reach almost to the edges of the box.
    val edge = cx - w * 0.11f
    val top = h * 0.20f
    val bottom = h * 0.80f
    drawLine(
        tint,
        start = Offset(cx, h * 0.04f),
        end = Offset(cx, h * 0.96f),
        strokeWidth = w * 0.07f,
        pathEffect = PathEffect.dashPathEffect(floatArrayOf(w * 0.12f, w * 0.09f)),
    )
    val solid = Path().apply {
        moveTo(edge, top)
        lineTo(edge, bottom)
        lineTo(w * 0.05f, cy)
        close()
    }
    drawPath(solid, tint)
    val outlined = Path().apply {
        moveTo(w - edge, top)
        lineTo(w - edge, bottom)
        lineTo(w * 0.95f, cy)
        close()
    }
    drawPath(outlined, tint, style = Stroke(width = w * 0.07f))
}

/** A filter funnel: the closest simple shape to "smooth out the noise". */
private fun DrawScope.denoiseGlyph(tint: Color) {
    val w = size.width
    val h = size.height
    val funnel = Path().apply {
        moveTo(w * 0.10f, h * 0.18f)
        lineTo(w * 0.90f, h * 0.18f)
        lineTo(w * 0.58f, h * 0.52f)
        lineTo(w * 0.58f, h * 0.88f)
        lineTo(w * 0.42f, h * 0.74f)
        lineTo(w * 0.42f, h * 0.52f)
        close()
    }
    drawPath(funnel, tint, style = Stroke(width = w * 0.08f))
}

/** Three bars, ascending-ish: the stats overlay toggle. */
/** Two offset frames: the uv picture laid over the phone picture. */
private fun DrawScope.alignGlyph(tint: Color) {
    val s = size.minDimension
    drawRect(tint, topLeft = Offset(s * 0.12f, s * 0.20f), size = Size(s * 0.52f, s * 0.52f), style = Stroke(width = s * 0.08f))
    drawRect(tint, topLeft = Offset(s * 0.36f, s * 0.40f), size = Size(s * 0.52f, s * 0.40f), style = Stroke(width = s * 0.08f))
}

private fun DrawScope.statsGlyph(tint: Color) {
    val w = size.width
    val h = size.height
    val barWidth = w * 0.16f
    val gap = w * 0.10f
    val heights = floatArrayOf(0.42f, 0.68f, 0.28f)
    heights.forEachIndexed { i, frac ->
        val x = w * 0.17f + i * (barWidth + gap)
        drawRect(tint, topLeft = Offset(x, h * (0.84f - frac)), size = Size(barWidth, h * frac))
    }
}
