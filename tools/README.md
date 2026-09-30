# rig tools

Linux-side scripts for the UV scope + phone rig. All run with [uv](https://docs.astral.sh/uv/) and no
install: `uvx --with <deps> python tools/<dir>/<script>.py ...`. Dependencies per script are in the
first lines of each file; the usual set is `opencv-contrib-python-headless numpy pillow scipy`
(`opencv-python-headless` is enough when the script does not use ArUco).

Conventions: the phone photo of a pair is `SCOPE_<t>_vis.jpg`, the UV frame `SCOPE_<t>.jpg`; clips are
`SCOPE_<t>.mp4` and `SCOPE_<t>_vis_+<offset>ms.mp4`. UV files are in the scope's native frame (the app
writes them that way since 2026-09-29). The rig calibration JSON is read from `$UVCAM_CALIB`
(default `rig_calib_v2.json` in the working directory); `calib/example/rig_calib_v2.json` is a real one.

## capture/

- `uvcam_capture.py` -- grab frames from the scope over pyusb (`--seconds`, `--save`), no app needed.
  `udev/99-supercamera-uv.rules` gives the device node user access.
- `uvcam_bridge.py`, `uvcam-webcam`, `install-webcam-bridge.sh` -- scope -> ffmpeg -> v4l2loopback, so the
  camera shows up as a webcam. Needs `v4l2loopback` (shipped on Universal Blue images) and ffmpeg.

## calib/

1. Print `targets/` at 100 % and shoot paired snapshots of a board at 3-4 measured distances (README there).
2. `calib_fit.py <dir>` with a `pairs.txt` listing `stem board Z_cm` per pair: detects ChArUco corners in
   both images (rectifying the UV frame through a rough model when the markers are too small to decode),
   estimates each board's distance from the phone image, and dumps correspondences.
3. `calib_rig.py <dir>` -- bundle fit of the scope intrinsics (f, principal point, k1, k2) and its pose
   relative to the phone from all pairs; writes `rig_calib_v2.json` and per-pair overlays. Expect ~2 px
   rms in UV pixels. Set the phone focal length constant at the top from the camera HAL
   (`adb logcat -s UVCam` prints sensor width and focal length at bind).

## register/

- `rig_register_still.py <dir> [stems]` -- calibrated registration of photo pairs: the only unknown per
  pair is the plane distance, searched on gradient correlation; writes overlays and a log-ratio panel.
  Weak on foliage; give it a plane anchor when it matters.
- `rig_anchor.py`, `anchor_plane.py`, `plane_fit.py`, `rig_ecc.py`, `rig_apply.py` -- video-mode helpers:
  solve distance and phone video crop from hand-read anchors, ECC polish, model-seeded search.
- `register_pair.py`, `batch_register.py`, `register_video_frame.py` -- the pre-calibration methods
  (feature matching and footprint search with the hand model in `rig_calib.json`); kept for reference.

## diff/

- `diff_inset_log.py uv.mp4 vis.mp4 H.npy out "x0,y0,x1,y1" [times] [stops]` -- log2(UV / phone blue)
  inside the registered footprint, gain-normalised on a reference region assumed UV-neutral, diverging
  colour map clipped at +-stops; clip plus four-panel stills. `diff_inset.py` is the linear-difference version.

## misc/

- `stack_frames.py` -- average consecutive UV frames for a cleaner still.
- `story_calib.py <stem>` -- 1080x1920 three-panel graphic (phone / UV / homography mesh) from a calib run.
