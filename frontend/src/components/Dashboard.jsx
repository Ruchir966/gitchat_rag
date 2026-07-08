import React, { useState } from 'react';
import axios from 'axios';
import { Globe, Loader2 } from 'lucide-react';

const Dashboard = ({ onRepoIngested }) => {
  const [repoUrl, setRepoUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!repoUrl) return;
    
    setLoading(true);
    setError('');

    try {
      // In a real app, use an environment variable for the API URL
      const response = await axios.post('http://localhost:3000/api/repo/submit', { repo_url: repoUrl });
      if (response.data.status === 'success') {
        onRepoIngested(repoUrl);
      } else {
        setError('Failed to ingest repository.');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred during ingestion.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] p-4">
      <div className="w-full max-w-md p-8 space-y-8 bg-slate-800 rounded-xl shadow-2xl border border-slate-700 backdrop-blur-sm">
        <div className="text-center">
          <Globe className="w-12 h-12 mx-auto text-blue-500 mb-4" />
          <h2 className="text-3xl font-bold text-white tracking-tight">Codebase RAG</h2>
          <p className="mt-2 text-slate-400">Chat with your GitHub repository</p>
        </div>

        <form onSubmit={handleSubmit} className="mt-8 space-y-6">
          <div>
            <label htmlFor="repoUrl" className="block text-sm font-medium text-slate-300">
              GitHub Repository URL
            </label>
            <div className="mt-2">
              <input
                id="repoUrl"
                name="repoUrl"
                type="url"
                required
                className="block w-full px-4 py-3 rounded-lg border-0 bg-slate-900/50 text-white shadow-sm ring-1 ring-inset ring-slate-700 focus:ring-2 focus:ring-inset focus:ring-blue-500 sm:text-sm sm:leading-6 placeholder:text-slate-500 transition-all"
                placeholder="https://github.com/username/repo"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
              />
            </div>
          </div>

          {error && (
            <div className="text-red-400 text-sm text-center bg-red-900/20 py-2 rounded-lg border border-red-900/50">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="group relative flex w-full justify-center rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg hover:shadow-blue-500/25"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-5 h-5 animate-spin" />
                Ingesting...
              </span>
            ) : (
              'Connect Repository'
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

export default Dashboard;
