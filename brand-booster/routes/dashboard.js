const router = require('express').Router();
const pool = require('../config/db');

// GET /api/dashboard/stats
router.get('/stats', async (req, res) => {
  try {
    const toolsUsed = await pool.query(
      'SELECT COUNT(*) FROM tool_usage WHERE user_id = $1',
      [req.user.id]
    );
    const totalTokens = await pool.query(
      'SELECT COALESCE(SUM(tokens_used), 0) as total FROM tool_usage WHERE user_id = $1',
      [req.user.id]
    );
    const recentActivity = await pool.query(
      `SELECT action, created_at FROM activity_logs WHERE user_id = $1
       ORDER BY created_at DESC LIMIT 5`,
      [req.user.id]
    );

    res.json({
      toolsUsed: parseInt(toolsUsed.rows[0].count),
      tokensUsed: parseInt(totalTokens.rows[0].total),
      recentActivity: recentActivity.rows,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Server error' });
  }
});

// GET /api/dashboard/tools
router.get('/tools', async (req, res) => {
  try {
    const result = await pool.query(
      'SELECT * FROM ai_tools WHERE status = $1 ORDER BY sort_order',
      ['active']
    );
    res.json({ tools: result.rows });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

// POST /api/dashboard/tools/:id/use
router.post('/tools/:id/use', async (req, res) => {
  try {
    const tool = await pool.query(
      'SELECT * FROM ai_tools WHERE id = $1 AND status = $2',
      [req.params.id, 'active']
    );
    if (!tool.rows[0]) return res.status(404).json({ error: 'Tool not found' });

    await pool.query(
      'INSERT INTO tool_usage (user_id, tool_id) VALUES ($1, $2)',
      [req.user.id, req.params.id]
    );
    res.json({ success: true, tool: tool.rows[0] });
  } catch (err) {
    res.status(500).json({ error: 'Server error' });
  }
});

module.exports = router;
