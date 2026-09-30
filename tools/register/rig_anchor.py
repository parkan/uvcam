#!/usr/bin/env python3
# solve (Z, video scale s) of the rig model from a few hand-read anchors on one plane. anchors are given in
# UPRIGHT uv coords (as made by: up = rot90(rot90(raw,2).T, 2)) and raw phone video px. usage: rig_anchor.py out_prefix "ux,uy,px,py;..."
import cv2, numpy as np, sys, json, os
from scipy.optimize import least_squares
c = json.load(open(os.environ.get('UVCAM_CALIB', 'rig_calib_v2.json')))   # rig calibration from tools/calib/calib_rig.py
K_s = np.array(c['K_scope']); R = np.array(c['R_phone_to_scope']); t = np.array(c['t_phone_to_scope_mm']); M = np.array(c['mirror_saved_uv'], float); K_p = np.array(c['K_phone'])
Wv, Hv = 1280, 720
# upright (X,Y) -> raw video (u,v) -> photo convention (UVK=2: rot180) (u2,v2). derive numerically from index images.
iu, iv = np.meshgrid(np.arange(640), np.arange(480)); raw_u = iu.astype(np.float32); raw_v = iv.astype(np.float32)
def upright(a): return np.ascontiguousarray(np.rot90(np.rot90(a, 2).T, 2))
U = upright(raw_u); V = upright(raw_v)   # U[Y,X] = raw u of that upright pixel
def up_to_photo(X, Y):
    u, v = U[int(round(Y)), int(round(X))], V[int(round(Y)), int(round(X))]; return np.array([639 - u, 479 - v])   # rot180 = UVK 2
anch = [[float(x) for x in a.split(',')] for a in sys.argv[2].split(';')]
pu = np.array([up_to_photo(a[0], a[1]) for a in anch], np.float32); pv = np.array([a[2:4] for a in anch], np.float32)
def K_video(s): sc = Wv / 4032.0; K = K_p.copy(); K[0, 0] *= sc * s; K[1, 1] *= sc * s; K[0, 2] = Wv / 2; K[1, 2] = Hv / 2; return K
def H_model(Z, s): return np.linalg.inv(M @ K_s @ (R + np.outer(t, [0, 0, 1.0]) / (Z * 10)) @ np.linalg.inv(K_video(s)))
def res(x): return (cv2.perspectiveTransform(pu[None], H_model(x[0], x[1]))[0] - pv).ravel()
best = min((least_squares(res, [z0, s0], bounds=([10, 0.3], [500, 3])) for z0 in (30, 60, 100) for s0 in (0.8, 1.0, 1.3)), key=lambda r: r.cost)
Z, s = best.x; e = np.linalg.norm(res(best.x).reshape(-1, 2), axis=1)
print(f"Z = {Z:.1f} cm, video scale s = {s:.3f} (1 = photo hfov); anchor residuals {np.round(e, 1).tolist()} px")
H = H_model(Z, s); np.save(sys.argv[1] + '_H_photoconv.npy', H)
# also the homography from the UPRIGHT uv frame (what the clips use): upright -> photo conv is an affine map, fit it exactly
src = np.array([[0, 0], [479, 0], [0, 639], [479, 639]], np.float32); dst = np.array([up_to_photo(x, y) for x, y in src], np.float32)
A = cv2.getPerspectiveTransform(src, dst); Hup = H @ A; np.save(sys.argv[1] + '_H_upright.npy', Hup)
json.dump(dict(Z_cm=float(Z), s=float(s), H_upright_to_phone=Hup.tolist(), H_photoconv_to_phone=H.tolist()), open(sys.argv[1] + '_anchor.json', 'w'), indent=1)
print("upright uv -> phone H:\n", np.round(Hup / Hup[2, 2], 4))
