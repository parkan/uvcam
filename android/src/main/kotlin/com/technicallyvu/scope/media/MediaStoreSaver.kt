package com.technicallyvu.scope.media

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import androidx.exifinterface.media.ExifInterface
import com.technicallyvu.scope.R
import java.io.ByteArrayOutputStream
import java.io.IOException

/**
 * Writes photos to Pictures/<folder> and clips to Movies/<folder> through MediaStore (no storage
 * permission needed on API 29+).
 *
 * Takes a [Context] rather than a bare `ContentResolver` because the failures it raises are shown
 * to the user (the view model appends them to a snackbar), so their text has to come from
 * resources — as does the album name, which the tips card promises by name.
 */
class MediaStoreSaver(
    private val context: Context,
    private val folder: String = context.getString(R.string.media_folder_name),
) {
    private val resolver get() = context.contentResolver

    fun saveJpeg(bytes: ByteArray, exifOrientation: Int?, displayName: String): Uri {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, displayName)
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/$folder")
            put(MediaStore.Images.Media.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: throw IOException(context.getString(R.string.error_media_create_failed))
        try {
            resolver.openOutputStream(uri)?.use { it.write(bytes) } ?: throw IOException(context.getString(R.string.error_media_open_failed))
            // Best effort: the pixels are already written, so a failed EXIF tag must not lose the
            // photo. The file stays a valid JPEG, just with the default orientation.
            if (exifOrientation != null) {
                runCatching {
                    resolver.openFileDescriptor(uri, "rw")?.use { pfd ->
                        ExifInterface(pfd.fileDescriptor).apply {
                            setAttribute(ExifInterface.TAG_ORIENTATION, exifOrientation.toString())
                            saveAttributes()
                        }
                    }
                }
            }
            resolver.update(uri, ContentValues().apply { put(MediaStore.Images.Media.IS_PENDING, 0) }, null, null)
            return uri
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            throw e
        }
    }

    fun saveBitmapJpeg(bitmap: Bitmap, displayName: String, quality: Int = 92): Uri {
        val out = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
        return saveJpeg(out.toByteArray(), null, displayName)
    }

    class PendingVideo(val uri: Uri, val fd: ParcelFileDescriptor, val displayName: String)

    fun createVideo(displayName: String): PendingVideo {
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, displayName)
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/$folder")
            put(MediaStore.Video.Media.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: throw IOException(context.getString(R.string.error_media_create_failed))
        val fd = resolver.openFileDescriptor(uri, "rw") ?: run { resolver.delete(uri, null, null); throw IOException(context.getString(R.string.error_media_open_failed)) }
        return PendingVideo(uri, fd, displayName)
    }

    fun finishVideo(video: PendingVideo, keep: Boolean) {
        runCatching { video.fd.close() }
        if (keep) resolver.update(video.uri, ContentValues().apply { put(MediaStore.Video.Media.IS_PENDING, 0) }, null, null)
        else resolver.delete(video.uri, null, null)
    }

    /**
     * A text sidecar. Scoped storage only lets non-media files into Download/ and Documents/, so it
     * lives in Documents/<folder>/ rather than next to the clip in Movies/.
     */
    fun createText(displayName: String, mime: String = "text/csv"): PendingVideo {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, displayName)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, "Documents/$folder")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val collection = MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        val uri = resolver.insert(collection, values) ?: throw IOException(context.getString(R.string.error_media_create_failed))
        val fd = resolver.openFileDescriptor(uri, "rw") ?: run { resolver.delete(uri, null, null); throw IOException(context.getString(R.string.error_media_open_failed)) }
        return PendingVideo(uri, fd, displayName)
    }
}
