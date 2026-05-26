require('dotenv').config();
const pool = require('../config/db');
const bcrypt = require('bcryptjs');

async function setupDatabase() {
  try {
    console.log('Setting up Brand Booster database...');

    await pool.query(`
      CREATE TABLE IF NOT EXISTS users (
        id CHAR(36) NOT NULL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        role VARCHAR(50) DEFAULT 'user',
        status VARCHAR(50) DEFAULT 'active',
        avatar VARCHAR(500),
        last_login DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
      )
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS sessions (
        id CHAR(36) NOT NULL PRIMARY KEY,
        user_id CHAR(36),
        token VARCHAR(500) NOT NULL,
        ip_address VARCHAR(50),
        user_agent TEXT,
        expires_at DATETIME NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
      )
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS activity_logs (
        id CHAR(36) NOT NULL PRIMARY KEY,
        user_id CHAR(36),
        action VARCHAR(255) NOT NULL,
        details TEXT,
        ip_address VARCHAR(50),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
      )
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS ai_tools (
        id CHAR(36) NOT NULL PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        description TEXT,
        icon VARCHAR(100),
        category VARCHAR(100),
        status VARCHAR(50) DEFAULT 'active',
        sort_order INT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS tool_usage (
        id CHAR(36) NOT NULL PRIMARY KEY,
        user_id CHAR(36),
        tool_id CHAR(36),
        tokens_used INT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (tool_id) REFERENCES ai_tools(id) ON DELETE CASCADE
      )
    `);

    // Create admin user
    const adminEmail = process.env.ADMIN_EMAIL || 'admin@thebrandbooster.biz';
    const [existing] = await pool.query('SELECT id FROM users WHERE email = ?', [adminEmail]);

    if (existing.length === 0) {
      const hashed = await bcrypt.hash(process.env.ADMIN_PASSWORD || 'Admin@123!', 12);
      await pool.query(
        `INSERT INTO users (id, name, email, password, role) VALUES (UUID(), ?, ?, ?, 'admin')`,
        [process.env.ADMIN_NAME || 'Super Admin', adminEmail, hashed]
      );
      console.log(`Admin user created: ${adminEmail}`);
    }

    // Seed AI tools
    const tools = [
      { name: 'AI Chat', description: 'Intelligent AI conversation assistant', icon: 'chat', category: 'Communication', sort_order: 1 },
      { name: 'Content Writer', description: 'Generate blogs, captions, and marketing copy', icon: 'edit', category: 'Content', sort_order: 2 },
      { name: 'Brand Analyzer', description: 'Analyze and improve your brand identity', icon: 'analytics', category: 'Analytics', sort_order: 3 },
      { name: 'Social Media AI', description: 'Auto-generate social media posts', icon: 'share', category: 'Social', sort_order: 4 },
      { name: 'SEO Optimizer', description: 'Optimize content for search engines', icon: 'search', category: 'Marketing', sort_order: 5 },
      { name: 'Email Campaign', description: 'Create AI-powered email campaigns', icon: 'mail', category: 'Marketing', sort_order: 6 },
    ];

    for (const tool of tools) {
      await pool.query(
        `INSERT IGNORE INTO ai_tools (id, name, description, icon, category, sort_order)
         VALUES (UUID(), ?, ?, ?, ?, ?)`,
        [tool.name, tool.description, tool.icon, tool.category, tool.sort_order]
      );
    }

    console.log('Database setup complete!');
  } finally {
    await pool.end();
  }
}

setupDatabase().catch(console.error);
