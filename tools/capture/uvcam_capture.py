"""capture jpeg frames from the geek szitman 'supercamera' (usee plus protocol, 2ce3:3828).

protocol (from hbens/geek-szitman-supercamera, cc0): claim ifaces 0+1, iface 1 alt 1,
write FF55FF55EE10 to ep2, write BBAA050000 to ep1, then bulk-read ep1. each usb frame:
  u16le magic 0xBBAA | u8 cid | u16le len | u8 fid | u8 cam | u8 flags | u32 g_sensor | jpeg chunk
chunks with the same fid concatenate into one jpeg.
"""
import argparse
import struct
import sys
import time
from pathlib import Path

import usb.core
import usb.util

VID, PID = 0x2CE3, 0x3828
EP_IN, EP1_OUT, EP2_OUT = 0x81, 0x01, 0x02


def open_cam():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit("camera not found")
    # a previous session leaves the stream half-open and the next start command is ignored
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


def frames(dev, seconds):
    buf = bytearray()
    cur_fid = None
    cur_cam = None
    jpeg = bytearray()
    stats = {"usb_frames": 0, "bad_magic": 0, "buttons": 0, "cams": set(), "cids": set()}
    end = time.time() + seconds
    while time.time() < end:
        try:
            buf += dev.read(EP_IN, 4096, timeout=1000)
        except usb.core.USBTimeoutError:
            continue
        while len(buf) >= 12:
            magic, cid, length = struct.unpack_from("<HBH", buf, 0)
            if magic != 0xBBAA:
                stats["bad_magic"] += 1
                del buf[0]
                continue
            if len(buf) < 5 + length:
                break
            fid, cam, flags, g = struct.unpack_from("<BBBI", buf, 5)
            chunk = bytes(buf[12:5 + length])
            del buf[:5 + length]
            stats["usb_frames"] += 1
            stats["cids"].add(cid)
            stats["cams"].add(cam)
            if flags & 0x02:
                stats["buttons"] += 1
            if jpeg and fid != cur_fid:
                yield cur_cam, bytes(jpeg), stats
                jpeg = bytearray()
            cur_fid, cur_cam = fid, cam
            jpeg += chunk


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=6)
    p.add_argument("--save", type=int, default=5, help="save this many complete frames")
    p.add_argument("--out", default="frames")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = open_cam()
    n = 0
    sizes = []
    t0 = time.time()
    last = None
    for cam, jpg, stats in frames(dev, a.seconds):
        ok = jpg[:2] == b"\xff\xd8" and jpg[-2:] == b"\xff\xd9"
        sizes.append(len(jpg))
        if ok and n < a.save:
            (out / f"frame{n:02d}_cam{cam}.jpg").write_bytes(jpg)
            n += 1
        last = stats
    dt = time.time() - t0
    print(f"{len(sizes)} frames in {dt:.1f} s ({len(sizes)/dt:.1f} fps), saved {n} to {out}")
    if sizes:
        print(f"jpeg sizes: min {min(sizes)} max {max(sizes)} mean {sum(sizes)//len(sizes)} bytes")
    if last:
        print(f"usb frames {last['usb_frames']}, bad magic {last['bad_magic']}, cids {sorted(last['cids'])}, cams {sorted(last['cams'])}, button presses {last['buttons']}")


if __name__ == "__main__":
    main()
