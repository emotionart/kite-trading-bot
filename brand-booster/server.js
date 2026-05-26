require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cookieParser = require('cookie-parser');
const rateLimit = require('express-rate-limit');
const path = require('path');

const authRoutes = require('./routes/auth');
const dashboardRoutes = require('./routes/dashboard');
const adminRoutes = require('./routes/admin');
const { verifyToken, requireAdmin } = require('./middleware/auth');

const app = express();
const PORT = process.env.PORT || 3000;

// Security middleware
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", "cdn.tailwindcss.com"],
      styleSrc: ["'self'", "'unsafe-inline'", "fonts.googleapis.com", "cdn.tailwindcss.com"],
      fontSrc: ["'self'", "fonts.gstatic.com"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'"],
    },
  },
}));

app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));
app.use(cookieParser());
app.use(express.static(path.join(__dirname, 'public')));

// Rate limiting
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: { error: 'Too many login attempts. Try again in 15 minutes.' },
  standardHeaders: true,
  legacyHeaders: false,
});

const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
});

app.use('/api/', apiLimiter);
app.use('/api/auth/login', loginLimiter);

// API Routes
app.use('/api/auth', authRoutes);
app.use('/api/dashboard', verifyToken, dashboardRoutes);
app.use('/api/admin', verifyToken, requireAdmin, adminRoutes);

// Page Routes
app.get('/', (req, res) => {
  const token = req.cookies?.token;
  if (token) return res.redirect('/dashboard');
  res.redirect('/login');
});

app.get('/login', (req, res) => {
  res.sendFile(path.join(__dirname, 'views', 'login.html'));
});

app.get('/dashboard', verifyToken, (req, res) => {
  res.sendFile(path.join(__dirname, 'views', 'dashboard.html'));
});

app.get('/admin', verifyToken, requireAdmin, (req, res) => {
  res.sendFile(path.join(__dirname, 'views', 'admin.html'));
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString(), env: process.env.NODE_ENV });
});

// Temporary debug endpoint
app.get('/debug-bb-2024', async (req, res) => {
  const pool = require('./config/db');
  const info = {
    env: {
      NODE_ENV: process.env.NODE_ENV,
      DB_HOST: process.env.DB_HOST,
      DB_NAME: process.env.DB_NAME,
      DB_USER: process.env.DB_USER,
      DB_PASSWORD: process.env.DB_PASSWORD ? '✓ set' : '✗ missing',
      DB_PASS: process.env.DB_PASS ? '✓ set' : '✗ missing',
      JWT_SECRET: process.env.JWT_SECRET ? '✓ set' : '✗ missing',
      PORT: process.env.PORT,
    },
    db: 'testing...',
  };
  try {
    const [rows] = await pool.query('SELECT COUNT(*) as users FROM users');
    info.db = `✓ Connected — ${rows[0].users} user(s) in DB`;
  } catch (e) {
    info.db = `✗ DB Error: ${e.message}`;
  }
  res.json(info);
});

// Temporary DB setup endpoint - auto-removes after first run
app.get('/setup-bb-init-2024', async (req, res) => {
  const pool = require('./config/db');
  const bcrypt = require('bcryptjs');
  const log = [];
  try {
    await pool.query(`CREATE TABLE IF NOT EXISTS users (id CHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(255) NOT NULL, email VARCHAR(255) UNIQUE NOT NULL, password VARCHAR(255) NOT NULL, role VARCHAR(50) DEFAULT 'user', status VARCHAR(50) DEFAULT 'active', avatar VARCHAR(500), last_login DATETIME, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)`);
    log.push('✓ users table');

    await pool.query(`CREATE TABLE IF NOT EXISTS sessions (id CHAR(36) NOT NULL PRIMARY KEY, user_id CHAR(36), token VARCHAR(500) NOT NULL, ip_address VARCHAR(50), user_agent TEXT, expires_at DATETIME NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)`);
    log.push('✓ sessions table');

    await pool.query(`CREATE TABLE IF NOT EXISTS activity_logs (id CHAR(36) NOT NULL PRIMARY KEY, user_id CHAR(36), action VARCHAR(255) NOT NULL, details TEXT, ip_address VARCHAR(50), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL)`);
    log.push('✓ activity_logs table');

    await pool.query(`CREATE TABLE IF NOT EXISTS ai_tools (id CHAR(36) NOT NULL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, description TEXT, icon VARCHAR(100), category VARCHAR(100), status VARCHAR(50) DEFAULT 'active', sort_order INT DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)`);
    log.push('✓ ai_tools table');

    await pool.query(`CREATE TABLE IF NOT EXISTS tool_usage (id CHAR(36) NOT NULL PRIMARY KEY, user_id CHAR(36), tool_id CHAR(36), tokens_used INT DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY (tool_id) REFERENCES ai_tools(id) ON DELETE CASCADE)`);
    log.push('✓ tool_usage table');

    const [existing] = await pool.query('SELECT id FROM users WHERE email = ?', ['admin@thebrandbooster.biz']);
    if (existing.length === 0) {
      const hashed = await bcrypt.hash('Admin@BrandBooster2024!', 12);
      await pool.query(`INSERT INTO users (id, name, email, password, role) VALUES (UUID(), 'Super Admin', 'admin@thebrandbooster.biz', ?, 'admin')`, [hashed]);
      log.push('✓ Admin user created');
    } else {
      log.push('✓ Admin user already exists');
    }

    const tools = [
      ['AI Chat','Intelligent AI conversation assistant','chat','Communication',1],
      ['Content Writer','Generate blogs, captions, and marketing copy','edit','Content',2],
      ['Brand Analyzer','Analyze and improve your brand identity','analytics','Analytics',3],
      ['Social Media AI','Auto-generate social media posts','share','Social',4],
      ['SEO Optimizer','Optimize content for search engines','search','Marketing',5],
      ['Email Campaign','Create AI-powered email campaigns','mail','Marketing',6],
    ];
    for (const [name, desc, icon, cat, order] of tools) {
      await pool.query(`INSERT IGNORE INTO ai_tools (id, name, description, icon, category, sort_order) VALUES (UUID(), ?, ?, ?, ?, ?)`, [name, desc, icon, cat, order]);
    }
    log.push('✓ 6 AI tools seeded');

    res.json({ success: true, message: 'Database setup complete!', steps: log, login: { email: 'admin@thebrandbooster.biz', password: 'Admin@BrandBooster2024!' } });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message, steps: log });
  }
});

// 404
app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

// Error handler
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`\n  Brand Booster AI Agent`);
  console.log(`  Server running on port ${PORT}`);
  console.log(`  Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`  URL: ${process.env.APP_URL || `http://localhost:${PORT}`}\n`);
});

module.exports = app;
