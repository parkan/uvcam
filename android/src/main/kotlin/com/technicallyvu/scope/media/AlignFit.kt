package com.technicallyvu.scope.media

import android.graphics.Bitmap
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Finds where the uv frame sits on the phone preview: a scale-and-shift search scored by the
 * correlation of gradient magnitudes. Sign-agnostic on purpose, vegetation is bright in visible
 * and dark in uv. Runs on ~240 px wide greyscale copies, well under a second on the phone. The
 * result is in view fractions: uv width over view width, and the uv centre.
 */
object AlignFit {
    data class Result(val w: Float, val x: Float, val y: Float, val score: Float)

    private const val PW = 240

    fun fit(preview: Bitmap, uv: Bitmap, w0: Float, x0: Float, y0: Float): Result {
        val ph = (PW.toFloat() * preview.height / preview.width).roundToInt().coerceAtLeast(8)
        val gp = grad(gray(Bitmap.createScaledBitmap(preview, PW, ph, true)), PW, ph)
        normalise(gp)
        var best = Result(w0, x0, y0, -1f)
        for (sc in floatArrayOf(0.80f, 0.88f, 0.95f, 1.0f, 1.05f, 1.13f, 1.25f)) {
            val w = (w0 * sc).coerceIn(0.08f, 1.5f)
            val tw = (w * PW).roundToInt().coerceAtLeast(6)
            val th = (tw.toFloat() * uv.height / uv.width).roundToInt().coerceAtLeast(6)
            if (tw > 2 * PW || th > 2 * ph) continue
            val gt = grad(gray(Bitmap.createScaledBitmap(uv, tw, th, true)), tw, th)
            normalise(gt)
            var tn = 0.0; for (v in gt) tn += v * v
            val tnorm = sqrt(tn).toFloat().coerceAtLeast(1e-3f)
            // centre within +-25% of the view around the current position, 2 px steps
            val cx0 = (x0 * PW).roundToInt(); val cy0 = (y0 * ph).roundToInt()
            val rx = (0.25f * PW).roundToInt(); val ry = (0.25f * ph).roundToInt()
            var cy = cy0 - ry
            while (cy <= cy0 + ry) {
                var cx = cx0 - rx
                while (cx <= cx0 + rx) {
                    val s = score(gp, PW, ph, gt, tw, th, cx - tw / 2, cy - th / 2, tnorm)
                    if (s > best.score) best = Result(w, cx.toFloat() / PW, cy.toFloat() / ph, s)
                    cx += 2
                }
                cy += 2
            }
        }
        return best
    }

    private fun gray(b: Bitmap): FloatArray {
        val w = b.width; val h = b.height
        val px = IntArray(w * h); b.getPixels(px, 0, w, 0, 0, w, h)
        return FloatArray(w * h) { i -> val p = px[i]; 0.299f * ((p shr 16) and 255) + 0.587f * ((p shr 8) and 255) + 0.114f * (p and 255) }
    }

    /** 3x3 box blur then central-difference gradient magnitude; borders zero. */
    private fun grad(g: FloatArray, w: Int, h: Int): FloatArray {
        val bl = FloatArray(w * h)
        for (y in 1 until h - 1) for (x in 1 until w - 1) {
            var s = 0f
            for (dy in -1..1) for (dx in -1..1) s += g[(y + dy) * w + x + dx]
            bl[y * w + x] = s / 9f
        }
        val out = FloatArray(w * h)
        for (y in 1 until h - 1) for (x in 1 until w - 1) {
            val gx = bl[y * w + x + 1] - bl[y * w + x - 1]
            val gy = bl[(y + 1) * w + x] - bl[(y - 1) * w + x]
            out[y * w + x] = sqrt(gx * gx + gy * gy)
        }
        return out
    }

    private fun normalise(a: FloatArray) {
        var m = 0.0; for (v in a) m += v; m /= a.size
        var sd = 0.0; for (v in a) sd += (v - m) * (v - m); sd = sqrt(sd / a.size).coerceAtLeast(1e-3)
        for (i in a.indices) a[i] = ((a[i] - m) / sd).toFloat()
    }

    /** Normalised correlation over the overlap; the template must be at least half inside the view. */
    private fun score(p: FloatArray, pw: Int, ph: Int, t: FloatArray, tw: Int, th: Int, ox: Int, oy: Int, tnorm: Float): Float {
        val x0 = maxOf(0, ox); val y0 = maxOf(0, oy); val x1 = minOf(pw, ox + tw); val y1 = minOf(ph, oy + th)
        if (x1 <= x0 || y1 <= y0) return -1f
        if ((x1 - x0) * (y1 - y0) < tw * th / 2) return -1f
        var dot = 0f; var pn = 0f
        for (y in y0 until y1) {
            val prow = y * pw; val trow = (y - oy) * tw - ox
            for (x in x0 until x1) { val pv = p[prow + x]; val tv = t[trow + x]; dot += pv * tv; pn += pv * pv }
        }
        return dot / (tnorm * sqrt(pn).coerceAtLeast(1e-3f))
    }
}
