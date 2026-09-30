"""register one uv video frame onto its paired phone video frame with the rig model.

the rig is rigid, so between shots only two things change: the phone's video-mode scale
(sensor crop + stabilisation, unknown but constant per mode) and the subject distance Z,
which slides the footprint along the baseline. sweep scale x translation on gradient
magnitude, polish with ecc, report the implied Z.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

cal = json.load(open(Path(__file__).with_name("rig_calib.json")))
A = np.array(cal["A"])                      # scope-landscape -> photo-portrait, ~no rotation
sx, sy = np.hypot(*A[:, 0]), np.hypot(*A[:, 1])   # 1.238, 1.335 at the photo working scale

def gradmag(img, s=12):
    f = img.astype(np.float32); mu = cv2.GaussianBlur(f, (0, 0), s)
    sd = np.sqrt(np.maximum(cv2.GaussianBlur((f - mu) ** 2, (0, 0), s), 1e-3))
    n = cv2.GaussianBlur((f - mu) / sd, (0, 0), 1.2)
    gx = cv2.Sobel(n, cv2.CV_32F, 1, 0); gy = cv2.Sobel(n, cv2.CV_32F, 0, 1)
    return cv2.GaussianBlur(np.sqrt(gx * gx + gy * gy), (0, 0), 2.0).astype(np.float32)

uv = cv2.imread(sys.argv[1], 0); vis = cv2.imread(sys.argv[2], 0)
g_uv, g_vis = gradmag(uv), gradmag(vis)
PAD = 400
g_vis_p = cv2.copyMakeBorder(g_vis, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=0)
best = None
# uv frame here is upright portrait (480x640): its 640 axis is the scope's long axis, which maps
# with factor sx*s onto the phone's short axis; the 480 axis with sy*s onto the long axis
for s in np.linspace(0.45, 0.85, 21):
    wt, ht = int(round(uv.shape[1] * sy * s)), int(round(uv.shape[0] * sx * s))
    if wt >= vis.shape[1] or ht >= vis.shape[0]: continue
    t = cv2.resize(g_uv, (wt, ht), interpolation=cv2.INTER_AREA)
    r = cv2.matchTemplate(g_vis_p, t, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.mgrid[0:r.shape[0], 0:r.shape[1]]
    ox = np.clip(np.minimum(xs + wt, PAD + vis.shape[1]) - np.maximum(xs, PAD), 0, None)
    oy = np.clip(np.minimum(ys + ht, PAD + vis.shape[0]) - np.maximum(ys, PAD), 0, None)
    r = np.where(ox * oy >= 0.6 * wt * ht, r, -1.0)
    # rig prior: phone in landscape puts the scope's baseline along the phone's long axis, so
    # the footprint is vertically centred and only slides in x with distance
    yc = PAD + (vis.shape[0] - ht) / 2
    r = np.where(np.abs(ys - yc) <= 40, r, -1.0)
    i = int(np.argmax(r)); mx = float(r.ravel()[i])
    if best is None or mx > best[0]:
        best = (mx, s, wt, ht, int(xs.ravel()[i]) - PAD, int(ys.ravel()[i]) - PAD)
score, s, wt, ht, x, y = best
H = np.array([[wt / uv.shape[1], 0, x], [0, ht / uv.shape[0], y], [0, 0, 1]], dtype=np.float64)
how = f"scale {s:.2f} (footprint {wt}x{ht}) score {score:.3f}"
try:
    warp0 = np.linalg.inv(H).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-6)
    cc, warp = cv2.findTransformECC(g_vis, g_uv, warp0, cv2.MOTION_HOMOGRAPHY, crit, None, 3)
    H2 = np.linalg.inv(warp.astype(np.float64))
    c0 = cv2.perspectiveTransform(np.float32([[[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]]]]), H)[0]
    c1 = cv2.perspectiveTransform(np.float32([[[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]]]]), H2)[0]
    if np.abs(c1 - c0).max() < 0.08 * wt: H, how = H2, how + f" +ecc cc={cc:.3f}"
except cv2.error: pass
c = cv2.perspectiveTransform(np.float32([[[uv.shape[1] / 2, uv.shape[0] / 2]]]), H)[0][0]
off = c - np.array([vis.shape[1] / 2, vis.shape[0] / 2])
# phone main cam: 5.11 mm on a 7.6 mm-wide sensor; the 1280-px video axis spans the sensor's
# long side if there is no crop, so f ~ 861 px. baseline 14 cm.
f_px = 5.11 / 7.6 * 1280
Z = f_px * cal["baseline_cm"] / max(np.linalg.norm(off), 1)
print(f"{how}; footprint centre offset from image centre {off.round()} px -> implied Z ~ {Z:.0f} cm (no-crop assumption)")
uv_w = cv2.warpPerspective(uv, H, (vis.shape[1], vis.shape[0]))
m = cv2.warpPerspective(np.full_like(uv, 255), H, (vis.shape[1], vis.shape[0])) > 0
uvf = uv_w.astype(np.float32); vf = vis.astype(np.float32)
uvn = np.clip((uvf - uvf[m].mean()) / (uvf[m].std() + 1e-6) * vf[m].std() + vf[m].mean(), 0, 255).astype(np.uint8)
over = cv2.merge([vis, vis, np.where(m, uvn, vis)])
cv2.rectangle(over, tuple(np.int32(cv2.perspectiveTransform(np.float32([[[0, 0]]]), H)[0][0])), tuple(np.int32(cv2.perspectiveTransform(np.float32([[[uv.shape[1], uv.shape[0]]]]), H)[0][0])), (0, 255, 255), 2)
out = Path(sys.argv[1]).with_name(Path(sys.argv[1]).stem + "_overlay.jpg")
cv2.imwrite(str(out), over, [cv2.IMWRITE_JPEG_QUALITY, 92])
np.save(str(out.with_suffix(".H.npy")), H)
print("wrote", out.name)
