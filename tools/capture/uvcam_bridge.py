"""bridge the usee-plus uv camera (2ce3:3828) into a v4l2loopback device so any app sees a webcam.

capture side is the same handshake as uvcam_capture.py; the reassembled jpeg frames are piped
into ffmpeg, which decodes, applies the orientation you ask for, letterboxes to the output size,
and writes yuyv422 frames to the loopback. yuyv because zoom/chrome are picky about mjpeg there.

usage: uvcam_bridge.py [--device /dev/videoN] [--transpose 0-3] [--hflip] [--vflip]
                       [--size 640x480] [--fps 24] [--no-pad]
orientation: transpose values are ffmpeg's (0 = 90ccw+vflip, 1 = 90cw, 2 = 90ccw, 3 = 90cw+vflip).
the sensor is mounted rotated, so with the camera upright you normally want 1 or 2, plus hflip.
"""
import argparse
import glob
import os
import struct
import subprocess
import sys
import time

import usb.core
import usb.util

VID, PID = 0x2CE3, 0x3828
EP_IN, EP1_OUT, EP2_OUT = 0x81, 0x01, 0x02


def find_loopback():
    # v4l2loopback devices announce themselves by name; ublue images ship one labelled
    # "OBS Virtual Camera" with exclusive_caps=1
    for n in sorted(glob.glob("/sys/devices/virtual/video4linux/video*/name")):
        name = open(n).read().strip()
        if "OBS" in name or "loopback" in name.lower() or "Dummy" in name:
            return "/dev/" + n.split("/")[-2]
    return None


def open_cam():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit("uv camera not found on usb (2ce3:3828)")
    # a previous session leaves the stream half-open; a reset makes the start command stick
    dev.reset()
    time.sleep(1.0)
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    for i in (0, 1):
        if dev.is_kernel_driver_active(i):
            dev.detach_kernel_driver(i)
        usb.util.claim_interface(dev, i)
    dev.set_interface_altsetting(interface=1, alternate_setting=1)
    try:
        dev.clear_halt(EP_IN)
    except usb.core.USBError:
        pass
    dev.write(EP2_OUT, bytes([0xFF, 0x55, 0xFF, 0x55, 0xEE, 0x10]), timeout=1000)
    dev.write(EP1_OUT, bytes([0xBB, 0xAA, 0x05, 0x00, 0x00]), timeout=1000)
    return dev


def jpeg_frames(dev):
    buf = bytearray()
    cur_fid = None
    jpeg = bytearray()
    while True:
        try:
            buf += dev.read(EP_IN, 4096, timeout=1000)
        except usb.core.USBTimeoutError:
            continue
        while len(buf) >= 12:
            magic, cid, length = struct.unpack_from("<HBH", buf, 0)
            if magic != 0xBBAA:
                del buf[0]
                continue
            if len(buf) < 5 + length:
                break
            fid = buf[5]
            chunk = bytes(buf[12:5 + length])
            del buf[:5 + length]
            if jpeg and fid != cur_fid:
                if jpeg[:2] == b"\xff\xd8" and jpeg[-2:] == b"\xff\xd9":
                    yield bytes(jpeg)
                jpeg = bytearray()
            cur_fid = fid
            jpeg += chunk


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default=None, help="v4l2loopback node (default: first one found)")
    p.add_argument("--transpose", type=int, default=None, help="ffmpeg transpose 0-3; omit for none")
    p.add_argument("--hflip", action="store_true")
    p.add_argument("--vflip", action="store_true")
    p.add_argument("--size", default="640x480", help="output WxH (default 640x480 landscape)")
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--no-pad", action="store_true", help="crop to fill instead of letterboxing")
    p.add_argument("--stats", action="store_true", help="print frame counts once a second")
    a = p.parse_args()

    device = a.device or find_loopback()
    if not device:
        sys.exit("no v4l2loopback device found; load the module or pass --device")
    w, h = a.size.split("x")
    vf = []
    if a.transpose is not None:
        vf.append(f"transpose={a.transpose}")
    if a.hflip:
        vf.append("hflip")
    if a.vflip:
        vf.append("vflip")
    if a.no_pad:
        vf.append(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
    else:
        vf.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer", "-flags", "low_delay",
           "-f", "mjpeg", "-framerate", str(a.fps), "-i", "pipe:0",
           "-vf", ",".join(vf), "-r", str(a.fps), "-pix_fmt", "yuyv422", "-f", "v4l2", device]
    dev = open_cam()
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    print(f"streaming to {device} as {w}x{h} yuyv422; ctrl-c to stop", file=sys.stderr)
    n, t0 = 0, time.time()
    try:
        for jpg in jpeg_frames(dev):
            ff.stdin.write(jpg)
            n += 1
            if a.stats and time.time() - t0 >= 1.0:
                print(f"{n} fps", file=sys.stderr)
                n, t0 = 0, time.time()
            if ff.poll() is not None:
                sys.exit("ffmpeg exited")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ff.stdin.close()
            ff.wait(timeout=3)
        except Exception:
            ff.kill()
        usb.util.dispose_resources(dev)


if __name__ == "__main__":
    main()
