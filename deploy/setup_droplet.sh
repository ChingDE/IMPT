#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy/setup_droplet.sh
# One-time bootstrap for a fresh DigitalOcean Ubuntu 24.04 Droplet.
#
# Run as root immediately after first SSH login:
#   bash deploy/setup_droplet.sh
#
# What it does:
#   1. Updates the system
#   2. Installs Docker + Compose plugin
#   3. Installs Caddy (reverse proxy / HTTPS)
#   4. Configures UFW firewall
#   5. Creates a non-root imptuser
#   6. Clones the repo (prompts for GitHub details)
#   7. Reminds you to fill in .env
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

echo "════════════════════════════════════════════════"
echo "  IMPT Droplet Bootstrap"
echo "════════════════════════════════════════════════"

# ── 1. System update ──────────────────────────────────────────────────────────
echo "[1/7] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Docker ─────────────────────────────────────────────────────────────────
echo "[2/7] Installing Docker..."
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version
docker compose version

# ── 3. Caddy ──────────────────────────────────────────────────────────────────
echo "[3/7] Installing Caddy..."
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq
apt-get install -y -qq caddy
caddy version

# ── 4. Firewall ───────────────────────────────────────────────────────────────
echo "[4/7] Configuring UFW firewall..."
apt-get install -y -qq ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment "SSH"
ufw allow 80/tcp    comment "HTTP  (Caddy / Cloudflare)"
ufw allow 443/tcp   comment "HTTPS (Caddy / Cloudflare)"
# Port 8000 (FastAPI) is NOT opened — only Caddy on the host can reach it
ufw --force enable
ufw status verbose

# ── 5. Non-root user ──────────────────────────────────────────────────────────
echo "[5/7] Creating imptuser..."
if ! id imptuser &>/dev/null; then
    useradd -m -s /bin/bash -G docker imptuser
fi
# Copy root SSH key so imptuser can also log in
mkdir -p /home/imptuser/.ssh
cp /root/.ssh/authorized_keys /home/imptuser/.ssh/
chown -R imptuser:imptuser /home/imptuser/.ssh
chmod 700 /home/imptuser/.ssh
chmod 600 /home/imptuser/.ssh/authorized_keys

# ── 6. Clone the repository ───────────────────────────────────────────────────
echo "[6/7] Setting up repository..."
echo ""
echo "  You need a GitHub deploy key. Steps:"
echo "  1. Run as imptuser: ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ''"
echo "  2. cat ~/.ssh/github_deploy.pub"
echo "  3. Add that key in GitHub → repo → Settings → Deploy Keys"
echo ""
echo "  Then clone with:"
echo "  su - imptuser"
echo "  git clone git@github.com:YOUR_USERNAME/impt.git ~/impt"
echo "  cd ~/impt"
echo "  cp .env.example .env && nano .env"
echo ""

# ── 7. Caddy config reminder ──────────────────────────────────────────────────
echo "[7/7] Caddy setup reminder..."
echo ""
echo "  After cloning:"
echo "  1. Edit deploy/caddy/Caddyfile — replace api.your-domain.com"
echo "  2. cp ~/impt/deploy/caddy/Caddyfile /etc/caddy/Caddyfile"
echo "  3. systemctl reload caddy"
echo ""

echo "════════════════════════════════════════════════"
echo "  Bootstrap complete."
echo "  Next: su - imptuser → clone repo → fill .env → docker compose up -d --build"
echo "════════════════════════════════════════════════"
