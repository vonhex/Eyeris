#!/bin/bash
# Restart the backend service cleanly.
# Run as root or with sudo.
sudo -u administrator XDG_RUNTIME_DIR=/run/user/$(id -u administrator) \
  systemctl --user restart image-catalog
echo "Backend restarted."
