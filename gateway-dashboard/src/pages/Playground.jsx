import React, { useState, useEffect } from 'react';
import { Send, Terminal, Code } from 'lucide-react';

const Playground = () => {
  const [prompt, setPrompt] = useState('Write a haiku about artificial intelligence.');
  const [isSending, setIsSending] = useState(false);
  const [requestJson, setRequestJson] = useState(null);
  const [responseJson, setResponseJson] = useState(null);

  const handleSend = async () => {
    if (!prompt) return;
    
    setIsSending(true);
    setResponseJson(null);

    const payload = {
      model: 'auto', // Dynamic semantic routing requested
      messages: [
        { role: 'user', content: prompt }
      ]
    };

    setRequestJson(payload);

    try {
      const startTime = Date.now();
      const response = await fetch('http://localhost:4000/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const data = await response.json();
      const endTime = Date.now();
      
      // Add latency to the response JSON for display purposes
      const displayData = {
        _latency_ms: endTime - startTime,
        ...data
      };
      
      setResponseJson(displayData);
    } catch (err) {
      setResponseJson({ error: err.message || 'Failed to connect to gateway' });
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="mb-6">
        <h1 className="heading-lg mb-2">Input / Output Playground</h1>
        <p className="text-muted">Test your models and inspect the raw API JSON payloads.</p>
      </div>

      <div style={{ display: 'flex', gap: '2rem', flex: 1, minHeight: '600px' }}>
        
        {/* Left Pane: Input Form */}
        <div className="glass-panel" style={{ flex: 1, padding: '2rem', display: 'flex', flexDirection: 'column' }}>
          <div className="flex items-center gap-2 mb-6">
            <Terminal className="text-accent-blue" />
            <h2 className="heading-md">Gateway Request</h2>
          </div>

          <div className="input-group" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <label className="input-label">User Prompt</label>
            <textarea 
              className="input-field" 
              style={{ flex: 1, resize: 'none', padding: '1rem', fontFamily: 'monospace' }}
              placeholder="Enter your prompt here..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>

          <button 
            className="btn btn-primary" 
            style={{ width: '100%', marginTop: '1.5rem', justifyContent: 'center' }}
            onClick={handleSend}
            disabled={isSending || !prompt}
          >
            <Send size={16} />
            {isSending ? 'Sending to Gateway...' : 'Send Request'}
          </button>
        </div>

        {/* Right Pane: Output Inspector */}
        <div className="glass-panel" style={{ flex: 1, padding: '2rem', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div className="flex items-center gap-2 mb-6">
            <Code className="text-accent-purple" />
            <h2 className="heading-md">Model Output</h2>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem', overflowY: 'auto' }}>
            
            <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', fontWeight: 600 }}>Response</div>
              <div style={{ 
                background: 'rgba(0,0,0,0.3)', 
                padding: '1.5rem', 
                borderRadius: 'var(--radius-sm)', 
                fontSize: '0.95rem',
                color: 'var(--text-primary)',
                flex: 1,
                overflowY: 'auto',
                borderLeft: '2px solid var(--accent-purple)',
                lineHeight: '1.6',
                whiteSpace: 'pre-wrap'
              }}>
                {isSending ? (
                  <span className="text-accent-purple" style={{ animation: 'pulse 1.5s infinite' }}>Awaiting response from LLM Engine...</span>
                ) : responseJson ? (
                  <div style={{ color: responseJson.error ? 'var(--accent-red)' : 'inherit' }}>
                    {responseJson.error ? (
                      responseJson.error
                    ) : (
                      responseJson.choices && responseJson.choices[0] 
                        ? responseJson.choices[0].message.content 
                        : "No content returned."
                    )}
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>Waiting for you to send a prompt...</span>
                )}
              </div>
            </div>
            
            {responseJson && !responseJson.error && (
              <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem' }}>
                <div className="badge" style={{ background: 'rgba(139, 92, 246, 0.1)', color: 'var(--accent-purple)' }}>
                  Latency: {responseJson._latency_ms}ms
                </div>
                {responseJson.usage && (
                  <div className="badge" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-blue)' }}>
                    Tokens: {responseJson.usage.total_tokens}
                  </div>
                )}
              </div>
            )}

          </div>
        </div>

      </div>
    </div>
  );
};

export default Playground;
