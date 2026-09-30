#!/usr/bin/env python3
# signed uv-vs-visible difference inside a registered footprint. usage: diff_inset.py uv.mp4 vis.mp4 H.npy out_prefix [t1,t2,...]
import cv2, numpy as np, sys, subprocess
uvp, visp, Hp, out = sys.argv[1:5]; H = np.load(Hp); stills = [float(t) for t in sys.argv[5].split(',')] if len(sys.argv) > 5 else []
a = cv2.VideoCapture(uvp); b = cv2.VideoCapture(visp); fps = a.get(cv2.CAP_PROP_FPS); n = int(min(a.get(7), b.get(7)))
W, Hh = int(b.get(3)), int(b.get(4)); mask = cv2.warpPerspective(np.full((int(a.get(4)), int(a.get(3))), 255, np.uint8), H, (W, Hh)) > 128
mask = cv2.erode(mask.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
def diff(fu, fv):
    g = cv2.cvtColor(fu, cv2.COLOR_BGR2GRAY).astype(np.float32); w = cv2.warpPerspective(g, H, (W, Hh))
    v = fv[:, :, 0].astype(np.float32)  # blue channel: closest band to uv
    w = cv2.GaussianBlur(w, (0, 0), 3); v = cv2.GaussianBlur(v, (0, 0), 3)
    x = w[mask]; y = v[mask]; sel = np.random.default_rng(0).choice(len(x), min(20000, len(x)), replace=False)
    A = np.vstack([x[sel], np.ones_like(x[sel])]).T; coef = np.linalg.lstsq(A, y[sel], rcond=None)[0]
    for _ in range(3):  # robust refit: drop the largest residuals (that is the signal we want to keep out of the fit)
        r = np.abs(A @ coef - y[sel]); keep = r < np.percentile(r, 70); coef = np.linalg.lstsq(A[keep], y[sel][keep], rcond=None)[0]
    pred = w * coef[0] + coef[1]; d = np.zeros((Hh, W), np.float32); d[mask] = (pred - v)[mask]     # + : uv brighter than visible predicts
    return d, w, v
def render(fv, d, gain=3.0):
    dc = np.clip(d * gain, -255, 255); rgb = fv.copy().astype(np.float32)
    pos = np.clip(dc, 0, 255)[..., None] * np.array([0, 0.3, 1.0]); neg = np.clip(-dc, 0, 255)[..., None] * np.array([1.0, 0.4, 0])
    o = rgb * 0.55 + pos + neg; o[~mask] = rgb[~mask]; o = np.clip(o, 0, 255).astype(np.uint8)
    cv2.putText(o, 'uv - visible (blue ch), matched on the footprint: red = uv brighter, blue = uv darker', (10, Hh - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA); return o
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{Hh}', '-r', str(int(round(fps))), '-i', '-', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', out + '_diff.mp4'], stdin=subprocess.PIPE)
want = {int(round(t * fps)): t for t in stills}
for i in range(n):
    ok1, fu = a.read(); ok2, fv = b.read()
    if not (ok1 and ok2): break
    d, w, v = diff(fu, fv); o = render(fv, d); p.stdin.write(o.tobytes())
    if i in want:
        t = want[i]; x0, y0, x1, y1 = np.where(mask.any(0))[0][[0, -1]][0], np.where(mask.any(1))[0][[0, -1]][0], np.where(mask.any(0))[0][[0, -1]][1], np.where(mask.any(1))[0][[0, -1]][1]
        crop = lambda im: im[y0:y1, x0:x1]; g3 = lambda im: cv2.cvtColor(np.clip(im, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        dm = np.zeros_like(d); dm[mask] = d[mask]; heat = cv2.applyColorMap(np.clip(dm * 3 + 128, 0, 255).astype(np.uint8), cv2.COLORMAP_JET); heat[~mask] = 0
        panel = np.hstack([crop(fv), g3(crop(w)), g3(crop(v)), crop(heat)])
        for k, lab in enumerate(['phone', 'uv warped', 'phone blue', 'uv - blue (jet, +-40)']): cv2.putText(panel, lab, (k * (x1 - x0) + 8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(f'{out}_diff_{t:.0f}s.jpg', panel, [cv2.IMWRITE_JPEG_QUALITY, 90]); cv2.imwrite(f'{out}_diffoverlay_{t:.0f}s.jpg', o, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"t={t}: diff inside footprint: p5 {np.percentile(d[mask],5):.1f} p50 {np.percentile(d[mask],50):.1f} p95 {np.percentile(d[mask],95):.1f}")
p.stdin.close(); p.wait(); print('frames', n)
