#!/usr/bin/env python3
# find the uv->phone homography for one plane from a static frame pair: template search (scale, shift) over the
# phone box on gradient magnitude, then ECC homography polish. usage: plane_fit.py uv_upright.png vis.png x0 y0 x1 y1
import cv2, numpy as np, sys, json, os
uv = cv2.imread(sys.argv[1], 0); vis = cv2.imread(sys.argv[2], 0); x0, y0, x1, y1 = [int(v) for v in sys.argv[3:7]]
def grad(g): gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1); m = np.hypot(gx, gy); return cv2.GaussianBlur(m, (0, 0), 1.5)
gu = grad(uv); gv = grad(vis); tpl_full = gv[y0:y1, x0:x1]
best = None
for s in np.arange(0.80, 1.30, 0.01):     # phone px per uv px; template scaled by 1/s to uv scale
    tpl = cv2.resize(tpl_full, None, fx=1 / s, fy=1 / s, interpolation=cv2.INTER_AREA)
    if tpl.shape[0] >= gu.shape[0] or tpl.shape[1] >= gu.shape[1]: continue
    r = cv2.matchTemplate(gu, tpl, cv2.TM_CCOEFF_NORMED); _, mx, _, loc = cv2.minMaxLoc(r)
    if best is None or mx > best[0]: best = (mx, s, loc)
mx, s, (ux, uy) = best; print(f"template: ncc {mx:.3f} scale {s:.2f} phone px/uv px, phone box top-left at uv ({ux},{uy})")
# similarity uv->phone: phone = s*(uv - [ux,uy]) + [x0,y0]
H0 = np.array([[s, 0, x0 - s * ux], [0, s, y0 - s * uy], [0, 0, 1]], np.float32)
mask = np.zeros(vis.shape, np.uint8); mask[y0:y1, x0:x1] = 1
crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6)
gun = gu / gu.max(); gvn = gv / gv.max()
try:
    cc, H = cv2.findTransformECC(gun, gvn, H0.copy(), cv2.MOTION_HOMOGRAPHY, crit, mask, 5); print(f"ecc polish: {cc:.3f}")
except cv2.error as e:
    print("ecc failed, keeping the similarity:", str(e).splitlines()[-1][:60]); H = H0; cc = -1
w = cv2.warpPerspective(uv, H, (vis.shape[1], vis.shape[0])); m = w > 0; ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
ov[m] = (0.5 * ov[m] + 0.5 * np.stack([w[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = w[m]; cv2.rectangle(ov, (x0, y0), (x1, y1), (0, 255, 0), 2)
out = os.path.splitext(sys.argv[1])[0]; cv2.imwrite(out + '_plane_overlay.jpg', ov); np.save(out + '_plane_H.npy', H)
json.dump(dict(ncc=float(mx), ecc=float(cc), scale=float(s), H=np.asarray(H).tolist()), open(out + '_plane.json', 'w'), indent=1)
