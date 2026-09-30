#!/usr/bin/env python3
# apply rig_calib_v2.json to a video-mode pair: search plane distance Z (and phone video fov factor s) for one frame.
# usage: rig_apply.py uv.png vis.png [x0 y0 x1 y1 of the subject box in the phone frame]
import cv2, numpy as np, sys, json, os
c = json.load(open(os.environ.get('UVCAM_CALIB', 'rig_calib_v2.json')))   # rig calibration from tools/calib/calib_rig.py
K_s = np.array(c['K_scope']); R = np.array(c['R_phone_to_scope']); t = np.array(c['t_phone_to_scope_mm']); M = np.array(c['mirror_saved_uv'], float)
K_p = np.array(c['K_phone']); k1, k2 = c['dist_scope']
uv = cv2.imread(sys.argv[1], 0)
UVK = int(os.environ.get('UVK', '0')); uv = np.rot90(uv, UVK % 4); uv = np.ascontiguousarray(uv[:, ::-1] if UVK >= 4 else uv)  # pre-transform into the photo-mode convention
vis = cv2.imread(sys.argv[2], 0); Hv, Wv = vis.shape
box = [int(v) for v in sys.argv[3:7]] if len(sys.argv) >= 7 else [0, 0, Wv, Hv]
def K_video(s):  # same sensor centre, photo fov scaled to the video width, times a fov factor s (1 = identical hfov)
    sc = Wv / 4032.0; K = K_p.copy(); K[0, 0] *= sc * s; K[1, 1] *= sc * s; K[0, 2] = Wv / 2; K[1, 2] = Hv / 2; return K
def H_uv_to_vis(Z_cm, s):
    Hs = M @ K_s @ (R + np.outer(t, [0, 0, 1.0]) / (Z_cm * 10)) @ np.linalg.inv(K_video(s)); return np.linalg.inv(Hs)
# undistort the scope frame once (in un-mirrored coords, then re-mirror) so the pinhole homography applies
uvu = cv2.undistort(uv[:, ::-1], K_s, np.array([k1, k2, 0, 0]))[:, ::-1]
def grad(g): gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1); return cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 1.5)
gv = grad(vis)
def score(Z, s):
    H = H_uv_to_vis(Z, s); w = cv2.warpPerspective(uvu, H, (Wv, Hv)); m = cv2.warpPerspective(np.full(uv.shape, 255, np.uint8), H, (Wv, Hv)) > 128
    m[:box[1]] = False; m[box[3]:] = False; m[:, :box[0]] = False; m[:, box[2]:] = False
    if m.sum() < 5000: return -1
    a = grad(w)[m]; b = gv[m]; a = a - a.mean(); b = b - b.mean(); return float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
best = max(((score(Z, s), Z, s) for Z in np.arange(20, 150, 2.0) for s in np.arange(0.8, 1.7, 0.02)), key=lambda x: x[0])
print(f"UVK={UVK} best ncc {best[0]:.3f} at Z={best[1]:.0f} cm, fov factor s={best[2]:.2f}")
for s in (1.0, 1.2, 1.3, 1.4, 1.5):
    zs = [(score(Z, s), Z) for Z in np.arange(20, 150, 2.0)]; sc, Z = max(zs); print(f"  s={s:.2f}: best Z={Z:.0f} ncc {sc:.3f}")
sc, Z, s = best; H = H_uv_to_vis(Z, s); w = cv2.warpPerspective(uvu, H, (Wv, Hv)); m = w > 0
ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR); ov[m] = (0.5 * ov[m] + 0.5 * np.stack([w[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = w[m]
cv2.rectangle(ov, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
out = os.path.splitext(sys.argv[1])[0]; cv2.imwrite(out + '_rigfit_overlay.jpg', ov); np.save(out + '_H.npy', H)
json.dump(dict(Z_cm=float(Z), s=float(s), ncc=float(sc), H=H.tolist()), open(out + '_rigfit.json', 'w'), indent=1)
# what the upright uv looks like on its own: warp through the pure-rotation part (Z -> inf) into a 480x640 canvas
Hinf = np.linalg.inv(M @ K_s @ R @ np.linalg.inv(K_video(s)))
print("uv->phone at infinity, 2x2 part:", np.round(Hinf[:2, :2] / abs(Hinf[:2, :2]).max(), 2).tolist())
