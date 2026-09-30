#!/usr/bin/env python3
# register one video-mode pair on a plane: model seeds (Z, crop factor s) -> ECC homography refinement in a box.
# usage: UVK=k rig_ecc.py uv.png vis.png x0 y0 x1 y1
import cv2, numpy as np, sys, json, os
from scipy.optimize import least_squares
c = json.load(open(os.environ.get('UVCAM_CALIB', 'rig_calib_v2.json')))   # rig calibration from tools/calib/calib_rig.py
K_s = np.array(c['K_scope']); R = np.array(c['R_phone_to_scope']); t = np.array(c['t_phone_to_scope_mm']); M = np.array(c['mirror_saved_uv'], float); K_p = np.array(c['K_phone']); k1, k2 = c['dist_scope']
uv = cv2.imread(sys.argv[1], 0); UVK = int(os.environ.get('UVK', '0')); uv = np.rot90(uv, UVK % 4); uv = np.ascontiguousarray(uv[:, ::-1] if UVK >= 4 else uv)
vis = cv2.imread(sys.argv[2], 0); Hv, Wv = vis.shape; box = [int(v) for v in sys.argv[3:7]]
uvu = cv2.undistort(uv[:, ::-1], K_s, np.array([k1, k2, 0, 0]))[:, ::-1]
def K_video(s): sc = Wv / 4032.0; K = K_p.copy(); K[0, 0] *= sc * s; K[1, 1] *= sc * s; K[0, 2] = Wv / 2; K[1, 2] = Hv / 2; return K
def H_model(Z, s): return np.linalg.inv(M @ K_s @ (R + np.outer(t, [0, 0, 1.0]) / (Z * 10)) @ np.linalg.inv(K_video(s)))
def grad(g): gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1); m = np.hypot(gx, gy); return cv2.GaussianBlur(m, (0, 0), 2) / (m.max() + 1e-6)
gu = grad(uvu); gv = grad(vis); mask = np.zeros(vis.shape, np.uint8); mask[box[1]:box[3], box[0]:box[2]] = 1
crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6); best = None
for s in (1.0, 1.15, 1.3, 1.45, 1.6):
    for Z in (35, 50, 70, 100, 150):
        W0 = H_model(Z, s).astype(np.float32); W0 /= W0[2, 2]
        try: cc, W = cv2.findTransformECC(gu, gv, W0.copy(), cv2.MOTION_HOMOGRAPHY, crit, mask, 5)   # W: uv px -> phone px, mask on the phone frame
        except cv2.error as e: print('  seed', Z, s, 'failed:', str(e).splitlines()[-1][:80]); continue
        if best is None or cc > best[0]: best = (cc, W, Z, s)
cc, W, Z0, s0 = best; print(f"best ecc {cc:.3f} from seed Z={Z0} s={s0}")
# back out (Z, s) from the refined H by corner transfer
pts = np.array([[0, 0], [uv.shape[1], 0], [uv.shape[1], uv.shape[0]], [0, uv.shape[0]], [uv.shape[1] / 2, uv.shape[0] / 2]], np.float32)
tgt = cv2.perspectiveTransform(pts[None], W.astype(np.float64))[0]
def res(x): return (cv2.perspectiveTransform(pts[None], H_model(x[0], x[1]))[0] - tgt).ravel()
sol = least_squares(res, [Z0, s0], bounds=([10, 0.5], [500, 2.5])); Zf, sf = sol.x; e = np.linalg.norm(res(sol.x).reshape(-1, 2), axis=1)
print(f"model fit to ECC result: Z={Zf:.1f} cm, crop factor s={sf:.3f}, corner mismatch rms {np.sqrt((e**2).mean()):.1f} px (model has no roll/tilt freedom)")
w = cv2.warpPerspective(uvu, W, (Wv, Hv)); m = w > 0; ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)
ov[m] = (0.5 * ov[m] + 0.5 * np.stack([w[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = w[m]; cv2.rectangle(ov, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
out = os.path.splitext(sys.argv[1])[0]; cv2.imwrite(out + '_ecc_overlay.jpg', ov); np.save(out + '_ecc_H.npy', W)
json.dump(dict(ecc=float(cc), H=W.tolist(), Z_cm=float(Zf), s=float(sf), UVK=UVK), open(out + '_ecc.json', 'w'), indent=1)
