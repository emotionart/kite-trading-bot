# Hostinger Shared Hosting - Deploy Guide

## Step 1: hPanel mein Node.js Setup

1. hPanel login karo → **Advanced** → **Node.js**
2. **Create Application** click karo:
   - Node.js version: `18.x` ya latest
   - Application mode: `Production`
   - Application root: `brand-booster`
   - Application URL: `agent.thebrandbooster.biz`
   - Application startup file: `server.js`

## Step 2: Environment Variables (hPanel mein)

Node.js app settings mein yeh variables add karo:

```
PORT=3000
NODE_ENV=production
APP_URL=https://agent.thebrandbooster.biz
DB_HOST=localhost
DB_PORT=5432
DB_NAME=brandbooster_db
DB_USER=brandbooster_user
DB_PASSWORD=<hostinger_db_password>
JWT_SECRET=<64_char_random_string>
JWT_EXPIRES_IN=7d
SESSION_SECRET=<32_char_random_string>
ADMIN_EMAIL=admin@thebrandbooster.biz
ADMIN_PASSWORD=<your_admin_password>
ADMIN_NAME=Super Admin
```

## Step 3: PostgreSQL Database

hPanel → **Databases** → **PostgreSQL**:
1. New database: `brandbooster_db`
2. New user: `brandbooster_user`
3. Password set karo
4. User ko database assign karo

## Step 4: Files Upload

**Option A - Git (recommended):**
```bash
# SSH terminal mein
cd ~/public_html  # ya subdomain folder
git clone https://github.com/emotionart/kite-trading-bot.git .
cd brand-booster
npm install --production
node scripts/setup-db.js
```

**Option B - File Manager:**
1. hPanel → File Manager
2. `brand-booster/` folder ko subdomain root mein upload karo
3. SSH se: `npm install && node scripts/setup-db.js`

## Step 5: Restart App

hPanel → Node.js → **Restart** button

## URLs

- Login: `https://agent.thebrandbooster.biz/login`
- Dashboard: `https://agent.thebrandbooster.biz/dashboard`
- Admin: `https://agent.thebrandbooster.biz/admin`

## Default Credentials

- Email: `admin@thebrandbooster.biz`
- Password: `Admin@123!` *(pehle login ke baad badlo)*
