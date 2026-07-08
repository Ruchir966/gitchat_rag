const mongoose = require('mongoose');

const ChatHistorySchema = new mongoose.Schema({
    repo_url: { type: String, required: true },
    user_prompt: { type: String, required: true },
    ai_response: { type: String, required: true },
    created_at: { type: Date, default: Date.now }
});

module.exports = mongoose.model('ChatHistory', ChatHistorySchema);
