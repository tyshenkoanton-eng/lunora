#!/bin/bash
set -euo pipefail

echo "=== Lunora VPS Setup ==="

# System updates
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 git ufw

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Docker autostart
systemctl enable docker
systemctl start docker

# Project
mkdir -p /opt/lunora
cd /opt/lunora
git clone https://github.com/tyshenkoanton-eng/lunora.git .

# Env file — EDIT THESE VALUES
cp .env.example .env
echo ""
echo "=== SETUP COMPLETE ==="
echo "Now edit /opt/lunora/.env with your tokens:"
echo "  nano /opt/lunora/.env"
echo ""
echo "Then start:"
echo "  cd /opt/lunora && docker compose up -d"
