#!/usr/bin/env python3
# rig bundle fit: phone = reference camera (K fixed), scope = K_s(f, cx, cy, k1) + [R|t]; board poses from the phone.
# saved uv frames are mirrored, so the model projects into un-mirrored coordinates u' = W-1-u.
# usage: calib_rig.py <dir>
import cv2, numpy as np, sys, os, json
from scipy.optimize import least_squares
D = sys.argv[1]; OUT = os.path.join(D, 'out'); W, Hh = 640, 480
F_PHONE = 4032 * 5.11 / 7.344; K_v = np.array([[F_PHONE, 0, 2016], [0, F_PHONE, 1512], [0, 0, 1]])
z = np.load(os.path.join(OUT, 'corr.npz')); stems = list(z['stems'])
pairs = []
for s in stems:
    ou = z[f'{s}_ou']; pu = z[f'{s}_pu'].copy(); pu[:, 0] = W - 1 - pu[:, 0]     # un-mirror
    R_b, _ = cv2.Rodrigues(z[f'{s}_rvec']); t_b = z[f'{s}_tvec']
    Xc = (R_b @ np.hstack([ou, np.zeros((len(ou), 1))]).T).T + t_b               # board points in the phone frame, mm
    pairs.append(dict(stem=s, Xc=Xc, pu=pu, Z=float(z[f'{s}_Z']), n=R_b[:, 2], t_b=t_b))
Xall = np.vstack([p['Xc'] for p in pairs]); Uall = np.vstack([p['pu'] for p in pairs]); idx = np.cumsum([0] + [len(p['pu']) for p in pairs])
def project(x, Xc):
    f, cx, cy, k1, k2 = x[:5]; R, _ = cv2.Rodrigues(x[5:8]); t = x[8:11]
    Xs = (R @ Xc.T).T + t; xn = Xs[:, :2] / Xs[:, 2:3]; r2 = (xn ** 2).sum(1, keepdims=True)
    xd = xn * (1 + k1 * r2 + k2 * r2 ** 2); return xd * f + [cx, cy]
def resid(x): return (project(x, Xall) - Uall).ravel()
# initial guess: scope looks along the phone axis, image transposed (sensor rotated 90 deg), sitting 140 mm off in-plane
best = None
for rz in (0, 90, 180, 270):
    for tx, ty in ((140, 0), (-140, 0), (0, 140), (0, -140)):
        rv = cv2.Rodrigues(cv2.Rodrigues(np.array([0, 0, np.radians(rz)]))[0])[0].ravel()
        x0 = np.array([860, 320, 240, 0, 0, *rv, tx, ty, 0.0])
        sol = least_squares(resid, x0, loss='soft_l1', f_scale=3.0, max_nfev=2000)
        if best is None or sol.cost < best.cost: best = sol
x = best.x; f, cx, cy, k1, k2 = x[:5]; R, _ = cv2.Rodrigues(x[5:8]); t = x[8:11]
res = resid(x).reshape(-1, 2); e = np.linalg.norm(res, axis=1)
print(f"scope: f={f:.1f} px  c=({cx:.1f},{cy:.1f})  k1={k1:.4f} k2={k2:.4f}   hfov={2*np.degrees(np.arctan(320/f)):.1f} deg")
print(f"scope position in phone frame (mm): {np.round(-R.T @ t, 1)}   (x right, y down, z forward, seen from the phone)")
ang = np.degrees(cv2.RQDecomp3x3(R)[0]); print(f"rotation phone->scope, euler xyz deg: {np.round(ang, 2)}")
print(f"overall rms {np.sqrt((e**2).mean()):.2f} uv px, median {np.median(e):.2f}, max {e.max():.1f}")
for i, p in enumerate(pairs):
    ei = e[idx[i]:idx[i+1]]; print(f"  {p['stem']} Z={p['Z']:5.1f} n={len(ei):3d} rms {np.sqrt((ei**2).mean()):.2f} px  max {ei.max():.1f}")
# leave-one-pair-out: how well does the rig predict a pair it never saw
print("leave-one-out (rms on the held-out pair):")
for i, p in enumerate(pairs):
    m = np.ones(len(Uall), bool); m[idx[i]:idx[i+1]] = False
    s = least_squares(lambda y: (project(y, Xall[m]) - Uall[m]).ravel(), x, loss='soft_l1', f_scale=3.0)
    ei = np.linalg.norm(project(s.x, p['Xc']) - p['pu'], axis=1); print(f"  {p['stem']} Z={p['Z']:5.1f} rms {np.sqrt((ei**2).mean()):.2f} px  max {ei.max():.1f}")
K_s = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]]); M = np.array([[-1, 0, W - 1], [0, 1, 0], [0, 0, 1.0]])   # un-mirrored -> saved uv px
def H_plane(n, d):
    """phone px -> saved uv px for the plane n.X = d (phone frame, mm). ignores scope distortion."""
    Hs = K_s @ (R + np.outer(t, n) / d) @ np.linalg.inv(K_v); return M @ Hs
def H_frontal(Z_cm): return H_plane(np.array([0, 0, 1.0]), Z_cm * 10)
json.dump(dict(K_scope=K_s.tolist(), dist_scope=[k1, k2], R_phone_to_scope=R.tolist(), t_phone_to_scope_mm=t.tolist(), K_phone=K_v.tolist(),
               mirror_saved_uv=[[-1, 0, W - 1], [0, 1, 0], [0, 0, 1]], rms_uv_px=float(np.sqrt((e**2).mean())),
               usage='H_phone_to_saved_uv(plane n,d in phone frame mm) = Mirror @ K_s @ (R + t n^T / d) @ inv(K_phone); fronto-parallel at Z cm: n=(0,0,1), d=10*Z. invert for uv->phone.',
               H_frontal_by_Z={str(zc): np.linalg.inv(H_frontal(zc)).tolist() for zc in (20, 30, 40, 50, 60, 80, 100, 150, 300)}),
          open(os.path.join(D, 'rig_calib_v2.json'), 'w'), indent=1)
# overlays with the rig model using each pair's true plane (uv warped into the phone frame)
import glob
from PIL import Image, ImageOps
for p in pairs:
    n = p['n']; d = float(n @ p['t_b']); Hup = np.linalg.inv(H_plane(n, d))
    uv = cv2.imread(os.path.join(D, p['stem'] + '.jpg'), 0); vis = np.array(ImageOps.exif_transpose(Image.open(os.path.join(D, p['stem'] + '_vis.jpg'))).convert('L'))
    warped = cv2.warpPerspective(uv, Hup, (vis.shape[1], vis.shape[0])); ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR); m = warped > 0
    ov[m] = (0.5 * ov[m] + 0.5 * np.stack([warped[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = warped[m]
    cv2.imwrite(os.path.join(OUT, f"{p['stem']}_rig_overlay.jpg"), cv2.resize(ov, None, fx=0.4, fy=0.4), [cv2.IMWRITE_JPEG_QUALITY, 85])
print("uv centre -> phone px, fronto-parallel plane:", {zc: cv2.perspectiveTransform(np.array([[[320, 240]]], np.float32), np.linalg.inv(H_frontal(zc)))[0][0].round(0).tolist() for zc in (30, 50, 100, 300)})
