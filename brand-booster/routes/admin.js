const router = require('express').Router();
const bcrypt = require('bcryptjs');
const pool = require('../config/db');

// GET /api/admin/stats
router.get('/stats', async (req, res) => {
  try {
    const [[totalRows], [activeRows], [usageRows], [recentLogs]] = await Promise.all([
      pool.query('SELECT COUNT(*) AS count FROM users'),
      pool.query("SELECT COUNT(*) AS count FROM users WHERE status = 'active'"),
      pool.query('SELECT COUNT(*) AS count FROM tool_usage'),
      pool.query(
        `SELECT al.action, al.ip_address, al.created_at, u.name, u.email
         FROM activity_logs al
         LEFT JOIN users u ON al.user_id = u.id
         ORDER BY al.created_at DESC LIMIT 10`
      ),
    ]);

    res.json({
      totalUsers: parseInt(totalRows[0].count),
      activeUsers: parseInt(activeRows[0].count),
      totalToolUses: parseInt(usageRows[0].count),
      recentLogs,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/admin/users
router.get('/users', async (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 20;
  const search = req.query.search || '';
  const offset = (page - 1) * limit;

  try {
    let usersRows, countRows;
    if (search) {
      const like = `%${search}%`;
      [[usersRows], [countRows]] = await Promise.all([
        pool.query(
          `SELECT id, name, email, role, status, last_login, created_at
           FROM users WHERE name LIKE ? OR email LIKE ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?`,
          [like, like, limit, offset]
        ),
        pool.query(
          'SELECT COUNT(*) AS count FROM users WHERE name LIKE ? OR email LIKE ?',
          [like, like]
        ),
      ]);
    } else {
      [[usersRows], [countRows]] = await Promise.all([
        pool.query(
          'SELECT id, name, email, role, status, last_login, created_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?',
          [limit, offset]
        ),
        pool.query('SELECT COUNT(*) AS count FROM users'),
      ]);
    }

    const total = parseInt(countRows[0].count);
    res.json({ users: usersRows, total, page, totalPages: Math.ceil(total / limit) });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// POST /api/admin/users
router.post('/users', async (req, res) => {
  const { name, email, password, role } = req.body;
  if (!name || !email || !password) {
    return res.status(400).json({ error: 'Name, email, and password required' });
  }

  try {
    const [exists] = await pool.query('SELECT id FROM users WHERE email = ?', [email.toLowerCase()]);
    if (exists[0]) return res.status(409).json({ error: 'Email already registered' });

    const hashed = await bcrypt.hash(password, 12);
    await pool.query(
      `INSERT INTO users (id, name, email, password, role) VALUES (UUID(), ?, ?, ?, ?)`,
      [name, email.toLowerCase(), hashed, role || 'user']
    );
    const [newUser] = await pool.query(
      'SELECT id, name, email, role FROM users WHERE email = ?',
      [email.toLowerCase()]
    );
    res.status(201).json({ success: true, user: newUser[0] });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// PATCH /api/admin/users/:id
router.patch('/users/:id', async (req, res) => {
  const { name, role, status } = req.body;
  if (req.params.id === req.user.id && status === 'inactive') {
    return res.status(400).json({ error: 'Cannot deactivate your own account' });
  }

  try {
    const updates = [];
    const params = [];
    if (name) { updates.push('name = ?'); params.push(name); }
    if (role) { updates.push('role = ?'); params.push(role); }
    if (status) { updates.push('status = ?'); params.push(status); }
    updates.push('updated_at = NOW()');
    params.push(req.params.id);

    await pool.query(`UPDATE users SET ${updates.join(', ')} WHERE id = ?`, params);
    const [updated] = await pool.query(
      'SELECT id, name, email, role, status FROM users WHERE id = ?',
      [req.params.id]
    );
    if (!updated[0]) return res.status(404).json({ error: 'User not found' });
    res.json({ success: true, user: updated[0] });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// DELETE /api/admin/users/:id
router.delete('/users/:id', async (req, res) => {
  if (req.params.id === req.user.id) {
    return res.status(400).json({ error: 'Cannot delete your own account' });
  }
  try {
    await pool.query('DELETE FROM users WHERE id = ?', [req.params.id]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/admin/tools
router.get('/tools', async (req, res) => {
  try {
    const [tools] = await pool.query('SELECT * FROM ai_tools ORDER BY sort_order');
    res.json({ tools });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// PATCH /api/admin/tools/:id
router.patch('/tools/:id', async (req, res) => {
  const { name, description, status } = req.body;
  try {
    await pool.query(
      `UPDATE ai_tools SET
        name = COALESCE(?, name),
        description = COALESCE(?, description),
        status = COALESCE(?, status)
       WHERE id = ?`,
      [name ?? null, description ?? null, status ?? null, req.params.id]
    );
    const [updated] = await pool.query('SELECT * FROM ai_tools WHERE id = ?', [req.params.id]);
    if (!updated[0]) return res.status(404).json({ error: 'Tool not found' });
    res.json({ success: true, tool: updated[0] });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/admin/logs
router.get('/logs', async (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 30;
  const offset = (page - 1) * limit;

  try {
    const [[logs], [totalRows]] = await Promise.all([
      pool.query(
        `SELECT al.*, u.name, u.email FROM activity_logs al
         LEFT JOIN users u ON al.user_id = u.id
         ORDER BY al.created_at DESC LIMIT ? OFFSET ?`,
        [limit, offset]
      ),
      pool.query('SELECT COUNT(*) AS count FROM activity_logs'),
    ]);

    const total = parseInt(totalRows[0].count);
    res.json({ logs, total, page, totalPages: Math.ceil(total / limit) });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
