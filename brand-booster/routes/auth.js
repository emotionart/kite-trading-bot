const router = require('express').Router();
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const pool = require('../config/db');

// POST /api/auth/login
router.post('/login', async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) {
    return res.status(400).json({ error: 'Email and password required' });
  }

  try {
    const [users] = await pool.query(
      'SELECT * FROM users WHERE email = ? AND status = ?',
      [email.toLowerCase().trim(), 'active']
    );

    const user = users[0];
    if (!user || !(await bcrypt.compare(password, user.password))) {
      await pool.query(
        'INSERT INTO activity_logs (id, action, ip_address, details) VALUES (UUID(), ?, ?, ?)',
        ['login_failed', req.ip, `Failed login attempt for ${email}`]
      );
      return res.status(401).json({ error: 'Invalid email or password' });
    }

    const token = jwt.sign(
      { userId: user.id, role: user.role },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRES_IN || '7d' }
    );

    await pool.query('UPDATE users SET last_login = NOW() WHERE id = ?', [user.id]);
    await pool.query(
      'INSERT INTO activity_logs (id, user_id, action, ip_address) VALUES (UUID(), ?, ?, ?)',
      [user.id, 'login_success', req.ip]
    );

    res.cookie('token', token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60 * 1000,
    });

    res.json({
      success: true,
      redirect: user.role === 'admin' ? '/admin' : '/dashboard',
      user: { id: user.id, name: user.name, email: user.email, role: user.role },
    });
  } catch (err) {
    console.error('Login error:', err);
    res.status(500).json({ error: 'Server error. Please try again.' });
  }
});

// POST /api/auth/logout
router.post('/logout', (req, res) => {
  res.clearCookie('token');
  res.json({ success: true, redirect: '/login' });
});

// GET /api/auth/me
router.get('/me', async (req, res) => {
  const token = req.cookies?.token;
  if (!token) return res.status(401).json({ error: 'Not authenticated' });

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    const [users] = await pool.query(
      'SELECT id, name, email, role, status, avatar, last_login, created_at FROM users WHERE id = ?',
      [decoded.userId]
    );
    if (!users[0]) return res.status(401).json({ error: 'User not found' });
    res.json({ user: users[0] });
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
});

// POST /api/auth/change-password
router.post('/change-password', async (req, res) => {
  const token = req.cookies?.token;
  if (!token) return res.status(401).json({ error: 'Not authenticated' });

  const { currentPassword, newPassword } = req.body;
  if (!currentPassword || !newPassword || newPassword.length < 8) {
    return res.status(400).json({ error: 'Password must be at least 8 characters' });
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    const [users] = await pool.query('SELECT * FROM users WHERE id = ?', [decoded.userId]);
    const user = users[0];

    if (!user || !(await bcrypt.compare(currentPassword, user.password))) {
      return res.status(401).json({ error: 'Current password is incorrect' });
    }

    const hashed = await bcrypt.hash(newPassword, 12);
    await pool.query('UPDATE users SET password = ?, updated_at = NOW() WHERE id = ?', [hashed, user.id]);
    res.json({ success: true, message: 'Password updated successfully' });
  } catch {
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
