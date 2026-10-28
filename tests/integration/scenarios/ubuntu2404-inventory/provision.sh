#!/bin/bash
# Provision ubuntu2404-inventory: Ubuntu 24.04 with a held nginx and a locally
# built package (no archive origin, so it reports as third-party).
set -euo pipefail

apt-get install -y --no-install-recommends nginx
apt-mark hold nginx

mkdir -p /tmp/disco-localtool/DEBIAN
cat > /tmp/disco-localtool/DEBIAN/control <<'CONTROL'
Package: disco-localtool
Version: 1.0
Architecture: all
Maintainer: cc-disco integration tests <noreply@example.com>
Description: Locally built package for third-party detection tests
CONTROL
dpkg-deb --build /tmp/disco-localtool /tmp/disco-localtool.deb
dpkg -i /tmp/disco-localtool.deb

echo "ubuntu2404-inventory provisioning complete"
