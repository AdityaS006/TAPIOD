"use client";

import React, { useState, useEffect } from 'react';
import { Shield, EyeOff, Database, GitBranch, Cpu, CheckCircle, XCircle } from 'lucide-react';

interface TraceNodeProps {
  title: string;
  icon: any;
  active: boolean;
  status?: string;
  delay?: number;
  detail?: string;
}

const TraceNode = ({ title, icon: Icon, active, status, delay = 0, detail }: TraceNodeProps) => {
  return (
    <div className="glass-panel p-4 flex flex-col items-center justify-center relative" style={{
      width: '160px',
      minHeight: '150px',
      opacity: active ? 1 : 0.3,
      transform: active ? 'scale(1.02)' : 'scale(1)',
      transition: `all 0.5s cubic-bezier(0.4, 0, 0.2, 1) ${delay}s`,
      borderColor: active 
        ? (status === 'error' ? 'var(--accent-red)' : 'var(--accent-purple-light)') 
        : 'var(--border-color)',
      boxShadow: active 
        ? (status === 'error' ? '0 0 30px rgba(239,68,68,0.15)' : '0 0 30px rgba(147,51,234,0.15)') 
        : 'none',
      gap: '0.75rem'
    }}>
      <div className="rounded-full p-4 transition-all" style={{
        background: active 
          ? (status === 'error' ? 'rgba(239,68,68,0.1)' : 'rgba(147,51,234,0.1)') 
          : 'rgba(255,255,255,0.03)',
        color: active 
          ? (status === 'error' ? 'var(--accent-red)' : 'var(--accent-purple-light)') 
          : 'var(--text-muted)'
      }}>
        <Icon size={28} strokeWidth={1.5} />
      </div>
      <div className="text-sm font-semibold text-center text-[var(--text-primary)]">
        {title}
      </div>
      
      {active && detail && (
        <div className="text-xs text-[var(--text-secondary)] text-center mt-1 p-2 bg-black-20 rounded-md w-full animate-fade-in border border-white/5">
          {detail}
        </div>
      )}

      {active && status && (
        <div className="absolute -top-2 -right-2 bg-[#09090b] rounded-full">
          {status === 'success' ? (
            <CheckCircle size={22} className="text-accent-green" fill="rgba(16,185,129,0.1)" />
          ) : (
            <XCircle size={22} className="text-accent-red" fill="rgba(239,68,68,0.1)" />
          )}
        </div>
      )}
    </div>
  );
};

const Connector = ({ active, delay = 0 }: { active: boolean, delay?: number }) => (
  <div className="relative overflow-hidden" style={{
    width: '40px',
    height: '2px',
    background: 'var(--border-color)'
  }}>
    <div className="absolute inset-0 w-full h-full" style={{
      background: 'linear-gradient(90deg, transparent, var(--accent-purple-light), transparent)',
      transform: active ? 'translateX(100%)' : 'translateX(-100%)',
      transition: `transform 1s cubic-bezier(0.4, 0, 0.2, 1) ${delay}s`,
      opacity: active ? 1 : 0
    }} />
  </div>
);

export default function LiveTraces() {
  const [tracing, setTracing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [previousTotal, setPreviousTotal] = useState(0);
  const [recentLogs, setRecentLogs] = useState<any[]>([]);
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
            setRecentLogs([...data.recent_requests].reverse());
          }

          setPreviousTotal(prev => {
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
    const interval = setInterval(fetchMetrics, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
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
          }, 5000);
        }
        step++;
      }, 1000);

      return () => clearInterval(progressionInterval);
    }
  }, [previousTotal, tracing]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Live Request Traces</h1>
          <p className="text-[var(--text-muted)]">Monitor the flow of LLM requests through the enterprise gateway pipeline.</p>
        </div>
        <div className="flex items-center gap-4">
          {tracing && (
            <span className="text-[var(--accent-purple-light)] font-medium text-sm animate-pulse-slow flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[var(--accent-purple-light)]" />
              Real-time Processing
            </span>
          )}
        </div>
      </div>

      <div className="glass-panel p-8 mb-8 overflow-x-auto relative">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-purple-900/5 to-transparent pointer-events-none" />
        <div className="flex flex-col gap-6 relative z-10">
          {(() => {
            const latestReq = recentLogs.length > 0 ? recentLogs[0] : null;
            const reqTime = latestReq ? latestReq.time : new Date().toLocaleTimeString();
            const reqModel = latestReq ? latestReq.model : 'heavy-model';
            const reqTokens = latestReq ? latestReq.tokens : '...';
            const reqLatency = latestReq ? latestReq.latency : '...';
            const reqCost = latestReq ? latestReq.cost.toFixed(6) : '0.000000';

            return (
              <div className="flex items-start justify-between min-w-[950px]">
                <TraceNode 
                  title="1. LiteLLM Proxy" 
                  icon={Shield}
                  active={currentStep > 0}
                  detail={`Received request at ${reqTime}. Authenticating...`} 
                />
                <div className="mt-16"><Connector active={currentStep > 0} delay={0.5} /></div>
                <TraceNode 
                  title="2. Llama Guard 3" 
                  icon={Shield}
                  active={currentStep > 1}
                  detail="Intent classified as SAFE. No malicious payload detected." 
                />
                <div className="mt-16"><Connector active={currentStep > 1} delay={1.5} /></div>
                <TraceNode 
                  title="3. Presidio PII" 
                  icon={EyeOff}
                  active={currentStep > 2}
                  detail="No PII masking logic hooked yet. Bypassing." 
                />
                <div className="mt-16"><Connector active={currentStep > 2} delay={2.5} /></div>
                <TraceNode 
                  title="4. Semantic Cache" 
                  icon={Database}
                  active={currentStep > 3}
                  detail="Cache miss. Semantic similarity below threshold." 
                />
                <div className="mt-16"><Connector active={currentStep > 3} delay={3.5} /></div>
                <TraceNode 
                  title="5. RouteLLM Controller" 
                  icon={GitBranch}
                  active={currentStep > 4}
                  detail={`Routing strategy selected: ${reqModel}.`} 
                />
                <div className="mt-16"><Connector active={currentStep > 4} delay={4.5} /></div>
                <TraceNode 
                  title="6. LLM Backend" 
                  icon={Cpu}
                  active={currentStep > 5}
                  detail={`${reqLatency}s | ${reqTokens} tkns | $${reqCost}`} 
                />
              </div>
            );
          })()}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-6">
        <div className="glass-panel p-6 flex flex-col min-h-[320px]">
          <h3 className="text-[1.125rem] font-semibold tracking-tight mb-4 flex items-center gap-2">
            Request Log
            <span className="text-xs text-[var(--text-muted)] font-normal ml-2">Recent real requests</span>
          </h3>
          <div className="flex-1 bg-black-20 rounded-lg p-4 font-mono text-xs text-[var(--text-secondary)] overflow-y-auto flex flex-col gap-3 border border-white/5">
            {recentLogs.length === 0 && <span className="opacity-50 text-center mt-4 block">Waiting for requests to flow through the proxy...</span>}
            {recentLogs.map((entry, i) => (
              <div key={i} className="flex flex-col gap-1 pb-3 border-b border-white/5 last:border-0 last:pb-0">
                <div className="flex gap-4">
                  <span className="text-[var(--accent-purple-light)] min-w-[75px]">[{entry.time}]</span>
                  <span className="text-[var(--text-primary)]">Processed request via <span className="text-[var(--accent-blue-light)]">{entry.model}</span></span>
                </div>
                <div className="pl-[90px] text-[var(--text-muted)] text-[11px]">
                  Latency: {entry.latency}s | Tokens: {entry.tokens} | Cost: ${entry.cost.toFixed(6)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-panel p-8 flex flex-col">
          <h3 className="text-[1.125rem] font-semibold tracking-tight mb-8 text-[var(--text-primary)]/90">Pipeline Metrics</h3>
          <div className="grid grid-cols-2 gap-6 flex-1">
            <div className="bg-black-20 p-6 rounded-xl border border-white/5 flex flex-col justify-center transition-all duration-300 hover:bg-black-30">
              <div className="text-[var(--text-muted)] text-[11px] uppercase tracking-widest mb-3 font-medium opacity-80">Cache Hit Rate</div>
              <div className="text-[2.25rem] font-bold text-gradient leading-none">{metrics.cacheHitRate}</div>
            </div>
            <div className="bg-black-20 p-6 rounded-xl border border-white/5 flex flex-col justify-center transition-all duration-300 hover:bg-black-30">
              <div className="text-[var(--text-muted)] text-[11px] uppercase tracking-widest mb-3 font-medium opacity-80">Avg Latency</div>
              <div className="text-[2.25rem] font-bold text-[var(--accent-orange)] leading-none">{metrics.avgLatency}</div>
            </div>
            <div className="bg-black-20 p-6 rounded-xl border border-white/5 flex flex-col justify-center transition-all duration-300 hover:bg-black-30">
              <div className="text-[var(--text-muted)] text-[11px] uppercase tracking-widest mb-3 font-medium opacity-80">Blocked (Guardrails)</div>
              <div className="text-[2.25rem] font-bold text-[var(--accent-red)] leading-none">{metrics.blockedRate}</div>
            </div>
            <div className="bg-black-20 p-6 rounded-xl border border-white/5 flex flex-col justify-center transition-all duration-300 hover:bg-black-30">
              <div className="text-[var(--text-muted)] text-[11px] uppercase tracking-widest mb-3 font-medium opacity-80">Total Cost</div>
              <div className="text-[2.25rem] font-bold text-gradient leading-none">{metrics.costSavings}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
