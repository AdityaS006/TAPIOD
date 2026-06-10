import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import LiveTraces from './pages/LiveTraces';
import Configuration from './pages/Configuration';
import Observability from './pages/Observability';
import Playground from './pages/Playground';
import './index.css';

function App() {
  return (
    <Router>
      <div style={{ display: 'flex', minHeight: '100vh', width: '100vw' }}>
        <Sidebar />
        <main style={{ 
          flex: 1, 
          padding: '2rem',
          height: '100vh',
          overflowY: 'auto'
        }}>
          <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
            <Routes>
              <Route path="/" element={<LiveTraces />} />
              <Route path="/playground" element={<Playground />} />
              <Route path="/config" element={<Configuration />} />
              <Route path="/observability" element={<Observability />} />
            </Routes>
          </div>
        </main>
      </div>
    </Router>
  );
}

export default App;
