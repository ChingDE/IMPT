#!/usr/bin/env bash
# deploy/setup_droplet.sh
# Bootstrap an Ubuntu 24.04 DigitalOcean Droplet for IMPT.
# Run once as root immediately after Droplet creation.
# Usage: bash /root/setup_droplet.sh

set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║          IMPT Droplet Bootstrap Script              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Update system ──────────────────────────────────────────────────────────────
echo "→ Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git unzip \
    ufw fail2ban \
    ca-certificates gnupg lsb-release

# ── Docker ─────────────────────────────────────────────────────────────────────
echo "→ Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
   https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

# ── Caddy ──────────────────────────────────────────────────────────────────────
echo "→ Installing Caddy..."
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    | tee /etc/apt/sources.list.d/caddy-stable.list > /dev/null
apt-get update -qq
apt-get install -y -qq caddy

mkdir -p /var/log/caddy
systemctl enable caddy

# ── Firewall ───────────────────────────────────────────────────────────────────
echo "→ Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment "SSH"
ufw allow 80/tcp    comment "HTTP (Caddy ACME)"
ufw allow 443/tcp   comment "HTTPS"
ufw --force enable

# ── Fail2ban ───────────────────────────────────────────────────────────────────
systemctl enable fail2ban
systemctl start fail2ban

# ── Deployment user ────────────────────────────────────────────────────────────
echo "→ Creating imptuser..."
if ! id imptuser &>/dev/null; then
    useradd -m -s /bin/bash -u 1001 imptuser
fi
usermod -aG docker imptuser
mkdir -p /home/imptuser/.ssh
chmod 700 /home/imptuser/.ssh

# Copy root SSH authorized_keys to imptuser so existing keys work
if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys /home/imptuser/.ssh/
    chmod 600 /home/imptuser/.ssh/authorized_keys
    chown -R imptuser:imptuser /home/imptuser/.ssh
fi

# ── Swap (for burst load during Docker builds) ─────────────────────────────────
echo "→ Setting up 2GB swap..."
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ── Systemd service (NFR079 — auto-start on reboot) ──────────────────────────
echo "→ Installing systemd service..."
# Copy service file after repo is cloned (post-deploy step)
cat > /etc/systemd/system/impt.service << 'UNIT'
[Unit]
Description=IMPT — Intelligent Mutation Prioritization Tool
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=imptuser
WorkingDirectory=/home/imptuser/impt
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
# Note: Do not enable yet — enable after repo is cloned with: systemctl enable impt

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Bootstrap complete! Next steps:                    ║"
echo "║                                                      ║"
echo "║  1. Switch to imptuser:  su - imptuser              ║"
echo "║  2. Generate deploy key: ssh-keygen -t ed25519 \\    ║"
echo "║        -f ~/.ssh/github_deploy -N \"\"               ║"
echo "║  3. Add key to GitHub repo → Deploy Keys            ║"
echo "║  4. Clone repo:  git clone git@github.com:...       ║"
echo "║  5. Set up .env: cp .env.example .env && nano .env  ║"
echo "║  6. Start:       docker compose up -d --build       ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
