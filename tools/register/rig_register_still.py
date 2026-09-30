#!/usr/bin/env python3
# calibrated registration of photo-mode pairs: the rig model leaves one unknown per pair, the plane distance Z.
# usage: rig_register_still.py <dir> [stems...]   -> <dir>/reg/<stem>_{overlay,uvwarp,logratio}.jpg + reg/results.json
import cv2, numpy as np, sys, os, json, glob
from PIL import Image, ImageOps
D = sys.argv[1]; OUT = os.path.join(D, 'reg'); os.makedirs(OUT, exist_ok=True)
c = json.load(open(os.environ.get('UVCAM_CALIB', 'rig_calib_v2.json')))   # rig calibration from tools/calib/calib_rig.py
K_s = np.array(c['K_scope']); R = np.array(c['R_phone_to_scope']); t = np.array(c['t_phone_to_scope_mm']); M = np.array(c['mirror_saved_uv'], float); K_p = np.array(c['K_phone']); k1, k2 = c['dist_scope']
WORK = 1600; sc = WORK / 4032.0; S = np.diag([sc, sc, 1.0])
def H_uv_to_work(Z_cm): return S @ np.linalg.inv(M @ K_s @ (R + np.outer(t, [0, 0, 1.0]) / (Z_cm * 10)) @ np.linalg.inv(K_p))
def grad(g): gx = cv2.Sobel(g, cv2.CV_32F, 1, 0); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1); return cv2.GaussianBlur(np.hypot(gx, gy), (0, 0), 2)
stems = sys.argv[2:] or sorted(set(os.path.basename(f)[:-4] for f in glob.glob(os.path.join(D, 'SCOPE_*.jpg')) if not f.endswith('_vis.jpg')))
results = {}
for stem in stems:
    if not os.path.exists(os.path.join(D, stem + '_vis.jpg')): print(stem, 'has no phone partner, skipped'); continue
    uv = cv2.imread(os.path.join(D, stem + '.jpg'), 0); UVK = int(os.environ.get('UVK', '0')); uv = np.rot90(uv, UVK % 4); uv = np.ascontiguousarray(uv[:, ::-1] if UVK >= 4 else uv)
    if uv.shape != (480, 640): uv = cv2.resize(uv, (640, 480))   # 90-degree cases: keep the calibration's 640x480 lattice
    pim = Image.open(os.path.join(D, stem + '_vis.jpg')); orient = pim.getexif().get(274, 1)
    # the calibration frame is the sensor frame rotated 180 (the calibration shots carried exif orientation 3);
    # work there whatever the tag says, and rotate outputs to the display orientation at the end
    visc = np.ascontiguousarray(np.rot90(np.array(pim.convert('RGB')), 2))
    disp = {1: 2, 3: 0, 6: 1, 8: 3}.get(orient, 0)   # rot90 count taking the calibration frame to the exif-upright view
    def to_disp(a): return np.ascontiguousarray(np.rot90(a, disp))
    vis = cv2.resize(visc, (WORK, int(visc.shape[0] * sc)), interpolation=cv2.INTER_AREA); g = cv2.cvtColor(vis, cv2.COLOR_RGB2GRAY)
    uvu = cv2.undistort(uv[:, ::-1], K_s, np.array([k1, k2, 0, 0]))[:, ::-1]; gu = grad(uvu); gv = grad(g); ones = np.full(uv.shape, 255, np.uint8)
    def score(Z):
        H = H_uv_to_work(Z); w = cv2.warpPerspective(gu, H, (vis.shape[1], vis.shape[0])); m = cv2.warpPerspective(ones, H, (vis.shape[1], vis.shape[0])) > 128
        if m.sum() < 2000: return -1
        a = w[m] - w[m].mean(); b = gv[m] - gv[m].mean(); return float((a * b).sum() / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    Zs = np.geomspace(12, 400, 60); s = [score(z) for z in Zs]; i = int(np.argmax(s))
    Zf = np.geomspace(Zs[max(0, i - 1)], Zs[min(len(Zs) - 1, i + 1)], 15); sf = [score(z) for z in Zf]; j = int(np.argmax(sf)); Z, best = float(Zf[j]), sf[j]
    H = H_uv_to_work(Z); w = cv2.warpPerspective(uvu, H, (vis.shape[1], vis.shape[0])); m = cv2.warpPerspective(ones, H, (vis.shape[1], vis.shape[0])) > 128
    # second-best distinct peak, to flag ambiguous fits
    peaks = [k for k in range(1, len(s) - 1) if s[k] > s[k - 1] and s[k] > s[k + 1]]; alt = sorted(((s[k], Zs[k]) for k in peaks if abs(np.log(Zs[k] / Z)) > 0.25), reverse=True)[:1]
    results[stem] = dict(Z_cm=Z, ncc=best, orient=int(orient), alt=[(float(a), float(b)) for a, b in alt])
    print(f"{stem}: exif {orient} Z={Z:5.1f} cm ncc {best:.3f}" + (f"   (alt peak Z={alt[0][1]:.0f} ncc {alt[0][0]:.3f})" if alt else ""))
    ov = vis.copy(); ov[m] = (0.5 * ov[m] + 0.5 * np.stack([w[m]] * 3, 1)).astype(np.uint8); ov[m, 0] = w[m]   # uv in red
    cv2.putText(ov, f"Z {Z:.0f} cm  ncc {best:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2, cv2.LINE_AA)
    cv2.imwrite(os.path.join(OUT, stem + '_overlay.jpg'), cv2.cvtColor(to_disp(ov), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    # log ratio uv/blue normalised to the footprint median (no neutral reference in the field)
    wb = cv2.GaussianBlur(w.astype(np.float32), (0, 0), 2) + 2; vb = cv2.GaussianBlur(vis[:, :, 2].astype(np.float32), (0, 0), 2) + 2
    k = np.median(vb[m] / wb[m]); r = np.zeros(g.shape, np.float32); r[m] = np.log2(k * wb[m] / vb[m]); tt = np.clip(r / 2, -1, 1)
    col = np.zeros(vis.shape, np.float32); pos = np.clip(tt, 0, 1)[..., None]; neg = np.clip(-tt, 0, 1)[..., None]
    col += pos * np.array([255, 190, 0]) + neg * np.array([120, 60, 255]) + (1 - pos - neg) * np.array([90, 90, 90]); lum = (g.astype(np.float32) / 255)[..., None]
    lr = vis.copy().astype(np.float32); lr[m] = (col * (0.35 + 0.65 * lum))[m]
    ys, xs = np.where(m); x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max(); crop = lambda im: im[y0:y1, x0:x1]
    panel = np.hstack([to_disp(crop(vis)), cv2.cvtColor(to_disp(crop(w)), cv2.COLOR_GRAY2RGB), to_disp(crop(lr).astype(np.uint8))])
    cv2.imwrite(os.path.join(OUT, stem + '_panel.jpg'), cv2.cvtColor(panel, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
json.dump(results, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
