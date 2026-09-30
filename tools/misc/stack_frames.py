"""stack a tripod burst from the scope into one low-noise frame and report what the sensor is doing.

input: a directory of frame*_cam*.jpg from uvcam_capture.py, or an .mp4 from the app.
only one camera tag is used, the other is a duplicate of the same sensor.
outputs next to the input: stack_mean.png (16-bit), stack_mean_8bit.jpg, stack_std.png, stack_report.txt
"""
import sys, glob, re
from pathlib import Path
import numpy as np, cv2


def load(src):
    p = Path(src)
    if p.is_dir():
        fs = sorted(glob.glob(str(p / "frame*_cam0.jpg")), key=lambda f: int(re.search(r"frame(\d+)", f).group(1)))
        return [cv2.imread(f, 0) for f in fs], p
    cap = cv2.VideoCapture(str(p)); frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
    return frames[::2], p.parent


def main(src):
    frames, out = load(src)
    n = len(frames)
    if n < 10: sys.exit(f"only {n} frames")
    ref = frames[n // 2].astype(np.float32)
    # tripod or not, remove residual drift with whole-pixel phase correlation against the middle frame
    acc = np.zeros_like(ref); acc2 = np.zeros_like(ref); shifts = []; used = 0
    for f in frames:
        f = f.astype(np.float32)
        (dx, dy), resp = cv2.phaseCorrelate(ref, f)
        if abs(dx) > 8 or abs(dy) > 8:
            continue
        M = np.float32([[1, 0, -dx], [0, 1, -dy]])
        g = cv2.warpAffine(f, M, (f.shape[1], f.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        acc += g; acc2 += g * g; shifts.append((dx, dy)); used += 1
    mean = acc / used
    std = np.sqrt(np.maximum(acc2 / used - mean ** 2, 0))
    shifts = np.array(shifts)

    # banding: row-profile ripple, single frame vs stack
    def ripple(a):
        p = a.mean(axis=1); k = 25
        s = np.convolve(np.pad(p, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
        return (p - s).std()
    # detail: high-frequency energy, single frame vs stack (jpeg blocks vs real structure)
    def hf(a):
        return (a - cv2.GaussianBlur(a, (0, 0), 1.5)).std()
    # 8x8 jpeg block grid strength: energy at block edges vs interior in the gradient image
    def blockiness(a):
        g = np.abs(np.diff(a, axis=1)); edge = g[:, 7::8].mean(); inner = np.delete(g, np.s_[7::8], axis=1).mean()
        return edge / inner

    single = ref
    rep = [
        f"frames read {n}, stacked {used} (tag 0 only)",
        f"registration drift: dx {shifts[:,0].min():+.2f}..{shifts[:,0].max():+.2f} px, dy {shifts[:,1].min():+.2f}..{shifts[:,1].max():+.2f} px",
        f"per-pixel temporal noise: median {np.median(std):.2f} grey levels, 95th pct {np.percentile(std, 95):.2f}",
        f"stack noise floor (median std / sqrt(n)): {np.median(std) / np.sqrt(used):.3f} levels  -> effective extra bits ~{np.log2(np.sqrt(used)):.1f}",
        f"banding ripple: single frame {ripple(single):.2f} levels, stack {ripple(mean):.2f} levels",
        f"high-frequency energy: single {hf(single):.2f}, stack {hf(mean):.2f} (what survives averaging is real detail or fixed pattern)",
        f"jpeg 8x8 block-edge ratio: single {blockiness(single):.3f}, stack {blockiness(mean):.3f} (1.0 = no block grid)",
        f"tonal range in stack: {mean.min():.1f}..{mean.max():.1f}, 1%..99% {np.percentile(mean,1):.1f}..{np.percentile(mean,99):.1f}",
    ]
    cv2.imwrite(str(out / "stack_mean.png"), np.clip(mean * 256, 0, 65535).astype(np.uint16))
    cv2.imwrite(str(out / "stack_mean_8bit.jpg"), np.clip(mean, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 97])
    lo, hi = np.percentile(mean, 0.5), np.percentile(mean, 99.5)
    cv2.imwrite(str(out / "stack_mean_stretched.jpg"), np.clip((mean - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 97])
    cv2.imwrite(str(out / "stack_std.png"), np.clip(std / max(std.max(), 1e-6) * 255, 0, 255).astype(np.uint8))
    (out / "stack_report.txt").write_text("\n".join(rep) + "\n")
    print("\n".join(rep)); print("wrote", out / "stack_mean*.{png,jpg}", out / "stack_std.png")


if __name__ == "__main__":
    main(sys.argv[1])
