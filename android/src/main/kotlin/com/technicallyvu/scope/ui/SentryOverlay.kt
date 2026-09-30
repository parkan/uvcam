package com.technicallyvu.scope.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/** Black screen while armed: what is left, what happened, one way out. Swallows taps so the sheet underneath stays put. */
@Composable
fun SentryOverlay(s: Sentry, recording: Boolean, onDisarm: () -> Unit) {
    var now by remember { mutableLongStateOf(System.nanoTime()) }
    LaunchedEffect(Unit) { while (true) { delay(1_000); now = System.nanoTime() } }
    val remainMin = ((s.untilNanos - now) / 60_000_000_000L).coerceAtLeast(0)
    val dim = Color(0xFF606060)
    Box(
        Modifier.fillMaxSize().background(Color.Black).pointerInput(Unit) { detectTapGestures { } },
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(if (recording) "REC" else "ARMED", color = if (recording) Color(0xFFFF3030) else Color(0xFFB03030), style = MaterialTheme.typography.headlineLarge)
            Spacer(Modifier.height(12.dp))
            Text("$remainMin min left", color = dim)
            Text("${s.accepted} accepted, ${s.refused} refused", color = dim)
            Text("${s.recordedMs / 1000} s recorded", color = dim)
            Text(s.lastEvent, color = dim, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(32.dp))
            OutlinedButton(onClick = onDisarm) { Text("Disarm") }
        }
    }
}
