# Hostinger Shared Hosting - Deploy Guide
# Target: agent.thebrandbooster.biz

## Step 1: MySQL Database Banao

hPanel → **Databases** → **MySQL Databases**:

1. **Database name**: `brandbooster_db`
2. **Username**: `brandbooster_user`
3. **Password**: apna strong password set karo (yad rakho)
4. User ko database assign karo — **All Privileges**

Note karo: Hostinger actual DB name aur user prefix add karta hai, jaise:
- `u123456789_brandbooster_db`
- `u123456789_bb_user`

Yahi values .env mein use karo.

---

## Step 2: Node.js App Setup

hPanel → **Advanced** → **Node.js**:

1. **Create Application** click karo:
   - Node.js version: `18.x` ya `20.x`
   - Application mode: `Production`
   - Application root: `public_html/agent` (ya subdomain folder)
   - Application URL: `agent.thebrandbooster.biz`
   - Application startup file: `server.js`

2. **Environment Variables** add karo (Node.js app settings mein):

```
PORT=3000
NODE_ENV=production
APP_URL=https://agent.thebrandbooster.biz
DB_HOST=localhost
DB_PORT=3306
DB_NAME=u123456789_brandbooster_db
DB_USER=u123456789_bb_user
DB_PASSWORD=<aapka_db_password>
JWT_SECRET=<64_random_chars>
JWT_EXPIRES_IN=7d
SESSION_SECRET=<32_random_chars>
ADMIN_EMAIL=admin@thebrandbooster.biz
ADMIN_PASSWORD=Admin@123!
ADMIN_NAME=Super Admin
```

---

## Step 3: Files Upload

**Option A - hPanel Git Integration (Recommended):**
1. hPanel → **Git** → **Manage Repositories**
2. Clone: `https://github.com/emotionart/kite-trading-bot.git`
3. Branch: `claude/adoring-cannon-5rpCO`
4. Path: subdomain folder
5. Clone ke baad: `brand-booster/` folder ke andar ke saare files move karo root mein

**Option B - File Manager:**
1. hPanel → **File Manager**
2. `agent.thebrandbooster.biz` subdomain folder kholо
3. `brand-booster/` ke andar ke saare files upload karo directly

---

## Step 4: Dependencies Install & DB Setup

hPanel → Node.js → aapki app → **Run NPM command**:

```
install --production
```

Phir run karo:
```
run setup-db
```

(Ya SSH se: `node scripts/setup-db.js`)

---

## Step 5: App Start

hPanel → Node.js → aapki app → **Restart** button

---

## URLs

| Page | URL |
|------|-----|
| Login | https://agent.thebrandbooster.biz/login |
| Dashboard | https://agent.thebrandbooster.biz/dashboard |
| Admin | https://agent.thebrandbooster.biz/admin |
| Health Check | https://agent.thebrandbooster.biz/health |

## Default Login

- Email: `admin@thebrandbooster.biz`
- Password: `Admin@123!`
- **Pehle login ke baad password zaroor badlo!**
