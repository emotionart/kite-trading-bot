const jwt = require('jsonwebtoken');
const pool = require('../config/db');

const verifyToken = async (req, res, next) => {
  const token = req.cookies?.token || req.headers.authorization?.split(' ')[1];

  if (!token) {
    if (req.headers.accept?.includes('application/json')) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    return res.redirect('/login');
  }

  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    const [users] = await pool.query(
      'SELECT id, name, email, role, status, avatar FROM users WHERE id = ? AND status = ?',
      [decoded.userId, 'active']
    );

    if (!users[0]) {
      res.clearCookie('token');
      return res.redirect('/login');
    }

    req.user = users[0];
    next();
  } catch {
    res.clearCookie('token');
    if (req.headers.accept?.includes('application/json')) {
      return res.status(401).json({ error: 'Invalid or expired token' });
    }
    return res.redirect('/login');
  }
};

const requireAdmin = (req, res, next) => {
  if (req.user?.role !== 'admin') {
    if (req.headers.accept?.includes('application/json')) {
      return res.status(403).json({ error: 'Admin access required' });
    }
    return res.redirect('/dashboard');
  }
  next();
};

const logActivity = (action) => async (req, res, next) => {
  if (req.user) {
    pool.query(
      'INSERT INTO activity_logs (id, user_id, action, ip_address) VALUES (UUID(), ?, ?, ?)',
      [req.user.id, action, req.ip]
    ).catch(() => {});
  }
  next();
};

module.exports = { verifyToken, requireAdmin, logActivity };
