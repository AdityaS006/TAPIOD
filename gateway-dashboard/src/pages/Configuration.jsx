import React, { useState, useEffect } from 'react';
import { Key, Server, Plus, Save, Trash2, ShieldCheck, GitBranch } from 'lucide-react';

const Configuration = () => {
  const [providers, setProviders] = useState([]);
  const [models, setModels] = useState([]);
  const [routellmStatus, setRoutellmStatus] = useState(false);
  
  // Form states for Provider
  const [newProviderName, setNewProviderName] = useState('Groq');
  const [newProviderKey, setNewProviderKey] = useState('');
  
  // Form states for Model Route
  const [newRouteAlias, setNewRouteAlias] = useState('');
  const [newRouteActual, setNewRouteActual] = useState('');
  const [newRouteProvider, setNewRouteProvider] = useState('Groq');

  const fetchConfig = async () => {
    try {
      const res = await fetch('http://localhost:4001/api/config');
      if (res.ok) {
        const data = await res.json();
        setProviders(data.providers || []);
        setModels(data.models || []);
        setRoutellmStatus(data.routellm_status || false);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchConfig();
    const interval = setInterval(fetchConfig, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleAddProvider = async () => {
    if (!newProviderKey) return;
    try {
      await fetch('http://localhost:4001/api/config/provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProviderName, apiKey: newProviderKey })
      });
      setNewProviderKey('');
      fetchConfig();
    } catch (err) {
      console.error(err);
    }
  };

  const handleAddRoute = async () => {
    if (!newRouteAlias || !newRouteActual) return;
    try {
      await fetch('http://localhost:4001/api/config/model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias: newRouteAlias, actual: newRouteActual, provider: newRouteProvider })
      });
      setNewRouteAlias('');
      setNewRouteActual('');
      fetchConfig();
    } catch (err) {
      console.error(err);
    }
  };

  const handleVerifyProvider = async (name) => {
    try {
      const res = await fetch(`http://localhost:4001/api/config/verify/${name}`);
      const data = await res.json();
      if (data.status === 'success') {
        alert(`${name} API Key is valid and active!`);
      } else {
        alert(`Failed to verify ${name} API Key: ${data.message}`);
      }
    } catch (err) {
      console.error(err);
      alert('Verification request failed.');
    }
  };

  const handleRemoveProvider = async (name) => {
    try {
      await fetch(`http://localhost:4001/api/config/provider/${name}`, {
        method: 'DELETE'
      });
      fetchConfig();
    } catch (err) {
      console.error(err);
    }
  };

  const handleRemoveRoute = async (alias) => {
    try {
      await fetch(`http://localhost:4001/api/config/model/${alias}`, {
        method: 'DELETE'
      });
      fetchConfig();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="heading-lg mb-2">Gateway Configuration</h1>
        <p className="text-muted">Manage LLM providers, API keys, and routing rules securely.</p>
      </div>

      <div className="grid grid-cols-2">
        <div className="glass-panel" style={{ padding: '2rem' }}>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <Key className="text-accent-orange" />
              <h2 className="heading-md">Provider API Keys</h2>
            </div>
            <button className="btn btn-primary" style={{ padding: '0.5rem 1rem' }}>
              <Plus size={16} /> Add Provider
            </button>
          </div>

          <div className="flex-col gap-4">
            {providers.map(p => (
              <div key={p.id} style={{ 
                background: 'rgba(0,0,0,0.2)', 
                padding: '1rem', 
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span style={{ fontWeight: 600 }}>{p.name}</span>
                    <span className="badge badge-success" style={{ fontSize: '0.6rem', padding: '0.15rem 0.5rem' }}>Active</span>
                  </div>
                  <div style={{ fontFamily: 'monospace', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                    {p.apiKey}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }} title="Verify Key" onClick={() => handleVerifyProvider(p.name)}>
                    <ShieldCheck size={18} className="hover:text-accent-green" />
                  </button>
                  <button style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }} title="Delete" onClick={() => handleRemoveProvider(p.name)}>
                    <Trash2 size={18} className="hover:text-accent-red" />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8">
            <h3 className="heading-sm mb-4">Add New Key</h3>
            <div className="input-group">
              <label className="input-label">Provider Name</label>
              <select className="input-field" style={{ appearance: 'none' }} value={newProviderName} onChange={e => setNewProviderName(e.target.value)}>
                <option value="Groq">Groq</option>
                <option value="OpenAI">OpenAI</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Mistral">Mistral</option>
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">API Key</label>
              <input type="password" className="input-field" placeholder="sk-..." value={newProviderKey} onChange={e => setNewProviderKey(e.target.value)} />
            </div>
            <button className="btn btn-secondary w-full" style={{ width: '100%', justifyContent: 'center' }} onClick={handleAddProvider}>
              <Save size={16} /> Save Key Securely
            </button>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '2rem' }}>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <Server className="text-accent-blue" />
              <h2 className="heading-md">Model Routing</h2>
            </div>
            {routellmStatus ? (
              <span className="badge badge-success">RouteLLM Active</span>
            ) : (
              <span className="badge" style={{ background: 'rgba(234, 179, 8, 0.1)', color: '#eab308', animation: 'pulse 2s infinite' }}>Initializing RouteLLM ML Dependencies...</span>
            )}
          </div>

          <div style={{ marginBottom: '1.5rem', padding: '1rem', background: 'rgba(59, 130, 246, 0.1)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-blue)', marginBottom: '0.5rem' }}>Semantic Routing Rules</h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Requests scoring &lt; 0.5 complexity will route to Low Complexity models. Scores &ge; 0.5 route to High Complexity.</p>
          </div>

          <div className="flex-col gap-4">
            {models.map(m => (
              <div key={m.id} style={{ 
                background: 'rgba(0,0,0,0.2)', 
                padding: '1rem', 
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-color)',
              }}>
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <span style={{ fontWeight: 600, color: 'var(--accent-purple)' }}>{m.alias}</span>
                    <span className="badge" style={{ 
                      background: 'rgba(255,255,255,0.1)', 
                      color: 'var(--text-secondary)',
                      fontSize: '0.65rem'
                    }}>{m.tier}</span>
                  </div>
                  <button style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 0 }} title="Delete Route" onClick={() => handleRemoveRoute(m.alias)}>
                    <Trash2 size={16} className="hover:text-accent-red" />
                  </button>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                  Maps to: <span style={{ fontFamily: 'monospace' }}>{m.actual}</span> ({m.provider})
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8">
            <h3 className="heading-sm mb-4">Add Route Mapping</h3>
            <div className="input-group">
              <label className="input-label">Alias (e.g. fast-model)</label>
              <input type="text" className="input-field" placeholder="Alias name" value={newRouteAlias} onChange={e => setNewRouteAlias(e.target.value)} />
            </div>
            <div className="input-group">
              <label className="input-label">Actual Model (e.g. groq/llama-3.1-8b-instant)</label>
              <input type="text" className="input-field" placeholder="Provider Model" value={newRouteActual} onChange={e => setNewRouteActual(e.target.value)} />
            </div>
            <div className="input-group">
              <label className="input-label">Provider Name</label>
              <select className="input-field" style={{ appearance: 'none' }} value={newRouteProvider} onChange={e => setNewRouteProvider(e.target.value)}>
                <option value="Groq">Groq</option>
                <option value="OpenAI">OpenAI</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Mistral">Mistral</option>
              </select>
            </div>
            <button className="btn btn-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={handleAddRoute}>
              <Plus size={16} /> Add Route Mapping
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Configuration;
