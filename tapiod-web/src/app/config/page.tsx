"use client";

import React, { useState, useEffect } from 'react';
import { Key, Server, Plus, Save, Trash2, ShieldCheck, GitBranch } from 'lucide-react';

interface Provider {
  id: string;
  name: string;
  apiKey: string;
}

interface ModelRoute {
  id: string;
  alias: string;
  actual: string;
  provider: string;
  tier: string;
}

export default function Configuration() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<ModelRoute[]>([]);
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
      // Backend might not be up yet, silently ignore for prototype
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
      // Backend might not be up yet, silently ignore for prototype
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
      // Backend might not be up yet, silently ignore for prototype
    }
  };

  const handleVerifyProvider = async (name: string) => {
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

  const handleRemoveProvider = async (name: string) => {
    try {
      await fetch(`http://localhost:4001/api/config/provider/${name}`, {
        method: 'DELETE'
      });
      fetchConfig();
    } catch (err) {
      // Backend might not be up yet, silently ignore for prototype
    }
  };

  const handleRemoveRoute = async (alias: string) => {
    try {
      await fetch(`http://localhost:4001/api/config/model/${alias}`, {
        method: 'DELETE'
      });
      fetchConfig();
    } catch (err) {
      // Backend might not be up yet, silently ignore for prototype
    }
  };

  return (
    <div className="flex flex-col h-full w-full relative">
      <div className="mb-8">
        <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Gateway Configuration</h1>
        <p className="text-[var(--text-muted)]">Manage LLM providers, API keys, and routing rules securely.</p>
      </div>

      <div className="grid grid-cols-2 gap-6 flex-1">
        <div className="glass-panel p-8 flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white/5 rounded-lg border border-white/5">
                <Key className="text-[var(--accent-orange)]" size={24} />
              </div>
              <h2 className="text-[1.5rem] font-semibold tracking-tight">Provider API Keys</h2>
            </div>
            <button className="flex items-center gap-2 bg-[var(--accent-purple)] hover:bg-[var(--accent-purple-light)] text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors border border-white/10 shadow-md">
              <Plus size={16} /> Add Provider
            </button>
          </div>

          <div className="flex flex-col gap-4">
            {providers.map(p => (
              <div key={p.id} className="bg-[#1e1e20] p-4 rounded-lg border border-white/5 flex items-center justify-between hover:border-white/10 transition-all duration-150">
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="font-semibold text-[var(--text-primary)]">{p.name}</span>
                    <span className="badge badge-success text-[10px] px-2 py-0.5">Active</span>
                  </div>
                  <div className="font-mono text-[var(--text-secondary)] text-xs opacity-80 tracking-widest">
                    {p.apiKey}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="p-2 rounded-md hover:bg-white/5 text-[var(--text-secondary)] hover:text-[var(--accent-green)] transition-colors" title="Verify Key" onClick={() => handleVerifyProvider(p.name)}>
                    <ShieldCheck size={18} />
                  </button>
                  <button className="p-2 rounded-md hover:bg-white/5 text-[var(--text-secondary)] hover:text-[var(--accent-red)] transition-colors" title="Delete" onClick={() => handleRemoveProvider(p.name)}>
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))}
            {providers.length === 0 && (
              <div className="text-center p-6 bg-[#1e1e20] rounded-lg border border-white/5 border-dashed text-[var(--text-muted)] text-sm">
                No providers configured yet.
              </div>
            )}
          </div>

          <div className="mt-auto pt-8 border-t border-white/5">
            <h3 className="text-[1.125rem] font-semibold tracking-tight mb-4">Add New Key</h3>
            <div className="flex flex-col gap-1.5 mb-4">
              <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">Provider Name</label>
              <select 
                className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded-lg py-2.5 px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-purple)] transition-colors" 
                value={newProviderName} 
                onChange={e => setNewProviderName(e.target.value)}
              >
                <option value="Groq">Groq</option>
                <option value="OpenAI">OpenAI</option>
                <option value="Anthropic">Anthropic</option>
                <option value="Mistral">Mistral</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5 mb-6">
              <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">API Key</label>
              <input 
                type="password" 
                className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded-lg py-2.5 px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-purple)] transition-colors" 
                placeholder="sk-..." 
                value={newProviderKey} 
                onChange={e => setNewProviderKey(e.target.value)} 
              />
            </div>
            <button 
              className="flex items-center justify-center gap-2 w-full bg-[#2a2a2d] hover:bg-[#3f3f46] text-[var(--text-primary)] text-sm font-medium py-2.5 px-4 rounded-lg transition-colors border border-white/5 disabled:opacity-50 disabled:cursor-not-allowed" 
              onClick={handleAddProvider} 
              disabled={!newProviderKey}
            >
              <Save size={16} /> Save Key Securely
            </button>
          </div>
        </div>

        <div className="glass-panel p-8 flex flex-col">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-white/5 rounded-lg border border-white/5">
                <Server className="text-[var(--accent-blue-light)]" size={24} />
              </div>
              <h2 className="text-[1.5rem] font-semibold tracking-tight">Model Routing</h2>
            </div>
            {routellmStatus ? (
              <span className="badge badge-success text-xs">RouteLLM Active</span>
            ) : (
              <span className="badge bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 text-xs animate-pulse-slow">Initializing RouteLLM...</span>
            )}
          </div>

          <div className="mb-6 p-4 bg-[var(--accent-blue)]/10 rounded-lg border border-[var(--accent-blue)]/20">
            <h4 className="text-sm font-semibold text-[var(--accent-blue-light)] mb-1">Semantic Routing Rules</h4>
            <p className="text-xs text-[var(--text-secondary)] leading-relaxed">Requests scoring &lt; 0.5 complexity will route to Low Complexity models. Scores &ge; 0.5 route to High Complexity models dynamically.</p>
          </div>

          <div className="flex flex-col gap-4 overflow-y-auto max-h-[300px] pr-2">
            {models.map(m => (
              <div key={m.id} className="bg-[#1e1e20] p-4 rounded-lg border border-white/5 relative group">
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-[var(--accent-purple-light)]">{m.alias}</span>
                    <span className="badge bg-transparent border border-white/20 text-[var(--text-secondary)] text-[10px]">{m.tier}</span>
                  </div>
                  <button 
                    className="p-1 rounded hover:bg-white/5 text-[var(--text-secondary)] opacity-0 group-hover:opacity-100 absolute top-2 right-2 transition-all" 
                    title="Delete Route" 
                    onClick={() => handleRemoveRoute(m.alias)}
                  >
                    <Trash2 size={16} className="hover:text-[var(--accent-red)]" />
                  </button>
                </div>
                <div className="text-xs text-[var(--text-secondary)] mt-2">
                  Maps to: <span className="font-mono text-[var(--text-primary)] bg-black/30 px-1.5 py-0.5 rounded ml-1">{m.actual}</span> <span className="opacity-60 ml-1">({m.provider})</span>
                </div>
              </div>
            ))}
            {models.length === 0 && (
              <div className="text-center p-6 bg-[#1e1e20] rounded-lg border border-white/5 border-dashed text-[var(--text-muted)] text-sm">
                No routes configured yet.
              </div>
            )}
          </div>

          <div className="mt-auto pt-8 border-t border-white/5">
            <h3 className="text-[1.125rem] font-semibold tracking-tight mb-4">Add Route Mapping</h3>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">Alias (e.g. fast-model)</label>
                <input 
                  type="text" 
                  className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded-lg py-2 px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-purple)] transition-colors" 
                  placeholder="Alias name" 
                  value={newRouteAlias} 
                  onChange={e => setNewRouteAlias(e.target.value)} 
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">Provider Name</label>
                <select 
                  className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded-lg py-2 px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-purple)] transition-colors" 
                  value={newRouteProvider} 
                  onChange={e => setNewRouteProvider(e.target.value)}
                >
                  <option value="Groq">Groq</option>
                  <option value="OpenAI">OpenAI</option>
                  <option value="Anthropic">Anthropic</option>
                  <option value="Mistral">Mistral</option>
                </select>
              </div>
            </div>
            <div className="flex flex-col gap-1.5 mb-6">
              <label className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">Actual Model (e.g. llama-3.1-8b-instant)</label>
              <input 
                type="text" 
                className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded-lg py-2 px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-purple)] transition-colors" 
                placeholder="Provider Model" 
                value={newRouteActual} 
                onChange={e => setNewRouteActual(e.target.value)} 
              />
            </div>
            <button 
              className="flex items-center justify-center gap-2 w-full bg-[#2a2a2d] hover:bg-[#3f3f46] text-[var(--text-primary)] text-sm font-medium py-2.5 px-4 rounded-lg transition-colors border border-white/5 disabled:opacity-50 disabled:cursor-not-allowed" 
              onClick={handleAddRoute} 
              disabled={!newRouteAlias || !newRouteActual}
            >
              <Plus size={16} /> Add Route Mapping
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
