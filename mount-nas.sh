#!/bin/bash
# Mount QNAP NAS shares via CIFS for fast file listing
# Run with: sudo bash mount-nas.sh

set -e

NAS_IP="10.0.1.228"
NAS_USER="administrator"
NAS_PASS="9937431334@Vv"
MOUNT_BASE="/mnt/nas"
SHARES="photos"

# Create credentials file (more secure than inline password)
CRED_FILE="/etc/nas-credentials"
cat > "$CRED_FILE" <<EOF
username=$NAS_USER
password=$NAS_PASS
EOF
chmod 600 "$CRED_FILE"

for share in $SHARES; do
    mountpoint="$MOUNT_BASE/$share"
    mkdir -p "$mountpoint"

    # Skip if already mounted
    if mountpoint -q "$mountpoint"; then
        echo "$share already mounted at $mountpoint"
        continue
    fi

    echo "Mounting $share -> $mountpoint"
    mount -t cifs "//$NAS_IP/$share" "$mountpoint" \
        -o credentials="$CRED_FILE",uid=1000,gid=1000,file_mode=0644,dir_mode=0755,rw,vers=3.0
done

# Add to fstab for persistence across reboots
for share in $SHARES; do
    mountpoint="$MOUNT_BASE/$share"
    fstab_entry="//$NAS_IP/$share $mountpoint cifs credentials=$CRED_FILE,uid=1000,gid=1000,file_mode=0644,dir_mode=0755,rw,vers=3.0,_netdev,nofail 0 0"
    if ! grep -qF "//$NAS_IP/$share" /etc/fstab; then
        echo "$fstab_entry" >> /etc/fstab
        echo "Added $share to /etc/fstab"
    fi
done

echo "All shares mounted. Listing is now instant."
