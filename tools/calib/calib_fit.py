#!/usr/bin/env python3
# fit the scope->phone rig model from paired charuco shots. usage: calib_fit.py <dir>
# <dir>/pairs.txt: "SCOPE_<t> near|far|fid Z_tape_cm" per line.
# model: H(Z) = H_inf + T/Z maps saved uv px (640x480, as written by the app) to exif-upright phone px (4032x3024).
import cv2, numpy as np, sys, os, json
from PIL import Image, ImageOps
D = sys.argv[1]; OUT = os.path.join(D, 'out'); os.makedirs(OUT, exist_ok=True)
F_PHONE = 4032 * 5.11 / 7.344  # xperia 5 iv main lens: 5.11 mm on a 7.344 mm wide sensor (from the camera HAL) = 2805 px
dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
boards = {'near': cv2.aruco.CharucoBoard((8, 6), 32.0, 24.0, dic, np.arange(0, 24)),
          'far':  cv2.aruco.CharucoBoard((5, 3), 55.0, 41.25, dic, np.arange(24, 31))}
par = cv2.aruco.DetectorParameters(); par.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX; par.minMarkerPerimeterRate = 0.01
K_PHONE = np.array([[F_PHONE, 0, 2016], [0, F_PHONE, 1512], [0, 0, 1]], float)

def load_vis(p): return np.array(ImageOps.exif_transpose(Image.open(p)).convert('L'))
def board_points(board, gray, up=1.0):
    """charuco corners + marker corners with their board-plane mm coordinates. returns (img_pts Nx2, obj_pts Nx2, n_markers)"""
    g = gray if up == 1.0 else cv2.resize(gray, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    g = cv2.createCLAHE(2.0, (8, 8)).apply(g)
    cc, cids, mc, mids = cv2.aruco.CharucoDetector(board, detectorParams=par).detectBoard(g)
    img, obj = [], []
    if mids is not None:
        objm = board.getObjPoints(); idlist = list(board.getIds().ravel())
        for c, i in zip(mc, mids.ravel()):
            k = idlist.index(int(i)); img += list(c.reshape(-1, 2)); obj += list(objm[k][:, :2])
    if cids is not None:
        cb = board.getChessboardCorners()
        for c, i in zip(cc.reshape(-1, 2), cids.ravel()): img.append(c); obj.append(cb[int(i)][:2])
    n = 0 if mids is None else len(mids)
    return (np.array(img, np.float32) / up if img else np.zeros((0, 2), np.float32)), (np.array(obj, np.float32) if obj else np.zeros((0, 2), np.float32)), n

def uv_points_direct(board, uv):
    W = uv.shape[1]; best = (np.zeros((0, 2)), np.zeros((0, 2)), 0)
    for up in (1.0, 2.0, 3.0):
        p, o, n = board_points(board, np.ascontiguousarray(uv[:, ::-1]), up)   # saved uv is mirrored
        if len(p) > len(best[0]): best = (p, o, n)
    p = best[0].copy()
    if len(p): p[:, 0] = W - 1 - p[:, 0]
    return p, best[1], best[2]

def uv_points_rectified(board, uv, H_bu, mm_px=6.0):
    """rectify the uv frame to the board plane through a rough board->uv homography, decode there, map back."""
    w_mm, h_mm = board.getChessboardSize()[0] * board.getSquareLength(), board.getChessboardSize()[1] * board.getSquareLength()
    S = np.diag([1 / mm_px, 1 / mm_px, 1.0])          # rectified px -> mm
    Hr = H_bu @ S                                      # rectified px -> uv px
    size = (int(w_mm * mm_px), int(h_mm * mm_px))
    rect = cv2.warpPerspective(uv, np.linalg.inv(Hr), size, flags=cv2.INTER_CUBIC)
    p, o, n = board_points(board, rect, 1.0)
    if len(p) == 0:  # try the mirror in case the rough H had the wrong hand
        p, o, n = board_points(board, np.ascontiguousarray(rect[:, ::-1]), 1.0)
        if len(p): p[:, 0] = size[0] - 1 - p[:, 0]
    if len(p) == 0: return p, o, n, rect
    return cv2.perspectiveTransform(p[None], Hr)[0], o, n, rect

def solve_Z(obj_mm, img_px):
    obj3 = np.hstack([obj_mm, np.zeros((len(obj_mm), 1), np.float32)])
    ok, rvec, tvec = cv2.solvePnP(obj3, img_px, K_PHONE, None, flags=cv2.SOLVEPNP_IPPE)
    R, _ = cv2.Rodrigues(rvec); centre = np.array([obj_mm[:, 0].mean(), obj_mm[:, 1].mean(), 0.0])
    zc = (R @ centre + tvec.ravel())[2] / 10.0        # cm, board centre along the phone optical axis
    tilt = np.degrees(np.arccos(abs(R[2, 2])))
    return zc, tilt, rvec.ravel(), tvec.ravel()

def fit_model(rows):
    """lambda_i H_i = H_inf + T/Z_i with T only in the 3rd column (fronto-parallel plane, scope offset in the image plane)."""
    Hs = [np.array(r['H']) for r in rows]; Z = np.array([r['Z'] for r in rows]); lam = np.array([1 / h[2, 2] for h in Hs])
    for _ in range(50):
        # linear solve for H_inf (9) and t (3): rows of A * x = lam_i*H_i flattened
        A = np.zeros((9 * len(Hs), 12)); b = np.zeros(9 * len(Hs))
        for i, (h, z, l) in enumerate(zip(Hs, Z, lam)):
            for k in range(9):
                A[9 * i + k, k] = 1
                if k % 3 == 2: A[9 * i + k, 9 + k // 3] = 1 / z
                b[9 * i + k] = l * h.flat[k]
        x = np.linalg.lstsq(A, b, rcond=None)[0]; H_inf = x[:9].reshape(3, 3); T = np.zeros((3, 3)); T[:, 2] = x[9:]
        M = [H_inf + T / z for z in Z]
        lam = np.array([(h * m).sum() / (h * h).sum() for h, m in zip(Hs, M)])
        s = 1 / H_inf[2, 2]; H_inf *= s; T *= s; lam *= s   # fix the gauge
    return H_inf, T

def model_H(model, Z): return model[0] + model[1] / Z

rows, fids = [], []
lines = [l.split() for l in open(os.path.join(D, 'pairs.txt')) if l.strip() and not l.startswith('#')]
# pass 1: pairs where the uv decodes directly
pending = []
for stem, bname, ztape in lines:
    if bname == 'fid': fids.append((stem, float(ztape))); continue
    board = boards[bname]; uv = cv2.imread(os.path.join(D, stem + '.jpg'), 0); vis = load_vis(os.path.join(D, stem + '_vis.jpg'))
    pv, ov, nv = board_points(board, vis); Z, tilt, rvec, tvec = solve_Z(ov, pv)
    pu, ou, nu = uv_points_direct(board, uv)
    rec = dict(stem=stem, board=bname, Ztape=float(ztape), Z=float(Z), tilt=float(tilt), rvec=rvec, tvec=tvec, pv=pv, ov=ov, pu=pu, ou=ou, nu=nu, nv=nv, uv=uv, vis=vis)
    (rows if len(pu) >= 8 else pending).append(rec)

def finish(r):
    # correspondences by board coordinate (exact match of obj points), homography uv->vis
    key = lambda o: (round(float(o[0]), 2), round(float(o[1]), 2))
    dv = {key(o): p for o, p in zip(r['ov'], r['pv'])}
    pairs = [(p, dv[key(o)]) for o, p in zip(r['ou'], r['pu']) if key(o) in dv]
    pu = np.array([a for a, _ in pairs], np.float32); pv = np.array([b for _, b in pairs], np.float32)
    H, mask = cv2.findHomography(pu, pv, cv2.RANSAC, 8.0)
    proj = cv2.perspectiveTransform(pu[None], H)[0]; err = np.linalg.norm(proj - pv, axis=1)
    r.update(H=H.tolist(), n=len(pu), inl=int(mask.sum()), rms=float(np.sqrt((err ** 2).mean())), pu_m=pu, pv_m=pv)
    print(f"{r['stem']} {r['board']:4s} tape {r['Ztape']:4.0f} -> Z_phone {r['Z']:5.1f} cm tilt {r['tilt']:4.1f}deg | uv {r['nu']} markers {len(r['pu'])} pts, vis {r['nv']}/{len(r['pv'])} | {r['n']} matched, {r['inl']} inl, rms {r['rms']:.2f} px, scale {np.sqrt(abs(np.linalg.det(H[:2, :2]))):.3f}")
for r in rows: finish(r)
model = fit_model(rows)
# pass 2: rectify the weak ones through the model and decode there, then refit
for r in pending:
    H0 = model_H(model, r['Z']); H_bv, _ = cv2.findHomography(r['ov'], r['pv']); H_bu = np.linalg.inv(H0) @ H_bv
    pu, ou, nu, rect = uv_points_rectified(boards[r['board']], r['uv'], H_bu)
    cv2.imwrite(os.path.join(OUT, f"{r['stem']}_rectified.jpg"), rect)
    if len(pu) >= 6:
        r.update(pu=pu, ou=ou, nu=nu); finish(r); rows.append(r)
    else:
        print(f"{r['stem']} {r['board']:4s}: still undecodable after rectification ({len(pu)} pts)")
rows.sort(key=lambda r: r['Z']); model = fit_model(rows)
H_inf, T = model
print("\nmodel: H(Z_cm) = H_inf + T/Z   (uv px -> phone px)\nH_inf =\n", np.round(H_inf, 4), "\nT third column =", np.round(T[:, 2], 1))
print("\nmodel residuals (vis corners predicted from uv corners through H(Z) vs detected):")
for r in rows:
    Hm = model_H(model, r['Z']); proj = cv2.perspectiveTransform(r['pu_m'][None], Hm)[0]; e = np.linalg.norm(proj - r['pv_m'], axis=1)
    c = cv2.perspectiveTransform(np.array([[[320, 240]]], np.float32), Hm)[0][0]
    print(f"  Z={r['Z']:5.1f} {r['board']:4s} rms {np.sqrt((e**2).mean()):6.1f} px (max {e.max():5.1f}) at 4032 wide | uv centre -> phone {c.round(0)}")
    vis = r['vis']; warped = cv2.warpPerspective(r['uv'], Hm, (vis.shape[1], vis.shape[0]))
    ov = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR); m = warped > 0
    ov[m] = (0.5 * ov[m] + 0.5 * np.stack([warped[m]] * 3, 1)).astype(np.uint8); ov[m, 2] = warped[m]
    for p in r['pv_m']: cv2.circle(ov, tuple(int(v) for v in p), 12, (0, 255, 0), 3)
    for p in proj: cv2.circle(ov, tuple(int(v) for v in p), 7, (0, 0, 255), 3)
    cv2.imwrite(os.path.join(OUT, f"{r['stem']}_model_overlay.jpg"), cv2.resize(ov, None, fx=0.4, fy=0.4), [cv2.IMWRITE_JPEG_QUALITY, 85])
np.savez(os.path.join(OUT, 'corr.npz'), **{f"{r['stem']}_{k}": np.asarray(r[k]) for r in rows for k in ('pu_m', 'pv_m', 'ou', 'pu', 'rvec', 'tvec', 'Z')}, stems=np.array([r['stem'] for r in rows]))
# physical read-out: scope focal length from the board scale, baseline/toe-in from the centre offset trend
fs = []
for r in rows:
    Hi = np.linalg.inv(np.array(r['H'])); H_bv, _ = cv2.findHomography(r['ov'], r['pv']); H_bu = Hi @ H_bv   # board mm -> uv px
    fs.append(np.sqrt(abs(np.linalg.det(H_bu[:2, :2]))) * r['Z'] * 10)
print(f"\nscope focal length from board scale: {np.median(fs):.0f} px (per pair {np.round(fs).astype(int).tolist()}); phone assumed {F_PHONE:.0f} px")
json.dump(dict(H_inf=H_inf.tolist(), T=T.tolist(), f_phone_px=F_PHONE, f_scope_px=float(np.median(fs)),
               pairs=[dict(stem=r['stem'], board=r['board'], Z_tape=r['Ztape'], Z_phone=r['Z'], tilt_deg=r['tilt'], n=r['n'], rms=r['rms'], H=r['H']) for r in rows],
               note='H(Z_cm)=H_inf+T/Z maps saved uv px (640x480) to exif-upright phone px (4032x3024); multiply the phone side by 1600/4032 for the 1600-wide working frame; Z = distance from the phone lens to the plane'),
          open(os.path.join(D, 'rig_model.json'), 'w'), indent=1)
# validation on the bullseye sheet: detect 4 dark blobs in both, Z from the 200x120 rectangle in the phone frame
def bullseyes(gray, scale):
    g = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1 else gray
    p = cv2.SimpleBlobDetector_Params(); p.filterByColor = True; p.blobColor = 0; p.filterByArea = True
    p.minArea = 40; p.maxArea = 20000; p.filterByCircularity = True; p.minCircularity = 0.6; p.filterByConvexity = False; p.filterByInertia = True; p.minInertiaRatio = 0.5
    kps = cv2.SimpleBlobDetector_create(p).detect(g)
    return np.array([k.pt for k in kps], np.float32) / scale, np.array([k.size for k in kps]) / scale
for stem, ztape in fids:
    uv = cv2.imread(os.path.join(D, stem + '.jpg'), 0); vis = load_vis(os.path.join(D, stem + '_vis.jpg'))
    pv, sv = bullseyes(vis, 0.25); pu, su = bullseyes(uv, 1.0)
    print(f"\n{stem} fid tape {ztape:.0f}: blobs vis {len(pv)} uv {len(pu)} -- sizes vis {np.round(sv).astype(int).tolist()[:8]} uv {np.round(su).astype(int).tolist()[:8]}")
    dbg = cv2.cvtColor(uv, cv2.COLOR_GRAY2BGR)
    for p, s in zip(pu, su): cv2.circle(dbg, tuple(int(v) for v in p), int(s / 2) + 2, (0, 0, 255), 1)
    cv2.imwrite(os.path.join(OUT, f'{stem}_uvblobs.jpg'), dbg)
