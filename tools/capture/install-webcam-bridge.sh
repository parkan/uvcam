#!/usr/bin/env bash
# install the uv camera webcam bridge on a ublue box (bazzite/bluefin). run as the normal user.
set -e
DEST="$HOME/.local/share/uvcam"; BIN="$HOME/.local/bin"
mkdir -p "$DEST" "$BIN"
HERE="$(dirname "$(readlink -f "$0")")"
cp "$HERE/uvcam_bridge.py" "$HERE/uvcam-webcam" "$DEST/"
chmod +x "$DEST/uvcam-webcam"
ln -sf "$DEST/uvcam-webcam" "$BIN/uvcam-webcam"
# raw usb access for the camera, it has no kernel driver
if [ ! -f /etc/udev/rules.d/99-supercamera-uv.rules ]; then
  echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="2ce3", ATTRS{idProduct}=="3828", MODE="0666"' | sudo tee /etc/udev/rules.d/99-supercamera-uv.rules >/dev/null
  sudo udevadm control --reload && sudo udevadm trigger
fi
command -v uvx >/dev/null || { echo "uv not found: curl -LsSf https://astral.sh/uv/install.sh | sh"; }
modinfo v4l2loopback >/dev/null 2>&1 && echo "v4l2loopback present" || echo "v4l2loopback missing on this image"
ls /dev/video* 2>/dev/null
echo "installed. plug the camera in and run: uvcam-webcam --stats"
