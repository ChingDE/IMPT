#!/bin/bash
# deploy/setup_vps.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-time VPS setup script for Ubuntu 22.04 / 24.04
# Run as root on a fresh server:
#   curl -O https://your-server/setup_vps.sh && chmod +x setup_vps.sh && ./setup_vps.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
IMPT_DIR="/opt/impt"
IMPT_USER="impt"

echo "=== IMPT VPS Setup ==="

# ── 1. System update ──────────────────────────────────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y curl git ufw fail2ban

# ── 2. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
# Docker Compose plugin
apt-get install -y docker-compose-plugin

# ── 3. Firewall ───────────────────────────────────────────────────────────────
ufw --force enable
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (redirect to HTTPS)
ufw allow 443/tcp   # HTTPS
# Block direct access to API/Redis/Postgres from outside
ufw deny 8000/tcp
ufw deny 5432/tcp
ufw deny 6379/tcp

# ── 4. Application user ───────────────────────────────────────────────────────
if ! id "$IMPT_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$IMPT_USER"
  usermod -aG docker "$IMPT_USER"
fi

# ── 5. Clone / update repo ────────────────────────────────────────────────────
if [ -d "$IMPT_DIR" ]; then
  git -C "$IMPT_DIR" pull
else
  # Replace with your actual repo URL
  git clone https://github.com/novasoft/impt.git "$IMPT_DIR"
fi
chown -R "$IMPT_USER:$IMPT_USER" "$IMPT_DIR"

# ── 6. Create .env ────────────────────────────────────────────────────────────
if [ ! -f "$IMPT_DIR/.env" ]; then
  cp "$IMPT_DIR/.env.example" "$IMPT_DIR/.env"
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  PGPASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
  sed -i "s/CHANGE_ME_64_CHAR_RANDOM_HEX/$SECRET/" "$IMPT_DIR/.env"
  sed -i "s/CHANGE_ME_STRONG_PASSWORD/$PGPASS/" "$IMPT_DIR/.env"
  sed -i "s/CHANGE_ME/$PGPASS/g" "$IMPT_DIR/.env"
  echo "✓ .env created — REVIEW AND SET YOUR DOMAIN in .env before continuing"
fi

# ── 7. SSL certificates (Let's Encrypt via certbot) ───────────────────────────
# Uncomment and replace YOUR_DOMAIN after pointing DNS to this server
# apt-get install -y certbot
# certbot certonly --standalone -d YOUR_DOMAIN --non-interactive --agree-tos -m admin@YOUR_DOMAIN
# mkdir -p "$IMPT_DIR/deploy/nginx/ssl"
# cp /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem "$IMPT_DIR/deploy/nginx/ssl/"
# cp /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem   "$IMPT_DIR/deploy/nginx/ssl/"

# ── 8. Build sandbox image ────────────────────────────────────────────────────
echo "Building sandbox image (takes 3-5 min on first run)..."
cd "$IMPT_DIR"
docker build -t impt-sandbox:latest ./sandbox/

# ── 9. Start stack ────────────────────────────────────────────────────────────
cd "$IMPT_DIR"
docker compose up -d --build

echo ""
echo "=== Setup complete ==="
echo "API health: curl http://localhost/api/health"
echo "Logs:       docker compose logs -f api worker"
echo ""
echo "IMPORTANT: Edit .env and set your domain, then:"
echo "  1. Set up SSL (see step 7 comments)"
echo "  2. Run database migrations: docker compose exec api alembic upgrade head"
echo "  3. Restart: docker compose restart"
