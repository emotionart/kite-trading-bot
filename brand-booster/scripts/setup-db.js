require('dotenv').config();
const pool = require('../config/db');
const bcrypt = require('bcryptjs');

async function setupDatabase() {
  const client = await pool.connect();
  try {
    console.log('Setting up Brand Booster database...');

    await client.query(`
      CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        role VARCHAR(50) DEFAULT 'user',
        status VARCHAR(50) DEFAULT 'active',
        avatar VARCHAR(500),
        last_login TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await client.query(`
      CREATE TABLE IF NOT EXISTS sessions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        token VARCHAR(500) NOT NULL,
        ip_address VARCHAR(50),
        user_agent TEXT,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await client.query(`
      CREATE TABLE IF NOT EXISTS activity_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        action VARCHAR(255) NOT NULL,
        details TEXT,
        ip_address VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await client.query(`
      CREATE TABLE IF NOT EXISTS ai_tools (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        description TEXT,
        icon VARCHAR(100),
        category VARCHAR(100),
        status VARCHAR(50) DEFAULT 'active',
        sort_order INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    await client.query(`
      CREATE TABLE IF NOT EXISTS tool_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        tool_id UUID REFERENCES ai_tools(id) ON DELETE CASCADE,
        tokens_used INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW()
      )
    `);

    // Create admin user
    const adminEmail = process.env.ADMIN_EMAIL || 'admin@thebrandbooster.biz';
    const existing = await client.query('SELECT id FROM users WHERE email = $1', [adminEmail]);

    if (existing.rows.length === 0) {
      const hashed = await bcrypt.hash(process.env.ADMIN_PASSWORD || 'Admin@123!', 12);
      await client.query(
        `INSERT INTO users (name, email, password, role) VALUES ($1, $2, $3, 'admin')`,
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
      await client.query(
        `INSERT INTO ai_tools (name, description, icon, category, sort_order)
         SELECT $1, $2, $3, $4, $5
         WHERE NOT EXISTS (SELECT 1 FROM ai_tools WHERE name = $1)`,
        [tool.name, tool.description, tool.icon, tool.category, tool.sort_order]
      );
    }

    console.log('Database setup complete!');
  } finally {
    client.release();
    await pool.end();
  }
}

setupDatabase().catch(console.error);
