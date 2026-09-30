#!/usr/bin/env python3
# plane homography from hand-read anchors (upright uv -> phone): similarity least squares, then ECC polish in a box.
# usage: anchor_plane.py uv_upright.png vis.png "ux,uy,px,py;..." x0 y0 x1 y1 out_prefix
import cv2, numpy as np, sys, json
uv = cv2.imread(sys.argv[1], 0); vis = cv2.imread(sys.argv[2], 0)
anch = np.array([[float(x) for x in a.split(',')] for a in sys.argv[3].split(';')], np.float32); x0, y0, x1, y1 = [int(v) for v in sys.argv[4:8]]; out = sys.argv[8]
S, inl = cv2.estimateAffinePartial2D(np.ascontiguousarray(anch[:, :2]).reshape(-1, 1, 2), np.ascontiguousarray(anch[:, 2:]).reshape(-1, 1, 2), method=cv2.LMEDS); H0 = np.vstack([S, [0, 0, 1]]).astype(np.float32)
e = np.linalg.norm(cv2.transform(anch[None, :, :2], S)[0] - anch[:, 2:], axis=1)
print(f"similarity: scale {np.hypot(S[0,0], S[0,1]):.3f} rot {np.degrees(np.arctan2(S[1,0], S[0,0])):.1f} deg, anchor residuals {np.round(e,1).tolist()} px")
def grad(g): gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1); m = np.hypot(gx, gy); m = cv2.GaussianBlur(m, (0, 0), 1.5); return m / m.max()
mask = np.zeros(vis.shape, np.uint8); mask[y0:y1, x0:x1] = 1; crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6)
H = H0.copy(); cc = -1
try: cc, H = cv2.findTransformECC(grad(uv), grad(vis), H0.copy(), cv2.MOTION_HOMOGRAPHY, crit, mask, 5)
except cv2.error as err: print("ecc failed:", str(err).splitlines()[-1][:60])
e2 = np.linalg.norm(cv2.perspectiveTransform(anch[None, :, :2], H.astype(np.float64))[0] - anch[:, 2:], axis=1)
print(f"ecc {cc:.3f}; anchors after polish {np.round(e2,1).tolist()} px")
if cc < 0 or e2.max() > 3 * max(e.max(), 4): print("polish drifted from the anchors -> keeping the similarity"); H = H0
w = cv2.warpPerspective(uv, H, (vis.shape[1], vis.shape[0])); m = w > 0; ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
ov[m] = (0.5 * ov[m] + 0.5 * np.stack([w[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = w[m]
for a in anch: cv2.circle(ov, (int(a[2]), int(a[3])), 6, (0, 255, 0), 2)
cv2.imwrite(out + '_overlay.jpg', cv2.resize(ov, (1000, int(1000 * vis.shape[0] / vis.shape[1])))); np.save(out + '_H.npy', H)
json.dump(dict(H=np.asarray(H).tolist(), ecc=float(cc), anchors=anch.tolist()), open(out + '.json', 'w'), indent=1)
