const express = require('express');
const axios = require('axios');
const ChatHistory = require('../models/ChatHistory');

const router = express.Router();

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';
const HISTORY_WINDOW = 20; // Max recent messages to send as context (10 exchanges)

// ---------------------------------------------------------------------------
// POST /api/repo/submit — Ingest a GitHub repository
// ---------------------------------------------------------------------------
router.post('/repo/submit', async (req, res) => {
    const { repo_url } = req.body;

    if (!repo_url) {
        return res.status(400).json({ error: 'repo_url is required' });
    }

    try {
        const response = await axios.post(`${AI_SERVICE_URL}/agent/ingest`, { repo_url });
        res.json(response.data);
    } catch (error) {
        console.error('Error in /repo/submit:', error.message);
        res.status(500).json({ error: 'Failed to ingest repository' });
    }
});

// ---------------------------------------------------------------------------
// POST /api/chat/message — Send a message and get an AI response
// ---------------------------------------------------------------------------
router.post('/chat/message', async (req, res) => {
    const { repo_url, message, session_id = 'default' } = req.body;

    if (!message || !repo_url) {
        return res.status(400).json({ error: 'message and repo_url are required' });
    }

    try {
        // 1. Fetch recent history for this session from MongoDB
        const recentHistory = await ChatHistory.find({ repo_url, session_id })
            .sort({ created_at: -1 })
            .limit(HISTORY_WINDOW / 2)   // limit exchanges, not messages
            .lean();

        // Convert to flat [{role, content}] list in chronological order
        const chatHistory = [];
        recentHistory.reverse().forEach(entry => {
            chatHistory.push({ role: 'user',      content: entry.user_prompt });
            chatHistory.push({ role: 'ai',         content: entry.ai_response });
        });

        // 2. Forward to AI service with history + session_id
        const response = await axios.post(`${AI_SERVICE_URL}/agent/chat`, {
            message,
            session_id,
            chat_history: chatHistory,
        });

        const { answer, sources = [], retry_count = 0 } = response.data;

        // 3. Persist this exchange to MongoDB
        const chatRecord = new ChatHistory({
            repo_url,
            session_id,
            user_prompt: message,
            ai_response: answer,
            sources,
            retry_count,
        });
        await chatRecord.save();

        res.json({ answer, sources, retry_count, session_id });

    } catch (error) {
        console.error('Error in /chat/message:', error.message);
        res.status(500).json({ error: 'Failed to process chat message' });
    }
});

// ---------------------------------------------------------------------------
// GET /api/chat/history — Fetch prior chat sessions for a repo
// ---------------------------------------------------------------------------
router.get('/chat/history', async (req, res) => {
    const { repo_url, session_id } = req.query;

    if (!repo_url) {
        return res.status(400).json({ error: 'repo_url is required' });
    }

    try {
        const query = { repo_url };
        if (session_id) query.session_id = session_id;

        const history = await ChatHistory.find(query)
            .sort({ created_at: 1 })
            .lean();

        res.json({ history });
    } catch (error) {
        console.error('Error in /chat/history:', error.message);
        res.status(500).json({ error: 'Failed to fetch chat history' });
    }
});

module.exports = router;
