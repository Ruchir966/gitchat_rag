import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Send, Loader2, Bot, User, Globe } from 'lucide-react';

const ChatRoom = ({ repoUrl, onReset }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await axios.post('http://localhost:3000/api/chat/message', {
        repo_url: repoUrl,
        message: input,
      });

      const aiMessage = { role: 'ai', content: response.data.answer };
      setMessages((prev) => [...prev, aiMessage]);
    } catch (error) {
      const errorMessage = { role: 'ai', content: 'Sorry, I encountered an error while processing your request.' };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-5xl mx-auto p-4">
      <header className="flex items-center justify-between p-4 bg-slate-800 rounded-t-xl border-b border-slate-700">
        <div className="flex items-center gap-3">
          <Globe className="w-6 h-6 text-blue-400" />
          <h1 className="text-lg font-semibold text-white truncate max-w-[300px] sm:max-w-md">
            {repoUrl.split('/').slice(-2).join('/')}
          </h1>
        </div>
        <button
          onClick={onReset}
          className="text-sm px-3 py-1.5 text-slate-300 hover:text-white bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
        >
          Change Repo
        </button>
      </header>

      <main className="flex-1 overflow-y-auto bg-slate-900/50 p-4 space-y-6 rounded-b-xl border border-t-0 border-slate-700 custom-scrollbar">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500 space-y-4">
            <Bot className="w-12 h-12 text-slate-600" />
            <p>Ask me anything about this repository!</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'ai' && (
                <div className="w-8 h-8 rounded-full bg-blue-600/20 flex items-center justify-center flex-shrink-0 mt-1">
                  <Bot className="w-5 h-5 text-blue-400" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-5 py-3.5 ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-800 text-slate-200 border border-slate-700 shadow-lg'
                }`}
              >
                {msg.role === 'user' ? (
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <div className="prose prose-invert max-w-none prose-pre:bg-slate-900 prose-pre:border prose-pre:border-slate-700">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 mt-1">
                  <User className="w-5 h-5 text-slate-300" />
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="flex gap-4 justify-start">
            <div className="w-8 h-8 rounded-full bg-blue-600/20 flex items-center justify-center flex-shrink-0 mt-1">
              <Bot className="w-5 h-5 text-blue-400" />
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-2xl px-5 py-4 flex items-center gap-2 text-slate-400">
              <Loader2 className="w-4 h-4 animate-spin text-blue-400" />
              <span>Thinking...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      <footer className="mt-4">
        <form onSubmit={handleSend} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about the code..."
            className="w-full bg-slate-800 text-white rounded-xl pl-4 pr-12 py-4 focus:outline-none focus:ring-2 focus:ring-blue-500 border border-slate-700 shadow-lg placeholder:text-slate-500 transition-all"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="absolute right-2 p-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </footer>
    </div>
  );
};

export default ChatRoom;
