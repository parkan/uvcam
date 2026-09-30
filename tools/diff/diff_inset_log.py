#!/usr/bin/env python3
# log-ratio uv/visible inside the registered footprint, gain-normalised on a reference region assumed uv-neutral.
# usage: diff_inset_log.py uv.mp4 vis.mp4 H.npy out_prefix "x0,y0,x1,y1" [t1,t2,...] [stops]
import cv2, numpy as np, sys, subprocess
uvp, visp, Hp, out, ref = sys.argv[1:6]; rx0, ry0, rx1, ry1 = [int(v) for v in ref.split(',')]
stills = [float(t) for t in sys.argv[6].split(',')] if len(sys.argv) > 6 and sys.argv[6] else []; STOPS = float(sys.argv[7]) if len(sys.argv) > 7 else 2.0
H = np.load(Hp); a = cv2.VideoCapture(uvp); b = cv2.VideoCapture(visp); fps = a.get(cv2.CAP_PROP_FPS); n = int(min(a.get(7), b.get(7)))
W, Hh = int(b.get(3)), int(b.get(4)); mask = cv2.warpPerspective(np.full((int(a.get(4)), int(a.get(3))), 255, np.uint8), H, (W, Hh)) > 128
mask = cv2.erode(mask.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0; refm = np.zeros_like(mask); refm[ry0:ry1, rx0:rx1] = True; refm &= mask
def logratio(fu, fv):
    g = cv2.cvtColor(fu, cv2.COLOR_BGR2GRAY).astype(np.float32); w = cv2.warpPerspective(g, H, (W, Hh)); v = fv[:, :, 0].astype(np.float32)
    w = cv2.GaussianBlur(w, (0, 0), 2) + 2; v = cv2.GaussianBlur(v, (0, 0), 2) + 2
    k = np.median(v[refm] / w[refm])                    # gain that makes the reference region uv-neutral
    r = np.zeros((Hh, W), np.float32); r[mask] = np.log2(k * w[mask] / v[mask]); return r, w, v, k
def colour(r):
    """diverging: violet/blue = uv darker than visible, yellow/orange = uv brighter; grey = neutral. clipped at +-STOPS."""
    t = np.clip(r / STOPS, -1, 1); c = np.zeros(r.shape + (3,), np.float32)
    pos = np.clip(t, 0, 1)[..., None]; neg = np.clip(-t, 0, 1)[..., None]
    c += pos * np.array([0, 190, 255]) + neg * np.array([255, 60, 120]) + (1 - pos - neg) * np.array([90, 90, 90])   # bgr
    return c
def render(fv, r):
    c = colour(r); base = fv.astype(np.float32); lum = cv2.cvtColor(fv, cv2.COLOR_BGR2GRAY).astype(np.float32)[..., None] / 255
    o = base.copy(); o[mask] = (c * (0.35 + 0.65 * lum))[mask]; o = np.clip(o, 0, 255).astype(np.uint8)
    cv2.rectangle(o, (rx0, ry0), (rx1, ry1), (200, 200, 200), 1)
    bar = colour(np.linspace(-STOPS, STOPS, 300)[None].repeat(18, 0)).astype(np.uint8); o[Hh - 40:Hh - 22, 20:320] = bar
    cv2.putText(o, f'log2(uv/blue), pot = neutral   -{STOPS:.0f} stops', (20, Hh - 46), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(o, f'+{STOPS:.0f}', (322, Hh - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA); return o
p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{Hh}', '-r', str(int(round(fps))), '-i', '-', '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', out + '_logdiff.mp4'], stdin=subprocess.PIPE)
want = {int(round(t * fps)): t for t in stills}
for i in range(n):
    ok1, fu = a.read(); ok2, fv = b.read()
    if not (ok1 and ok2): break
    r, w, v, k = logratio(fu, fv); o = render(fv, r); p.stdin.write(o.tobytes())
    if i in want:
        t = want[i]; ys, xs = np.where(mask); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max(); crop = lambda im: im[y0:y1, x0:x1]
        g3 = lambda im: cv2.cvtColor(np.clip(im, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        panel = np.hstack([crop(fv), g3(crop(np.clip(w * k, 0, 255))), g3(crop(v)), crop(o)])
        for j, lab in enumerate(['phone', 'uv (gain-matched on pot)', 'phone blue', 'log2 ratio']): cv2.putText(panel, lab, (j * (x1 - x0) + 8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(f'{out}_logdiff_{t:.0f}s.jpg', panel, [cv2.IMWRITE_JPEG_QUALITY, 90])
        print(f"t={t}: gain {k:.2f}; log2 ratio p5 {np.percentile(r[mask],5):.2f} p50 {np.percentile(r[mask],50):.2f} p95 {np.percentile(r[mask],95):.2f} stops")
p.stdin.close(); p.wait(); print('frames', n)
