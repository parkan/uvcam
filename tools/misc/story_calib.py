#!/usr/bin/env python3
# instagram-story 3-up of the calibration: phone | uv (upright, registered crop) | homography visualised. 1080x1920.
import cv2, numpy as np, json, os, sys
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageFilter
D = os.environ.get('UVCAM_CALIB_DIR', '.'); stem = sys.argv[1]   # a calib dir with out/pairs_H.json + out/corr.npz from calib_fit.py
rows = {r['stem']: r for r in json.load(open(f'{D}/out/pairs_H.json'))}; H = np.array(rows[stem]['H'])
z = np.load(f'{D}/out/corr.npz'); pu = z[f'{stem}_pu_m']; pv = z[f'{stem}_pv_m']
vis = np.array(ImageOps.exif_transpose(Image.open(f'{D}/{stem}_vis.jpg')).convert('RGB')); uv = cv2.imread(f'{D}/{stem}.jpg', 0)
Hh, W = vis.shape[:2]; PW, PH = 1080, 640
# crop window in the phone frame around the board, story-panel aspect
x0, y0, x1, y1 = 100, 380, 3000, 2100
def crop_fit(img): return cv2.resize(img[y0:y1, x0:x1], (PW, PH), interpolation=cv2.INTER_AREA)
warped = cv2.warpPerspective(uv, H, (W, Hh)); fmask = cv2.warpPerspective(np.full(uv.shape, 255, np.uint8), H, (W, Hh)) > 128
# panel 1: phone
p1 = crop_fit(vis)
# panel 2: uv camera, upright = the warped frame cropped to its own footprint, fitted on a blurred fill
ys, xs = np.where(fmask); bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
uvc = cv2.cvtColor(warped[by0:by1, bx0:bx1], cv2.COLOR_GRAY2RGB); s = min(PW / uvc.shape[1], PH / uvc.shape[0]); uvs = cv2.resize(uvc, (int(uvc.shape[1] * s), int(uvc.shape[0] * s)), interpolation=cv2.INTER_AREA)
fill = np.array(Image.fromarray(cv2.resize(uvc, (PW, PH))).filter(ImageFilter.GaussianBlur(40))) // 2
p2 = fill.copy(); ox, oy = (PW - uvs.shape[1]) // 2, (PH - uvs.shape[0]) // 2; p2[oy:oy + uvs.shape[0], ox:ox + uvs.shape[1]] = uvs
# panel 3: homography -- uv pixel grid projected through H onto the phone frame, uv content tinted inside, matched corners
p3 = vis.copy().astype(np.float32); tint = np.array([150, 60, 255], np.float32)
p3[fmask] = 0.45 * p3[fmask] + 0.55 * (warped[fmask][:, None] / 255.0 * tint + (1 - warped[fmask][:, None] / 255.0) * np.array([20, 0, 40]))
p3 = p3.astype(np.uint8)
for u in range(0, 641, 40):
    pts = cv2.perspectiveTransform(np.array([[[u, v] for v in np.linspace(0, 479, 25)]], np.float32), H)[0].astype(np.int32); cv2.polylines(p3, [pts], False, (255, 230, 80), 3, cv2.LINE_AA)
for v in range(0, 481, 40):
    pts = cv2.perspectiveTransform(np.array([[[u, v] for u in np.linspace(0, 639, 33)]], np.float32), H)[0].astype(np.int32); cv2.polylines(p3, [pts], False, (255, 230, 80), 3, cv2.LINE_AA)
proj = cv2.perspectiveTransform(pu[None].astype(np.float32), H)[0]
for a, b in zip(pv, proj):
    cv2.circle(p3, tuple(int(v) for v in a), 22, (0, 255, 120), 5, cv2.LINE_AA); cv2.circle(p3, tuple(int(v) for v in b), 9, (255, 0, 200), -1, cv2.LINE_AA)
p3 = crop_fit(p3)
# assemble with labels
FONT = os.environ.get('FONT', '/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf'); font = ImageFont.truetype(FONT, 44); small = ImageFont.truetype(FONT, 30)
story = Image.new('RGB', (1080, 1920), (8, 8, 12)); d = ImageDraw.Draw(story)
labels = ['phone camera', 'UV camera  ·  365 nm, upright', 'homography  ·  UV pixel grid on the phone frame']
subs = ['Xperia 5 IV main cam', 'reflectance only, visible blocked', f'{len(pv)} ChArUco corners matched, rms {rows[stem]["rms"]:.1f} px']
for i, p in enumerate((p1, p2, p3)): story.paste(Image.fromarray(p), (0, i * PH))
out = f'{D}/out/story_calib_{stem[-6:]}.jpg'; story.save(out, quality=92); print(out)
