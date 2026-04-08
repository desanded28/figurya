#!/bin/bash
# Figurya Oracle Proxy — one-shot setup script
# Run this on a fresh Oracle Cloud ARM VM (Ubuntu)
#
# Usage:
#   curl -fsSL <raw-github-url>/oracle-proxy/setup.sh | bash -s <YOUR_PROXY_KEY>
#
# Or manually:
#   chmod +x setup.sh && ./setup.sh <YOUR_PROXY_KEY>

set -euo pipefail

PROXY_KEY="${1:-}"
if [ -z "$PROXY_KEY" ]; then
    echo "Usage: ./setup.sh <PROXY_KEY>"
    echo "  PROXY_KEY = shared secret for authenticating proxy requests"
    exit 1
fi

echo "==> Installing Python and dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv

echo "==> Setting up proxy app..."
sudo mkdir -p /opt/figurya-proxy
sudo cp proxy.py /opt/figurya-proxy/ 2>/dev/null || sudo tee /opt/figurya-proxy/proxy.py < proxy.py > /dev/null

cd /opt/figurya-proxy
sudo python3 -m venv venv
sudo venv/bin/pip install -q fastapi uvicorn httpx

echo "==> Creating systemd service..."
sudo tee /etc/systemd/system/figurya-proxy.service > /dev/null <<EOF
[Unit]
Description=Figurya Scraping Proxy
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/figurya-proxy
Environment=PROXY_KEY=${PROXY_KEY}
Environment=PORT=9090
ExecStart=/opt/figurya-proxy/venv/bin/uvicorn proxy:app --host 0.0.0.0 --port 9090
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> Starting proxy service..."
sudo systemctl daemon-reload
sudo systemctl enable figurya-proxy
sudo systemctl restart figurya-proxy

echo "==> Opening port 9090 in iptables..."
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 9090 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

echo ""
echo "========================================="
echo " Figurya Proxy is running on port 9090"
echo " Test: curl http://$(curl -s ifconfig.me):9090/health"
echo "========================================="
echo ""
echo "IMPORTANT: Also open port 9090 in Oracle Cloud Console:"
echo "  Networking → Virtual Cloud Networks → your VCN → Security Lists"
echo "  → Add Ingress Rule: Source 0.0.0.0/0, TCP, Port 9090"
