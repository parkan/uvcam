package com.technicallyvu.scope.media

import android.content.ContentValues
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.util.Log
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import android.provider.MediaStore
import androidx.camera.core.CameraSelector
import androidx.camera.core.CameraControl
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.SurfaceOrientedMeteringPointFactory
import java.util.concurrent.TimeUnit
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.view.PreviewView
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.MediaStoreOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * The phone's back camera, kept bound (warm) while a pairing setting is on. Still capture and a
 * video recorder share one session; no preview use case, nothing is shown. Stills come back as
 * JPEG bytes with CameraX's EXIF orientation set; videos go straight to MediaStore.
 */
@OptIn(ExperimentalCamera2Interop::class)
class VisibleCamera(private val context: Context, private val folder: String = context.getString(com.technicallyvu.scope.R.string.media_folder_name)) {
    private var provider: ProcessCameraProvider? = null
    private var capture: ImageCapture? = null
    private var recorder: Recorder? = null
    private var recording: Recording? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var control: CameraControl? = null
    private var owner: LifecycleOwner? = null
    private var preview: Preview? = null
    private var previewView: PreviewView? = null

    /** No-op by design: the target rotation is pinned to ROTATION_0 so files always carry the same sensor orientation. */
    fun updateRotation(displayRotation: Int) = Unit

    val isBound: Boolean get() = capture != null

    /**
     * Pin the geometry: one physical lens, zoom 1.0, no electronic or optical stabilisation. EIS slides
     * a crop window around the sensor frame by frame and a logical multi-camera may swap lenses, both
     * of which break the fixed scope->phone homography the registration relies on.
     */
    private fun <T> lockGeometry(b: androidx.camera.core.ExtendableBuilder<T>, physicalId: String?) {
        val ext = Camera2Interop.Extender(b)
        ext.setCaptureRequestOption(CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE, CaptureRequest.CONTROL_VIDEO_STABILIZATION_MODE_OFF)
        ext.setCaptureRequestOption(CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE, CaptureRequest.LENS_OPTICAL_STABILIZATION_MODE_OFF)
        if (physicalId != null) ext.setPhysicalCameraId(physicalId)
    }

    /** The main (widest-aperture, ~24 mm) physical lens behind the default back camera, if it is a logical multi-camera. */
    private fun mainPhysicalLens(): String? {
        val cm = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val back = cm.cameraIdList.firstOrNull { cm.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK } ?: return null
        val ch = cm.getCameraCharacteristics(back)
        val physical = ch.physicalCameraIds
        val logicalFocal = ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)?.firstOrNull()
        Log.i(TAG, "back camera $back focal=$logicalFocal physical=$physical eis=${ch.get(CameraCharacteristics.CONTROL_AVAILABLE_VIDEO_STABILIZATION_MODES)?.toList()} ois=${ch.get(CameraCharacteristics.LENS_INFO_AVAILABLE_OPTICAL_STABILIZATION)?.toList()}")
        if (physical.isEmpty()) return null
        val described = physical.map { id ->
            val c = cm.getCameraCharacteristics(id)
            val f = c.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS)?.firstOrNull() ?: 0f
            val w = c.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE)?.width ?: 1f
            Log.i(TAG, "  physical $id focal=$f sensorW=$w equiv35=${36f * f / w}")
            Triple(id, f, 36f * f / w)
        }
        // the lens whose focal length the logical camera reports as its own is the default (main) one
        return (described.firstOrNull { it.second == logicalFocal } ?: described.minByOrNull { kotlin.math.abs(it.third - 24f) })?.first
    }

    fun bind(owner: LifecycleOwner, displayRotation: Int) {
        if (capture != null) return
        this.owner = owner
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            val p = future.get()
            val physicalId = runCatching { mainPhysicalLens() }.onFailure { Log.w(TAG, "lens query failed", it) }.getOrNull()
            Log.i(TAG, "locking physical lens ${physicalId ?: "(none, single camera)"}, zoom 1.0, EIS/OIS off")
            val icb = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .setTargetRotation(android.view.Surface.ROTATION_0)   // fixed: no auto-rotate, orient in post
            lockGeometry(icb, physicalId)
            val ic = icb.build()
            // 720p: the phone is also decoding the scope stream and encoding its own clip, and
            // sits in the sun; 1080p buys nothing for registration against a 640x480 partner
            val rec = Recorder.Builder()
                .setQualitySelector(QualitySelector.from(Quality.HD, FallbackStrategy.lowerQualityOrHigherThan(Quality.HD)))
                .build()
            val vcb = VideoCapture.Builder(rec).setTargetRotation(android.view.Surface.ROTATION_0).setVideoStabilizationEnabled(false)
            lockGeometry(vcb, physicalId)
            val vc = vcb.build()
            p.unbindAll()
            val cam = bindAll(p, owner, ic, vc)
            cam.cameraControl.setZoomRatio(1f)
            control = cam.cameraControl
            refocus(hold = true)
            provider = p
            capture = ic
            recorder = rec
            videoCapture = vc
        }, ContextCompat.getMainExecutor(context))
    }

    /** Binds the still and video use cases plus the align-mode preview when one is attached. */
    private fun bindAll(p: ProcessCameraProvider, owner: LifecycleOwner, ic: ImageCapture, vc: VideoCapture<Recorder>) =
        preview?.let { p.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, it, ic, vc) }
            ?: p.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, ic, vc)

    /**
     * Shows the back camera in [view] (align mode). Rebinds with a Preview use case; stills and
     * video keep working. Main thread. A running clip is never interrupted: the preview then
     * attaches on the next bind.
     */
    fun attachPreview(view: PreviewView) {
        if (preview != null && previewView === view) return
        previewView = view
        val pv = Preview.Builder().build()
        pv.surfaceProvider = view.surfaceProvider
        preview = pv
        rebind()
    }

    fun detachPreview() {
        preview = null
        previewView = null
        rebind()
    }

    private fun rebind() {
        val p = provider ?: return
        val o = owner ?: return
        val ic = capture ?: return
        val vc = videoCapture ?: return
        if (recording != null) return
        p.unbindAll()
        val cam = bindAll(p, o, ic, vc)
        cam.cameraControl.setZoomRatio(1f)
        control = cam.cameraControl
        refocus(hold = true)
    }

    fun unbind() {
        recording?.stop()
        recording = null
        provider?.unbindAll()
        provider = null
        capture = null
        recorder = null
        videoCapture = null
        control = null
        owner = null
        preview = null
        previewView = null
    }


    /**
     * Focus and meter where the scope is looking. Without a preview the phone's continuous AF votes on
     * the whole frame and picks the background; the rig calibration says the UV footprint centre sits
     * at (0.43, 0.70) of the ROTATION_0 frame at 30 cm and (0.45, 0.63) at 50 cm, so one window there
     * covers the working range. [hold] keeps it until the next call; a capture re-triggers and waits.
     */
    fun refocus(hold: Boolean): com.google.common.util.concurrent.ListenableFuture<androidx.camera.core.FocusMeteringResult>? {
        val ctl = control ?: return null
        val pt = SurfaceOrientedMeteringPointFactory(1f, 1f).createPoint(0.44f, 0.67f, 0.30f)
        val b = FocusMeteringAction.Builder(pt, FocusMeteringAction.FLAG_AF or FocusMeteringAction.FLAG_AE)
        if (hold) b.disableAutoCancel() else b.setAutoCancelDuration(3, TimeUnit.SECONDS)
        return ctl.startFocusAndMetering(b.build())
    }

    /** Re-run focus/metering on the scope's footprint and wait for it (bounded) before a capture. */
    suspend fun refocusAndWait(timeoutMs: Long = 1200) {
        val f = refocus(hold = true) ?: return
        val ok = runCatching { kotlinx.coroutines.withTimeoutOrNull(timeoutMs) { kotlinx.coroutines.suspendCancellableCoroutine<Boolean> { cont ->
            f.addListener({ cont.resume(runCatching { f.get().isFocusSuccessful }.getOrDefault(false)) }, ContextCompat.getMainExecutor(context)) } } }.getOrNull()
        Log.i(TAG, "footprint focus: " + (ok?.let { if (it) "locked" else "not converged" } ?: "timeout"))
    }

    /** One JPEG from the back camera, or throws with CameraX's reason. */
    suspend fun captureJpeg(): ByteArray {
        val ic = capture ?: throw IllegalStateException("back camera not bound")
        return suspendCancellableCoroutine { cont ->
            ic.takePicture(ContextCompat.getMainExecutor(context), object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(image: ImageProxy) {
                    val buf = image.planes[0].buffer
                    val bytes = ByteArray(buf.remaining())
                    buf.get(bytes)
                    image.close()
                    cont.resume(bytes)
                }
                override fun onError(exception: ImageCaptureException) {
                    cont.resumeWithException(exception)
                }
            })
        }
    }

    /**
     * Start a phone-camera clip named [displayName]. [onStart] gets System.nanoTime() at the
     * recorder's Start event, the closest thing CameraX exposes to "first frame captured".
     * [onFinalize] gets the finished item's uri, or null when the clip failed and was discarded.
     */
    @android.annotation.SuppressLint("MissingPermission")
    fun startRecording(displayName: String, withAudio: Boolean, onStart: (Long) -> Unit, onFinalize: (android.net.Uri?, String?) -> Unit) {
        val rec = recorder ?: throw IllegalStateException("back camera not bound")
        if (recording != null) throw IllegalStateException("already recording")
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, displayName)
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/$folder")
        }
        val opts = MediaStoreOutputOptions.Builder(context.contentResolver, MediaStore.Video.Media.EXTERNAL_CONTENT_URI)
            .setContentValues(values)
            .build()
        val pending = rec.prepareRecording(context, opts)
        val micOk = ContextCompat.checkSelfPermission(context, android.Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED
        if (withAudio && micOk) pending.withAudioEnabled()
        recording = pending.start(ContextCompat.getMainExecutor(context)) { ev ->
            when (ev) {
                is VideoRecordEvent.Start -> onStart(System.nanoTime())
                is VideoRecordEvent.Finalize -> {
                    recording = null
                    // camerax keeps the file for most errors (e.g. ERROR_SOURCE_INACTIVE when the
                    // activity stops); an empty uri is the only real loss
                    val uri = ev.outputResults.outputUri.takeIf { it != android.net.Uri.EMPTY }
                    onFinalize(uri, if (ev.hasError()) "error ${ev.error}: ${ev.cause?.message}" else null)
                }
                else -> Unit
            }
        }
    }

    /**
     * A recording that never produced a Start event is stuck pending: the camera is not feeding
     * the video surface (seen 2026-10-19, 25 min lost). Drop it and rebuild the session.
     */
    fun resetAfterStall() {
        recording?.stop()
        recording = null
        rebind()
    }

    fun stopRecording() {
        recording?.stop()
    }

    /** Fold the measured start offset into the file name once it is known. */
    private companion object { const val TAG = "UVCam" }

    fun rename(uri: android.net.Uri, displayName: String) {
        context.contentResolver.update(uri, ContentValues().apply { put(MediaStore.Video.Media.DISPLAY_NAME, displayName) }, null, null)
    }
}
