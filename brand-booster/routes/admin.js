const router = require('express').Router();
const bcrypt = require('bcryptjs');
const pool = require('../config/db');

// GET /api/admin/stats
router.get('/stats', async (req, res) => {
  try {
    const [users, activeUsers, totalToolUses, recentLogs] = await Promise.all([
      pool.query('SELECT COUNT(*) FROM users'),
      pool.query("SELECT COUNT(*) FROM users WHERE status = 'active'"),
      pool.query('SELECT COUNT(*) FROM tool_usage'),
      pool.query(
        `SELECT al.action, al.ip_address, al.created_at, u.name, u.email
         FROM activity_logs al
         LEFT JOIN users u ON al.user_id = u.id
         ORDER BY al.created_at DESC LIMIT 10`
      ),
    ]);

    res.json({
      totalUsers: parseInt(users.rows[0].count),
      activeUsers: parseInt(activeUsers.rows[0].count),
      totalToolUses: parseInt(totalToolUses.rows[0].count),
      recentLogs: recentLogs.rows,
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
    const where = search ? `WHERE name ILIKE $3 OR email ILIKE $3` : '';
    const params = search ? [limit, offset, `%${search}%`] : [limit, offset];

    const users = await pool.query(
      `SELECT id, name, email, role, status, last_login, created_at
       FROM users ${where} ORDER BY created_at DESC LIMIT $1 OFFSET $2`,
      params
    );
    const total = await pool.query(
      `SELECT COUNT(*) FROM users ${search ? 'WHERE name ILIKE $1 OR email ILIKE $1' : ''}`,
      search ? [`%${search}%`] : []
    );

    res.json({
      users: users.rows,
      total: parseInt(total.rows[0].count),
      page,
      totalPages: Math.ceil(parseInt(total.rows[0].count) / limit),
    });
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
    const exists = await pool.query('SELECT id FROM users WHERE email = $1', [email.toLowerCase()]);
    if (exists.rows[0]) return res.status(409).json({ error: 'Email already registered' });

    const hashed = await bcrypt.hash(password, 12);
    const result = await pool.query(
      `INSERT INTO users (name, email, password, role) VALUES ($1, $2, $3, $4) RETURNING id, name, email, role`,
      [name, email.toLowerCase(), hashed, role || 'user']
    );
    res.status(201).json({ success: true, user: result.rows[0] });
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
    let idx = 1;
    if (name) { updates.push(`name = $${idx++}`); params.push(name); }
    if (role) { updates.push(`role = $${idx++}`); params.push(role); }
    if (status) { updates.push(`status = $${idx++}`); params.push(status); }
    updates.push(`updated_at = NOW()`);
    params.push(req.params.id);

    const result = await pool.query(
      `UPDATE users SET ${updates.join(', ')} WHERE id = $${idx} RETURNING id, name, email, role, status`,
      params
    );
    if (!result.rows[0]) return res.status(404).json({ error: 'User not found' });
    res.json({ success: true, user: result.rows[0] });
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
    await pool.query('DELETE FROM users WHERE id = $1', [req.params.id]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/admin/tools
router.get('/tools', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM ai_tools ORDER BY sort_order');
    res.json({ tools: result.rows });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// PATCH /api/admin/tools/:id
router.patch('/tools/:id', async (req, res) => {
  const { name, description, status } = req.body;
  try {
    const result = await pool.query(
      `UPDATE ai_tools SET
        name = COALESCE($1, name),
        description = COALESCE($2, description),
        status = COALESCE($3, status)
       WHERE id = $4 RETURNING *`,
      [name, description, status, req.params.id]
    );
    if (!result.rows[0]) return res.status(404).json({ error: 'Tool not found' });
    res.json({ success: true, tool: result.rows[0] });
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
    const result = await pool.query(
      `SELECT al.*, u.name, u.email FROM activity_logs al
       LEFT JOIN users u ON al.user_id = u.id
       ORDER BY al.created_at DESC LIMIT $1 OFFSET $2`,
      [limit, offset]
    );
    const total = await pool.query('SELECT COUNT(*) FROM activity_logs');
    res.json({
      logs: result.rows,
      total: parseInt(total.rows[0].count),
      page,
      totalPages: Math.ceil(parseInt(total.rows[0].count) / limit),
    });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
