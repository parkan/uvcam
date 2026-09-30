"""run register_pair over every SCOPE_<stamp>.jpg in a directory, then build a contact sheet."""
import sys, glob, importlib.util
from pathlib import Path
import numpy as np, cv2

spec = importlib.util.spec_from_file_location("rp", str(Path(__file__).with_name("register_pair.py")))
rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)

d = Path(sys.argv[1]); fb = np.load(sys.argv[2]) if len(sys.argv) > 2 else None
rows = []
for f in sorted(d.glob("SCOPE_*.jpg")):
    if "_vis" in f.name or not f.with_name(f.stem + "_vis.jpg").exists(): continue
    print("==", f.name)
    H = rp.main(f, fb)
    stamp = f.stem.replace("SCOPE_", "")
    rows.append((stamp, H is not None))

# contact sheet: vis crop | uv warped | diff, one row per pair, 3 x 300 px wide
tiles = []
for stamp, ok in rows:
    if not ok: continue
    imgs = [cv2.imread(str(d / f"{stamp}_{k}.jpg")) for k in ("vis_crop", "uv_warped", "diff")]
    if any(i is None for i in imgs): continue
    h = 220
    imgs = [cv2.resize(i, (int(i.shape[1] * h / i.shape[0]), h)) for i in imgs]
    w = max(i.shape[1] for i in imgs)
    imgs = [cv2.copyMakeBorder(i, 0, 0, 0, w - i.shape[1], cv2.BORDER_CONSTANT) for i in imgs]
    row = cv2.hconcat(imgs)
    cv2.putText(row, stamp, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1, cv2.LINE_AA)
    tiles.append(row)
if tiles:
    w = max(t.shape[1] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, 4, 0, w - t.shape[1], cv2.BORDER_CONSTANT) for t in tiles]
    for i in range(0, len(tiles), 8):
        cv2.imwrite(str(d / f"contact_{i//8:02d}.jpg"), cv2.vconcat(tiles[i:i+8]), [cv2.IMWRITE_JPEG_QUALITY, 88])
print("pairs:", len(rows), "registered:", sum(ok for _, ok in rows))
