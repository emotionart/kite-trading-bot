#!/bin/bash
# Brand Booster AI - Full VPS Auto-Deploy Script
# Run as root on fresh Hostinger VPS

set -e  # Exit on any error

APP_DIR="/var/www/brand-booster"
APP_URL="agent.thebrandbooster.biz"
GITHUB_REPO="https://github.com/emotionart/kite-trading-bot.git"
APP_SUBFOLDER="brand-booster"

echo "============================================="
echo "  Brand Booster AI - VPS Auto Deploy"
echo "  Target: $APP_URL"
echo "============================================="
echo ""

# ── 1. System Update ──────────────────────────────────────
echo "[1/8] System update karo..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Node.js 20 Install ────────────────────────────────
echo "[2/8] Node.js 20 install karo..."
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 18 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
echo "  Node: $(node -v) | NPM: $(npm -v)"

# ── 3. PostgreSQL Install ────────────────────────────────
echo "[3/8] PostgreSQL install karo..."
if ! command -v psql &>/dev/null; then
  apt-get install -y postgresql postgresql-contrib
fi
systemctl start postgresql
systemctl enable postgresql

# DB setup
DB_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 24)
sudo -u postgres psql -c "CREATE USER brandbooster_user WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE brandbooster_db OWNER brandbooster_user;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE brandbooster_db TO brandbooster_user;" 2>/dev/null || true
echo "  DB Password: $DB_PASSWORD (neeche .env mein save hoga)"

# ── 4. PM2 Install ───────────────────────────────────────
echo "[4/8] PM2 install karo..."
npm install -g pm2 -q

# ── 5. Nginx Install ─────────────────────────────────────
echo "[5/8] Nginx install aur configure karo..."
apt-get install -y nginx
cat > /etc/nginx/sites-available/brand-booster << EOF
server {
    listen 80;
    server_name $APP_URL www.$APP_URL;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }
}
EOF

ln -sf /etc/nginx/sites-available/brand-booster /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
systemctl enable nginx

# ── 6. App Clone & Setup ─────────────────────────────────
echo "[6/8] Code clone karo GitHub se..."
mkdir -p /var/www
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR" && git pull origin claude/adoring-cannon-5rpCO
else
  git clone -b claude/adoring-cannon-5rpCO "$GITHUB_REPO" /tmp/repo-clone
  mv /tmp/repo-clone/$APP_SUBFOLDER "$APP_DIR"
  rm -rf /tmp/repo-clone
fi

# ── 7. .env Setup ────────────────────────────────────────
echo "[7/8] Environment variables setup karo..."
JWT_SECRET=$(openssl rand -base64 48 | tr -dc 'a-zA-Z0-9' | head -c 64)
SESSION_SECRET=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)

cat > "$APP_DIR/.env" << ENV
PORT=3000
NODE_ENV=production
APP_URL=https://$APP_URL

DB_HOST=localhost
DB_PORT=5432
DB_NAME=brandbooster_db
DB_USER=brandbooster_user
DB_PASSWORD=$DB_PASSWORD

JWT_SECRET=$JWT_SECRET
JWT_EXPIRES_IN=7d
SESSION_SECRET=$SESSION_SECRET

ADMIN_EMAIL=admin@thebrandbooster.biz
ADMIN_PASSWORD=Admin@123!
ADMIN_NAME=Super Admin
ENV

echo "  .env file created at $APP_DIR/.env"

# ── 8. App Start ─────────────────────────────────────────
echo "[8/8] App install aur start karo..."
cd "$APP_DIR"
npm install --production

# Database init
node scripts/setup-db.js

# PM2 se start
pm2 delete brand-booster 2>/dev/null || true
pm2 start server.js --name brand-booster --env production
pm2 save
pm2 startup | tail -1 | bash 2>/dev/null || true

echo ""
echo "============================================="
echo "  DEPLOY COMPLETE!"
echo "============================================="
echo ""
echo "  App URL  : http://$APP_URL (SSL neeche setup hoga)"
echo "  Admin    : admin@thebrandbooster.biz"
echo "  Password : Admin@123!  <- Badlo pehle login pe!"
echo ""
echo "  SSL ke liye run karo:"
echo "  apt-get install -y certbot python3-certbot-nginx"
echo "  certbot --nginx -d $APP_URL"
echo ""
echo "  PM2 status: pm2 status"
echo "  App logs  : pm2 logs brand-booster"
echo "============================================="
