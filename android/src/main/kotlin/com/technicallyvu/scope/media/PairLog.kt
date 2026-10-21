package com.technicallyvu.scope.media

import android.os.SystemClock
import android.util.Range
import java.io.BufferedWriter
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import android.os.ParcelFileDescriptor

/**
 * Per-frame timing sidecar for a paired recording, one CSV next to the clips. Every row carries a
 * CLOCK_BOOTTIME nanosecond stamp (SystemClock.elapsedRealtimeNanos), which is the clock the phone
 * camera's sensor timestamps are in on devices that report SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME.
 *
 * rows (stream,index,t_boot_ns,extra):
 *   uv,<n>,<arrival>,<frame.timestampNanos>     the n-th frame handed to the scope encoder
 *   uv_start / uv_stop,,<t>,
 *   vis_start,,<t>,                             recorder Start event (what the _vis_+Nms name is derived from)
 *   vis,<frameNumber>,<sensor_ts>,<ae fps range> every phone frame captured while the scope clip runs
 *   vis_file,,<t>,<final display name>
 *
 * The phone clip's mp4 timestamps are the sensor timestamps minus the first encoded one, so the
 * vis rows map onto the mp4 by matching timestamp differences; uv rows map by index.
 */
class PairLog(fd: ParcelFileDescriptor, uvName: String, visName: String?, sensorTimestampSource: String) : AutoCloseable {
    // the fd stays owned by the media store entry (closed by MediaStoreSaver.finishVideo); this
    // stream is flushed but never closed so the descriptor is not closed twice
    private val out = BufferedWriter(OutputStreamWriter(FileOutputStream(fd.fileDescriptor), Charsets.UTF_8), 1 shl 16)
    private val lock = Any()
    @Volatile private var closed = false

    init {
        val boot = SystemClock.elapsedRealtimeNanos()
        val mono = System.nanoTime()
        out.write("# uvcam pairlog 1\n")
        out.write("# uv_video $uvName\n")
        if (visName != null) out.write("# vis_video $visName\n")
        out.write("# clock CLOCK_BOOTTIME ns; sensor_timestamp_source $sensorTimestampSource; System.nanoTime at boot_ns $boot = $mono\n")
        out.write("stream,index,t_boot_ns,extra\n")
    }

    fun row(stream: String, index: Long?, tBootNs: Long, extra: String = "") {
        if (closed) return
        synchronized(lock) {
            if (closed) return
            out.write(stream); out.write(","); if (index != null) out.write(index.toString()); out.write(",")
            out.write(tBootNs.toString()); out.write(","); out.write(extra); out.write("\n")
        }
    }

    fun mark(stream: String, extra: String = "") = row(stream, null, SystemClock.elapsedRealtimeNanos(), extra)

    fun visFrame(frameNumber: Long, sensorNs: Long, fps: Range<Int>?) = row("vis", frameNumber, sensorNs, fps?.let { "${it.lower}-${it.upper}" } ?: "")

    override fun close() {
        synchronized(lock) {
            if (closed) return
            closed = true
            runCatching { out.flush() }
        }
    }
}
