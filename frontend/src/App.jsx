import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import ChatRoom from './components/ChatRoom';

function App() {
  const [activeRepo, setActiveRepo] = useState(null);

  const handleReset = () => {
    setActiveRepo(null);
  };

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100">
      {!activeRepo ? (
        <Dashboard onRepoIngested={setActiveRepo} />
      ) : (
        <ChatRoom repoUrl={activeRepo} onReset={handleReset} />
      )}
    </div>
  );
}

export default App;
