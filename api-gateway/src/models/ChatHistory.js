const mongoose = require('mongoose');

const ChatHistorySchema = new mongoose.Schema({
    repo_url:    { type: String, required: true },
    session_id:  { type: String, required: true, default: 'default' },
    user_prompt: { type: String, required: true },
    ai_response: { type: String, required: true },
    sources:     { type: [String], default: [] },
    retry_count: { type: Number, default: 0 },
    created_at:  { type: Date, default: Date.now }
});

// Compound index for fast per-session history fetching
ChatHistorySchema.index({ repo_url: 1, session_id: 1, created_at: 1 });

module.exports = mongoose.model('ChatHistory', ChatHistorySchema);
