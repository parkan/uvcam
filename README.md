# UV Cam

Android app and rig tooling for a cheap 365 nm UV borescope ("Usee Plus" / "supercamera", USB 2CE3:3828)
mounted next to a phone camera. The app records the UV stream and, in the same moment, the phone's own
camera, with timestamps that let the two be registered afterwards. The tools calibrate the rig, register
UV frames onto the phone frames and compute UV-versus-visible reflectance maps. Built for photographing
birds and flowers; the crows on the balcony are the regular subjects.

## Provenance

The app is a fork of [technicallyvu/usb-scope](https://github.com/technicallyvu/usb-scope) (MIT), a
privacy-first viewer for USB endoscopes that ship with untrusted vendor apps. Its USB drivers, MJPEG
pipeline and zero-permission design are unchanged and its git history is kept here. The original readme is
in `docs/upstream-README.md`; the `docs/play-*.md` and `docs/privacy-policy.md` files describe the upstream
Play Store listing, not this app. What this fork adds:

- **Paired capture.** Every UV snapshot saves a phone photo beside it (`SCOPE_<t>.jpg` + `SCOPE_<t>_vis.jpg`);
  every UV recording can run a phone clip beside it, 720p, named with its start offset in milliseconds
  (`SCOPE_<t>_vis_+<offset>ms.mp4`) so the two align in post. Optional phone audio (jack mic).
- **Fixed geometry.** Files are written in each sensor's native frame: the UV rotate/mirror controls only
  affect the display, and the phone's target rotation is pinned. The phone is locked to one physical lens,
  zoom 1.0, electronic and optical stabilisation off, with autofocus and metering pinned to the window
  where the UV footprint sits at 30-50 cm. Registration then has one unknown per plane: its distance.
- **Sentry mode.** Arm the app on the device for 30-120 minutes; while armed, an intent from another app
  (Tasker fed by a bird detector, say) starts or stops a recording. Arming is never persisted and ends on
  expiry, scope unplug, low battery or the Disarm button. Every trigger decision is logged.

Still no network permission: `CAMERA` and `RECORD_AUDIO` are requested only when the matching setting is
switched on, and the build fails if any dependency adds `INTERNET`.

## Trigger contract

Two activity intents, honoured only while armed:

| action | extra | effect |
|---|---|---|
| `id.corvid.uvcam.START_RECORDING` | `duration` (seconds, string or int, default 60, clamped 5-300) | start UV (+ phone) recording, stop after `duration` |
| `id.corvid.uvcam.STOP_RECORDING` | | stop the running recording |

Refused, with the reason in logcat (`adb logcat -s UVCam`): disarmed, already recording, within the 30 s
cooldown after a clip, past the 30 min recording budget of the current arming, scope not streaming.

## Build

Any JDK 17 + Android SDK works; the reference build runs in a container so nothing is installed on the host:

```
podman run --rm -v "$PWD":/src:Z -w /src -e GRADLE_USER_HOME=/src/.gradle-home \
  -v "$HOME/.android-uvcam":/root/.android:Z ghcr.io/cirruslabs/android-sdk:36 \
  bash -lc 'apt-get update -qq && apt-get install -y -qq openjdk-17-jdk-headless && yes | sdkmanager --licenses >/dev/null; bash ./gradlew --no-daemon :android:assembleDebug'
adb install -r android/build/outputs/apk/debug/android-debug.apk
```

The mounted `.android` directory keeps the debug signing key stable between builds; without it every
container build makes a new key and the phone refuses the update (uninstall first).

## Files on the phone

`Pictures/UV Cam/` and `Movies/UV Cam/`. The UV frame is 640x480 MJPEG at 8-20 fps depending on light,
saved as it comes off the camera (mirrored and rotated 90 degrees relative to the phone; the calibration
takes care of that). The phone photo is full resolution with a constant EXIF orientation; the phone clip is
1280x720, 30 fps, H.264, AAC when audio is on.

## Tools

`tools/` holds the Linux side: pyusb capture, a v4l2loopback webcam bridge, ChArUco calibration of the
rig, calibrated registration of stills and video, and the log-ratio UV/visible diff. See `tools/README.md`.
`docs/uvcam-protocol-notes.md` records what the camera firmware actually accepts over USB (only start and
stop; there is no exposure, gain, LED or raw-format control).

## License

MIT, see `LICENSE`. Upstream copyright Anthony Vu; UV Cam changes and tools copyright parkan.
