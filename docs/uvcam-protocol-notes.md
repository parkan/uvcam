# usee plus / supercamera (2ce3:3828) protocol -- what the firmware actually accepts

2026-09-28. sources: the vendor app com.i4season.useeplus 1.0.102 (not redistributed),
jadx of its classes.dex, a ghidra headless decompile of
lib/armeabi-v7a/libOtgCameraLibUSB.so (decompiled output not redistributed), and live
probes on this unit.

## the library speaks to two different device personalities

`OtgCamera::connect` -> `init_device_info` -> `otg_scan_control` walks the config
descriptor and `getbulk_type` returns the ctype from what it found:

- ctype 1 "YUV": single vendor interface (ff/f0/1), bulk IN 0x82. driven by class
  control requests on ep0: `A0 00 wValue=5 len 512` = info block (vendor, product,
  fw, width @46, height @48), `20 01 wValue=5 len 64` = start, `20 02` = stop.
  frames = 511-byte `DD CC 01 00` header + raw YUYV w*h*2 (mfi_handle_data_yuv,
  then I422ToNV21 for the preview). this is what usb-scope calls the "YUV
  endoscope"; same VID/PID exists in this shape, and 0329:2022.
- ctype 2 "JPEG": two interfaces (iAP stub on if0 + com.useeplus.protocol on if1
  alt 1), bulk 0x01/0x81. BB AA framed commands, AA BB framed 944-byte packets,
  payload = baseline JPEG slices. THIS UNIT.

the personality is fixed by the descriptors the firmware presents; there is no
command that moves a device from one to the other.

## complete host->device vocabulary of the JPEG personality (from the .so)

| bytes | native fn | this unit |
|---|---|---|
| `FF 55 FF 55 EE 10` on if0 OUT 0x02, expects 6-byte reply on 0x82 | test_mfi_usb | no reply (timeout); only sets an "mfi present" flag |
| `BB AA 05 00 00` | open_video_jpeg / send_connect_command(1) | starts stream; mid-stream = restarts frame counter at 0 |
| `BB AA 06 00 00` | open_video_new / send_connect_command(other) | STOPS the stream on this fw |
| `BB AA 08 00 00` | send_disconnect_command | ignored (stream keeps running) |
| `BB AA 0B 00 02 cam res 00` | change_camera | ignored: cam 0-2 x res 0,1,2,4..0x80,0xff, no cid-0x0B ack, no size change |
| `BB AA 0C 09 00 00 aH aL lenL lenH 00 00 00 00` | read_user_data_unlock | ignored at addr 0, 0x100, 0x1000 |
| `BB AA 0D len+9 ..` + up to 128 B | write_user_data_unlock | NOT tried (flash write) |
| ctrl `A0/A1/C0/C1`, req 0-3, wValue 5/0 | (yuv personality) | all STALL |
| `BB AA cid 00 00` for cid 01-04,07,09,0A,0E-11,20 | -- | ignored |

there is nothing else: the only other bulk writers in the .so are check_id/
check_id2/get_lic, which are SCSI CBWs for the mass-storage product family
(OTGDeviceHandle.java: "USBC" wrappers, GET_MAX_LUN), not this device.

## device->host packet types the library understands (handle_pro switch)

5 = all-info (vendor/product/version/flashid/camnum/res_list/capacity -- never
emitted by this unit), 6 = open-stream ack, 7 / 10 = JPEG slice, 0x0E = JPEG slice
with g-sensor angle in byte 6 (pictype flag, not a raw format), 0x0B = switch ack,
0x0C = user-data reply. flags byte 7: bit0 hasg, bit1 button, bit2-4 zoom.

## conclusion

no exposure, gain, LED, format or resolution control exists in this firmware's
command language; the parser only reacts to 05 and 06. a raw feed is a property of
the other product (single-interface YUV firmware), not something this unit can be
switched into. the JPEG decode in the webcam bridge is unavoidable, and black
indoor frames are a light problem (no near-UV) rather than a protocol one.

measured on this unit today: 20 fps in room light on the laptop (12.5 KB/frame),
vs the 12.7 fps the Tibiaworx sniffer saw on Android; the rate is exposure-bound.
