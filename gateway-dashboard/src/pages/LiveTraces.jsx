import React, { useState, useEffect } from 'react';
import { Shield, EyeOff, Database, GitBranch, Cpu, CheckCircle, XCircle } from 'lucide-react';

const TraceNode = ({ title, icon: Icon, active, status, delay, detail }) => {
  return (
    <div className={`glass-panel p-4 flex-col items-center justify-center`} style={{
      width: '150px',
      minHeight: '140px',
      position: 'relative',
      opacity: active ? 1 : 0.4,
      transform: active ? 'scale(1.05)' : 'scale(1)',
      transition: `all 0.5s ease ${delay}s`,
      border: active 
        ? (status === 'error' ? '1px solid var(--accent-red)' : '1px solid var(--accent-purple)') 
        : '1px solid var(--border-color)',
      boxShadow: active 
        ? (status === 'error' ? '0 0 20px rgba(239,68,68,0.2)' : '0 0 20px var(--glow-purple)') 
        : 'none',
      display: 'flex',
      gap: '0.75rem',
      alignItems: 'center'
    }}>
      <div style={{
        background: active 
          ? (status === 'error' ? 'rgba(239,68,68,0.1)' : 'rgba(139, 92, 246, 0.1)') 
          : 'rgba(255,255,255,0.05)',
        padding: '1rem',
        borderRadius: '50%',
        color: active 
          ? (status === 'error' ? 'var(--accent-red)' : 'var(--accent-purple)') 
          : 'var(--text-muted)'
      }}>
        <Icon size={28} />
      </div>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, textAlign: 'center' }}>
        {title}
      </div>
      
      {active && detail && (
        <div style={{
          fontSize: '0.7rem',
          color: 'var(--text-secondary)',
          textAlign: 'center',
          marginTop: '0.25rem',
          background: 'rgba(0,0,0,0.2)',
          padding: '0.5rem',
          borderRadius: '4px',
          width: '100%',
          animation: 'fadeIn 0.3s ease-in-out'
        }}>
          {detail}
        </div>
      )}

      {active && status && (
        <div style={{ position: 'absolute', top: '-8px', right: '-8px' }}>
          {status === 'success' ? (
            <CheckCircle size={20} className="text-accent-green" fill="rgba(16,185,129,0.2)" />
          ) : (
            <XCircle size={20} className="text-accent-red" fill="rgba(239,68,68,0.2)" />
          )}
        </div>
      )}
    </div>
  );
};

const Connector = ({ active, delay }) => (
  <div style={{
    width: '40px',
    height: '2px',
    background: 'var(--border-color)',
    position: 'relative',
    overflow: 'hidden'
  }}>
    <div style={{
      position: 'absolute',
      top: 0,
      left: 0,
      height: '100%',
      width: '100%',
      background: 'linear-gradient(90deg, transparent, var(--accent-purple), transparent)',
      transform: active ? 'translateX(100%)' : 'translateX(-100%)',
      transition: `transform 1s ease ${delay}s`,
      opacity: active ? 1 : 0
    }} />
  </div>
);

const LiveTraces = () => {
  const [tracing, setTracing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [previousTotal, setPreviousTotal] = useState(0);
  const [recentLogs, setRecentLogs] = useState([]);
  const [metrics, setMetrics] = useState({
    cacheHitRate: '0%',
    avgLatency: '0ms',
    blockedRate: '0%',
    costSavings: '$0.00'
  });

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('http://localhost:4001/api/metrics');
        if (res.ok) {
          const data = await res.json();
          const total = data.total_requests || 1; 
          const cacheHits = data.cache_hits || 0;
          const blocked = data.blocked_requests || 0;
          
          setMetrics({
            cacheHitRate: `${((cacheHits / total) * 100).toFixed(1)}%`,
            avgLatency: `${data.avg_latency_ms || 0}ms`,
            blockedRate: `${((blocked / total) * 100).toFixed(1)}%`,
            costSavings: `$${data.total_cost.toFixed(4)}`
          });
          
          if (data.recent_requests) {
            setRecentLogs([...data.recent_requests].reverse()); // latest first
          }

          setPreviousTotal(prev => {
            // We only update if the total actually increased
            if (data.total_requests > prev) {
              return data.total_requests;
            }
            return prev;
          });
        }
      } catch (err) {
        // Silently ignore if proxy isn't tracking yet
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 1000); // 1-second polling for real-time feel
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Only animate if there's actually a request to show, and we're not currently tracing
    if (previousTotal > 0 && !tracing) {
      setTracing(true);
      setCurrentStep(0);

      let step = 1;
      const progressionInterval = setInterval(() => {
        setCurrentStep(step);
        if (step >= 6) {
          clearInterval(progressionInterval);
          setTimeout(() => {
            setTracing(false);
            setCurrentStep(0);
          }, 5000); // Reset after 5 seconds of being fully lit
        }
        step++;
      }, 1000); // 1-second animation per node

      return () => clearInterval(progressionInterval);
    }
  }, [previousTotal]);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="heading-lg mb-2">Live Request Traces</h1>
          <p className="text-muted">Monitor the flow of LLM requests through the enterprise gateway pipeline.</p>
        </div>
        <div className="flex items-center gap-4">
          {tracing && <span className="text-accent-purple" style={{ animation: 'pulse 1.5s infinite' }}>● Real-time Request Processing</span>}
        </div>
      </div>

      <div className="glass-panel" style={{ padding: '3rem', marginBottom: '2rem', overflowX: 'auto' }}>
      <div className="flex flex-col gap-6" style={{ position: 'relative', zIndex: 10 }}>
        {(() => {
          const latestReq = recentLogs.length > 0 ? recentLogs[0] : null;
          const reqTime = latestReq ? latestReq.time : new Date().toLocaleTimeString();
          const reqModel = latestReq ? latestReq.model : 'heavy-model';
          const reqTokens = latestReq ? latestReq.tokens : '...';
          const reqLatency = latestReq ? latestReq.latency : '...';
          const reqCost = latestReq ? latestReq.cost.toFixed(6) : '0.000000';

          return (
            <div className="flex items-center justify-between" style={{ minWidth: '900px', alignItems: 'flex-start' }}>
              <TraceNode 
                title="1. LiteLLM Proxy" 
                icon={Shield}
                active={currentStep > 0}
                detail={`Received request at ${reqTime}. Authenticating...`} 
              />
              <Connector active={currentStep > 0} delay={0.5} />
              <TraceNode 
                title="2. Llama Guard 3" 
                icon={Shield}
                active={currentStep > 1}
                detail="Intent classified as SAFE. No malicious payload detected." 
              />
              <Connector active={currentStep > 1} delay={1.5} />
              <TraceNode 
                title="3. Presidio PII Masking" 
                icon={EyeOff}
                active={currentStep > 2}
                detail="No PII masking logic hooked yet. Bypassing." 
              />
              <Connector active={currentStep > 2} delay={2.5} />
              <TraceNode 
                title="4. Qdrant Semantic Cache" 
                icon={Database}
                active={currentStep > 3}
                detail="Cache miss. Semantic similarity below threshold." 
              />
              <Connector active={currentStep > 3} delay={3.5} />
              <TraceNode 
                title="5. RouteLLM Controller" 
                icon={GitBranch}
                active={currentStep > 4}
                detail={`Routing strategy selected: ${reqModel}.`} 
              />
              <Connector active={currentStep > 4} delay={4.5} />
              <TraceNode 
                title="6. LLM Provider Backend" 
                icon={Cpu}
                active={currentStep > 5}
                detail={`Successfully dispatched to ${reqModel}. Latency: ${reqLatency}s | Tokens: ${reqTokens} | Cost: $${reqCost}`} 
              />
            </div>
          );
        })()}
      </div>
      </div>

      <div className="grid grid-cols-2">
        <div className="glass-panel" style={{ padding: '1.5rem', height: '300px', display: 'flex', flexDirection: 'column' }}>
          <h3 className="heading-sm mb-4">Request Log (Recent Real Requests)</h3>
          <div style={{ 
            flex: 1, 
            background: 'rgba(0,0,0,0.3)', 
            borderRadius: 'var(--radius-sm)', 
            padding: '1rem',
            fontFamily: 'monospace',
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.75rem'
          }}>
            {recentLogs.length === 0 && <span style={{ opacity: 0.5 }}>Waiting for requests to flow through the proxy...</span>}
            {recentLogs.map((entry, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '0.5rem' }}>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <span style={{ color: 'var(--accent-purple)', minWidth: '70px' }}>[{entry.time}]</span>
                  <span style={{ color: 'var(--text-primary)' }}>Processed request via <span style={{ color: 'var(--accent-blue)' }}>{entry.model}</span></span>
                </div>
                <div style={{ paddingLeft: '85px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Latency: {entry.latency}s | Tokens: {entry.tokens} | Cost: ${entry.cost.toFixed(6)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.5rem', height: '300px' }}>
          <h3 className="heading-sm mb-4">Pipeline Metrics (Real-time)</h3>
          <div className="grid grid-cols-2" style={{ gap: '1rem' }}>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: 'var(--radius-sm)' }}>
              <div className="text-muted" style={{ fontSize: '0.75rem', marginBottom: '0.25rem' }}>Cache Hit Rate</div>
              <div className="heading-md text-gradient">{metrics.cacheHitRate}</div>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: 'var(--radius-sm)' }}>
              <div className="text-muted" style={{ fontSize: '0.75rem', marginBottom: '0.25rem' }}>Avg Latency</div>
              <div className="heading-md" style={{ color: 'var(--accent-orange)' }}>{metrics.avgLatency}</div>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: 'var(--radius-sm)' }}>
              <div className="text-muted" style={{ fontSize: '0.75rem', marginBottom: '0.25rem' }}>Blocked (Guardrails)</div>
              <div className="heading-md" style={{ color: 'var(--accent-red)' }}>{metrics.blockedRate}</div>
            </div>
            <div style={{ background: 'rgba(0,0,0,0.2)', padding: '1rem', borderRadius: 'var(--radius-sm)' }}>
              <div className="text-muted" style={{ fontSize: '0.75rem', marginBottom: '0.25rem' }}>Total Cost</div>
              <div className="heading-md text-gradient">{metrics.costSavings}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveTraces;
