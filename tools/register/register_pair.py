"""register a scope (uv) frame onto its paired phone photo and produce overlay + difference images.

usage: register_pair.py SCOPE_<stamp>.jpg   (expects SCOPE_<stamp>_vis.jpg next to it)
outputs: <stamp>_overlay.jpg, <stamp>_diff.jpg, <stamp>_uv_warped.jpg, <stamp>_vis_crop.jpg
"""
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


def load_gray(path, max_side=None):
    im = ImageOps.exif_transpose(Image.open(path)).convert("L")
    if max_side and max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    return np.asarray(im)


def main(scope_path, fallback_H=None):
    scope_path = Path(scope_path)
    stamp = scope_path.stem.replace("SCOPE_", "")
    vis_path = scope_path.with_name(scope_path.stem + "_vis.jpg")
    uv = load_gray(scope_path)
    # 1600 px keeps the phone photo's scale ~2.5x the scope's over the shared patch; sift copes
    vis = load_gray(vis_path, max_side=1600)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    # the scope frame is soft and small: upscale 2x and unsharp-mask so orb has corners to bite on.
    # sift gave under 10 inliers on this material, orb with a loose ratio gives ~50.
    uv_e = cv2.resize(clahe.apply(uv), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    uv_e = cv2.addWeighted(uv_e, 1.6, cv2.GaussianBlur(uv_e, (0, 0), 3), -0.6, 0)
    vis_e = clahe.apply(vis)

    orb = cv2.ORB_create(nfeatures=8000)
    k1, d1 = orb.detectAndCompute(uv_e, None)
    k2, d2 = orb.detectAndCompute(vis_e, None)
    raw = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(d1, d2, k=2)
    good = [p[0] for p in raw if len(p) == 2 and p[0].distance < 0.82 * p[1].distance]
    print(f"features uv={len(k1)} vis={len(k2)} ratio-test matches={len(good)}")
    H, inl, how = None, 0, "features"
    if len(good) >= 12:
        src = np.float32([k1[m.queryIdx].pt for m in good]) / 2.0
        dst = np.float32([k2[m.trainIdx].pt for m in good])
        H, mask = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 5.0)
        inl = int(mask.sum()) if mask is not None else 0
    print(f"homography inliers={inl}/{len(good)}")
    if inl < 20:
        # rigid rig: footprint size and orientation are fixed (A from the calibration homography),
        # only its centre moves, along the baseline direction by f*B/Z. so the search is one
        # dimensional in subject distance Z, with a small window for slop, and Z falls out for free
        import json
        cal = json.load(open(Path(__file__).with_name("rig_calib.json")))
        A = np.array(cal["A"]); uvc = np.array(cal["uv_center"]); imc = np.array(cal["img_center"])
        d = np.array(cal["parallax_dir"]); k = cal["parallax_px_cm"]
        def gradmag(img, s_norm=15):
            f = img.astype(np.float32); mu = cv2.GaussianBlur(f, (0, 0), s_norm)
            sd = np.sqrt(np.maximum(cv2.GaussianBlur((f - mu) ** 2, (0, 0), s_norm), 1e-3))
            n = cv2.GaussianBlur((f - mu) / sd, (0, 0), 1.5)
            gx = cv2.Sobel(n, cv2.CV_32F, 1, 0); gy = cv2.Sobel(n, cv2.CV_32F, 0, 1)
            return cv2.GaussianBlur(np.sqrt(gx * gx + gy * gy), (0, 0), 2.5).astype(np.float32)
        g_vis, g_uv = gradmag(vis), gradmag(uv)
        # template of the uv gradient at the fixed footprint scale, origin at its own top-left
        wt = int(round(np.hypot(*A[:, 0]) * uv.shape[1])); ht = int(round(np.hypot(*A[:, 1]) * uv.shape[0]))
        Hs = np.array([[A[0, 0], A[0, 1], 0], [A[1, 0], A[1, 1], 0], [0, 0, 1]], dtype=np.float64)
        corners = cv2.perspectiveTransform(np.float32([[[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]]]]), Hs)[0]
        shift = -corners.min(axis=0)
        Hs[:2, 2] = shift
        tw, th = int(np.ceil((corners.max(axis=0) - corners.min(axis=0))[0])), int(np.ceil((corners.max(axis=0) - corners.min(axis=0))[1]))
        t = cv2.warpPerspective(g_uv, Hs, (tw, th))
        tmask = cv2.warpPerspective(np.ones_like(g_uv), Hs, (tw, th)) > 0.5
        t = np.where(tmask, t, 0).astype(np.float32)
        PAD = 500
        g_vis_p = cv2.copyMakeBorder(g_vis, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=0)
        r = cv2.matchTemplate(g_vis_p, t, cv2.TM_CCOEFF_NORMED)
        # centre of the template in template coords
        tc = (A @ uvc) + shift
        best = None
        WIN = 25
        for Z in np.geomspace(10, 100, 80):
            c = imc + d * (k / Z)                       # predicted footprint centre in photo coords
            tl = c - tc + PAD                            # template top-left in padded coords
            x0, y0 = int(round(tl[0])), int(round(tl[1]))
            xs, xe = max(x0 - WIN, 0), min(x0 + WIN + 1, r.shape[1])
            ys, ye = max(y0 - WIN, 0), min(y0 + WIN + 1, r.shape[0])
            if xs >= xe or ys >= ye:
                continue
            sub = r[ys:ye, xs:xe]
            # require most of the template to overlap the photo
            ox = min(x0 + tw, PAD + vis.shape[1]) - max(x0, PAD); oy = min(y0 + th, PAD + vis.shape[0]) - max(y0, PAD)
            if ox <= 0 or oy <= 0 or ox * oy < 0.5 * tw * th:
                continue
            i = int(np.argmax(sub)); mx = float(sub.ravel()[i])
            ly, lx = divmod(i, sub.shape[1])
            if best is None or mx > best[0]:
                best = (mx, Z, xs + lx - PAD, ys + ly - PAD)
        score, Z, x, y = best
        H = np.array([[A[0, 0], A[0, 1], x + shift[0]], [A[1, 0], A[1, 1], y + shift[1]], [0, 0, 1]], dtype=np.float64)
        how = f"geom Z={Z:.0f}cm score={score:.3f}"
        print(how)
        try:
            warp0 = np.linalg.inv(H).astype(np.float32)
            crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-6)
            cc, warp = cv2.findTransformECC(g_vis, g_uv, warp0, cv2.MOTION_HOMOGRAPHY, crit, None, 3)
            H2 = np.linalg.inv(warp.astype(np.float64))
            c0 = cv2.perspectiveTransform(np.float32([[[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]]]]), H)[0]
            c1 = cv2.perspectiveTransform(np.float32([[[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]]]]), H2)[0]
            if np.abs(c1 - c0).max() < 0.08 * tw:
                H, how = H2, how + f" +ecc cc={cc:.3f}"
            else:
                print("ecc drifted, keeping geometric result")
        except cv2.error:
            print("ecc refinement failed, keeping geometric result")

    # where the scope frame lands on the photo
    h, w = uv.shape
    corners = cv2.perspectiveTransform(np.float32([[[0, 0], [w, 0], [w, h], [0, h]]]), H)[0]
    x0, y0 = np.floor(corners.min(axis=0)).astype(int)
    x1, y1 = np.ceil(corners.max(axis=0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, vis.shape[1]), min(y1, vis.shape[0])
    print(f"scope footprint on photo: x {x0}..{x1}, y {y0}..{y1} of {vis.shape[1]}x{vis.shape[0]}")

    # warp uv into photo space, crop both to the footprint
    uv_w = cv2.warpPerspective(uv, H, (vis.shape[1], vis.shape[0]), flags=cv2.INTER_LINEAR)
    valid = cv2.warpPerspective(np.full_like(uv, 255), H, (vis.shape[1], vis.shape[0])) > 0
    uv_c, vis_c, valid_c = uv_w[y0:y1, x0:x1], vis[y0:y1, x0:x1], valid[y0:y1, x0:x1]

    # local normalisation: divide out the lamp's illumination gradient on the uv side and the
    # room light on the photo side, so only reflectance structure is left to compare
    def local_norm(img, sigma=35):
        f = img.astype(np.float32)
        mu = cv2.GaussianBlur(f, (0, 0), sigma)
        sd = np.sqrt(np.maximum(cv2.GaussianBlur((f - mu) ** 2, (0, 0), sigma), 1e-3))
        return (f - mu) / sd
    m = valid_c
    # blur the sharp photo down to the scope's real resolution first, else edge grain dominates
    vis_soft = cv2.GaussianBlur(vis_c.astype(np.float32), (0, 0), 2.0)
    uv_n = local_norm(uv_c)
    vis_n = local_norm(vis_soft)
    d = uv_n - vis_n
    d[~m] = 0
    # signed difference: uv relatively brighter -> cyan, uv relatively darker -> red
    diff = np.full((*d.shape, 3), 128, np.uint8)
    gain = 40.0
    pos = np.clip(d * gain, 0, 127)
    neg = np.clip(-d * gain, 0, 127)
    diff[..., 0] = np.clip(128 + pos - neg, 0, 255)
    diff[..., 1] = np.clip(128 + pos - neg, 0, 255)
    diff[..., 2] = np.clip(128 - pos + neg, 0, 255)
    diff[~m] = 0
    strong = np.abs(d[m]) > 1.5
    print(f"normalised difference: std {d[m].std():.2f}, |d|>1.5 sigma on {strong.mean()*100:.1f}% of pixels")
    # for the overlay, a display version of uv matched to the photo's mean/std
    uv_f = uv_c.astype(np.float32); vis_f = vis_c.astype(np.float32)
    uv_n = np.clip((uv_f - uv_f[m].mean()) / (uv_f[m].std() + 1e-6) * vis_f[m].std() + vis_f[m].mean(), 0, 255)

    # overlay: photo in grey, uv in the red channel
    over = cv2.merge([vis_c, vis_c, np.where(m, uv_n.astype(np.uint8), vis_c)])
    out = scope_path.parent
    cv2.imwrite(str(out / f"{stamp}_overlay.jpg"), over, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(out / f"{stamp}_diff.jpg"), diff, [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(out / f"{stamp}_uv_warped.jpg"), uv_n.astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    cv2.imwrite(str(out / f"{stamp}_vis_crop.jpg"), vis_c, [cv2.IMWRITE_JPEG_QUALITY, 92])
    np.save(str(out / f"{stamp}_H.npy"), H)
    print(f"STATUS ok ({how}): wrote {stamp}_{{overlay,diff,uv_warped,vis_crop}}.jpg and _H.npy")
    return H


if __name__ == "__main__":
    fb = np.load(sys.argv[2]) if len(sys.argv) > 2 else None
    main(sys.argv[1], fb)
