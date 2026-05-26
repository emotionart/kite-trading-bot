const router = require('express').Router();
const pool = require('../config/db');

// GET /api/dashboard/stats
router.get('/stats', async (req, res) => {
  try {
    const [[toolsUsed], [totalTokens], [recentActivity]] = await Promise.all([
      pool.query('SELECT COUNT(*) AS count FROM tool_usage WHERE user_id = ?', [req.user.id]),
      pool.query('SELECT COALESCE(SUM(tokens_used), 0) AS total FROM tool_usage WHERE user_id = ?', [req.user.id]),
      pool.query(
        'SELECT action, created_at FROM activity_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 5',
        [req.user.id]
      ),
    ]);

    res.json({
      toolsUsed: parseInt(toolsUsed[0].count),
      tokensUsed: parseInt(totalTokens[0].total),
      recentActivity,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/dashboard/tools
router.get('/tools', async (req, res) => {
  try {
    const [tools] = await pool.query(
      'SELECT * FROM ai_tools WHERE status = ? ORDER BY sort_order',
      ['active']
    );
    res.json({ tools });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// POST /api/dashboard/tools/:id/use
router.post('/tools/:id/use', async (req, res) => {
  try {
    const [toolRows] = await pool.query(
      'SELECT * FROM ai_tools WHERE id = ? AND status = ?',
      [req.params.id, 'active']
    );
    if (!toolRows[0]) return res.status(404).json({ error: 'Tool not found' });

    await pool.query(
      'INSERT INTO tool_usage (id, user_id, tool_id) VALUES (UUID(), ?, ?)',
      [req.user.id, req.params.id]
    );
    res.json({ success: true, tool: toolRows[0] });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
