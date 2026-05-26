#!/bin/bash
# Brand Booster AI - One-Command Deploy
# Run this in hPanel Terminal or SSH

set -e

GITHUB_REPO="https://github.com/emotionart/kite-trading-bot.git"
BRANCH="claude/adoring-cannon-5rpCO"
APP_SUBFOLDER="brand-booster"

# Find domain folder
if [ -d "$HOME/domains/agent.thebrandbooster.biz/public_html" ]; then
  DEPLOY_DIR="$HOME/domains/agent.thebrandbooster.biz/public_html"
elif [ -d "$HOME/public_html/agent" ]; then
  DEPLOY_DIR="$HOME/public_html/agent"
else
  mkdir -p "$HOME/domains/agent.thebrandbooster.biz/public_html"
  DEPLOY_DIR="$HOME/domains/agent.thebrandbooster.biz/public_html"
fi

echo "=== Brand Booster AI Deploy ==="
echo "Target: $DEPLOY_DIR"
echo ""

# Step 1: Clone or update files
echo "[1/4] Cloning files from GitHub..."
if [ -d "$DEPLOY_DIR/.git" ]; then
  cd "$DEPLOY_DIR" && git pull origin $BRANCH
else
  TMP=$(mktemp -d)
  git clone --depth=1 -b $BRANCH $GITHUB_REPO $TMP
  cp -r $TMP/$APP_SUBFOLDER/. $DEPLOY_DIR/
  rm -rf $TMP
  cd "$DEPLOY_DIR"
fi

# Step 2: Create .env
echo "[2/4] Creating .env file..."
cat > "$DEPLOY_DIR/.env" << 'ENVEOF'
PORT=3000
NODE_ENV=production
APP_URL=https://agent.thebrandbooster.biz

DB_HOST=localhost
DB_PORT=3306
DB_NAME=u102761338_agent
DB_USER=u102761338_agent
DB_PASSWORD=BrandBooster@2024

JWT_SECRET=BbAI2024SecureJWTKey_xK9mP3qR7vN1wL5zA8jE2tY6uH4cF0sBdGiOe
JWT_EXPIRES_IN=7d
SESSION_SECRET=BbSession2024_mX3kP9vQ2nR8wL

ADMIN_EMAIL=admin@thebrandbooster.biz
ADMIN_PASSWORD=Admin@BrandBooster2024!
ADMIN_NAME=Super Admin
ENVEOF
echo "  .env created"

# Step 3: Install dependencies
echo "[3/4] Installing npm packages..."
cd "$DEPLOY_DIR"
NODE_PATH=$(which node 2>/dev/null || ls /opt/alt/node*/bin/node 2>/dev/null | tail -1 || ls ~/.nvm/versions/node/*/bin/node 2>/dev/null | tail -1)
NPM_PATH=$(which npm 2>/dev/null || ls /opt/alt/node*/bin/npm 2>/dev/null | tail -1 || ls ~/.nvm/versions/node/*/bin/npm 2>/dev/null | tail -1)
echo "  Node: $NODE_PATH | npm: $NPM_PATH"
$NPM_PATH install --production --no-audit --no-fund 2>&1 | tail -5

# Step 4: Setup database
echo "[4/4] Setting up MySQL database..."
$NODE_PATH scripts/setup-db.js

echo ""
echo "==================================="
echo "  FILES DEPLOYED SUCCESSFULLY!"
echo "==================================="
echo ""
echo "  NEXT: hPanel mein Node.js app setup karo:"
echo "  1. hPanel → Advanced → Node.js"
echo "  2. Create Application:"
echo "     - Node.js Version: 18.x or 20.x"
echo "     - App Root: ${DEPLOY_DIR#$HOME/}"
echo "     - Startup File: server.js"
echo "     - App URL: agent.thebrandbooster.biz"
echo "  3. SAVE + START karo"
echo ""
echo "  Login: admin@thebrandbooster.biz"
echo "  Pass : Admin@BrandBooster2024!"
echo "==================================="
