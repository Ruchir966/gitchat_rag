const express = require('express');
const axios = require('axios');
const ChatHistory = require('../models/ChatHistory');

const router = express.Router();

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';

// Ingest Repo
router.post('/repo/submit', async (req, res) => {
    const { repo_url } = req.body;
    
    if (!repo_url) {
        return res.status(400).json({ error: 'repo_url is required' });
    }

    try {
        const response = await axios.post(`${AI_SERVICE_URL}/agent/ingest`, {
            repo_url
        });
        res.json(response.data);
    } catch (error) {
        console.error('Error in /repo/submit:', error.message);
        res.status(500).json({ error: 'Failed to ingest repository' });
    }
});

// Chat Message
router.post('/chat/message', async (req, res) => {
    const { repo_url, message } = req.body;

    if (!message || !repo_url) {
        return res.status(400).json({ error: 'message and repo_url are required' });
    }

    try {
        // Forward to AI service
        const response = await axios.post(`${AI_SERVICE_URL}/agent/chat`, {
            message
        });

        const ai_response = response.data.answer;

        // Save to MongoDB
        const chatHistory = new ChatHistory({
            repo_url,
            user_prompt: message,
            ai_response: ai_response
        });
        await chatHistory.save();

        res.json({ answer: ai_response });
    } catch (error) {
        console.error('Error in /chat/message:', error.message);
        res.status(500).json({ error: 'Failed to process chat message' });
    }
});

module.exports = router;
