#!/bin/bash
# Brand Booster AI - Hostinger Shared Hosting Deploy Script
# Run this on Hostinger SSH terminal

echo "=== Brand Booster AI Deploy ==="

# 1. Install dependencies
echo "[1/4] Installing dependencies..."
npm install --production

# 2. Setup .env if not exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[!] .env file banaya - please edit karo: nano .env"
  exit 1
fi

# 3. Setup database
echo "[2/4] Setting up database..."
node scripts/setup-db.js

# 4. Start/restart app
echo "[3/4] Starting app..."
if command -v pm2 &> /dev/null; then
  pm2 delete brand-booster 2>/dev/null || true
  pm2 start server.js --name brand-booster --env production
  pm2 save
  echo "[4/4] App started with PM2"
else
  echo "[4/4] PM2 nahi mila. hPanel mein Node.js App Manager se start karo."
  echo "      Entry point: server.js"
fi

echo ""
echo "=== Deploy Complete ==="
echo "URL: https://agent.thebrandbooster.biz"
echo "Admin: admin@thebrandbooster.biz / Admin@123!"
