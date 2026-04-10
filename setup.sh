#!/bin/bash
set -euo pipefail

echo "=== Just Plane Mosher Setup ==="

# Enable SPI (required for Inky display)
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0

# Add SPI chip-select overlay if not already present
if ! grep -q "dtoverlay=spi0-0cs" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt
    echo "Added SPI overlay — reboot required after setup"
fi

# System dependencies
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv \
    libopenjp2-7 libtiff6 libfreetype6 libfreetype6-dev \
    fonts-dejavu-core

# Python venv
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install inky[rpi]

# Create config from example if not exists
[ -f .env ] || cp .env.example .env

# Pre-cache map tiles
echo "Pre-caching map tiles..."
python3 -c "
from src.config import load_config
from src.map_tiles import TileCache
config = load_config()
tc = TileCache(config)
tc.build_base_map(config)
print('Map tiles cached!')
"

# Install systemd service
sudo cp just-plane-mosher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable just-plane-mosher

echo ""
echo "=== Setup complete! ==="
echo "1. Edit .env with your settings (location, API key)"
echo "2. Reboot: sudo reboot"
echo "3. After reboot, start: sudo systemctl start just-plane-mosher"
echo "4. Check logs: journalctl -u just-plane-mosher -f"
