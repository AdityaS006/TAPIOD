"use client";

import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, Cell } from 'recharts';
import { TrendingUp, Activity, DollarSign, ShieldAlert } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  sub: string;
  icon: any;
  colorClass: string;
}

const StatCard = ({ title, value, sub, icon: Icon, colorClass }: StatCardProps) => (
  <div className="glass-panel p-6 flex flex-col justify-between h-full">
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-[var(--text-muted)] text-sm font-medium tracking-wide uppercase">{title}</h3>
      <div className="p-2 bg-white/5 rounded-lg border border-white/5">
        <Icon size={20} className={colorClass} />
      </div>
    </div>
    <div>
      <div className="text-[2.25rem] font-bold mb-1 tracking-tight">{value}</div>
      <div className="text-xs text-[var(--text-secondary)] opacity-80">
        {sub}
      </div>
    </div>
  </div>
);

export default function Observability() {
  const [latencyData, setLatencyData] = useState<any[]>([]);
  const [routingData, setRoutingData] = useState<any[]>([]);
  const [stats, setStats] = useState({
    totalRequests: '0',
    cacheHitRate: '0%',
    totalSpend: '$0.00',
    guardrailBlocks: '0%'
  });

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [obsRes, metRes] = await Promise.all([
          fetch('http://localhost:4001/api/observability'),
          fetch('http://localhost:4001/api/metrics')
        ]);
        if (obsRes.ok && metRes.ok) {
          const obs = await obsRes.json();
          const met = await metRes.json();
          
          setLatencyData(obs.latencyData || []);
          setRoutingData(obs.routingData || []);
          
          const total = met.total_requests || 1;
          setStats({
            totalRequests: met.total_requests.toString(),
            cacheHitRate: `${((met.cache_hits / total) * 100).toFixed(1)}%`,
            totalSpend: `$${met.total_cost.toFixed(4)}`,
            guardrailBlocks: `${((met.blocked_requests / total) * 100).toFixed(1)}%`
          });
        }
      } catch (err) {
        // Handle error silently for prototype
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full w-full relative">
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="text-[2.25rem] font-bold tracking-tight mb-2">Observability Dashboard</h1>
          <p className="text-[var(--text-muted)]">Analytics, cost tracking, and gateway health.</p>
        </div>
        <select className="bg-[#1e1e20] border border-white/10 text-[var(--text-primary)] text-sm rounded-lg py-2 px-4 focus:outline-none focus:border-[var(--accent-purple)] transition-colors">
          <option>Last 24 Hours</option>
          <option>Last 7 Days</option>
          <option>Last 30 Days</option>
        </select>
      </div>

      <div className="grid grid-cols-4 gap-6 mb-8">
        <StatCard title="Total Requests" value={stats.totalRequests} sub="Live Gateway Traffic" icon={Activity} colorClass="text-[var(--accent-blue)]" />
        <StatCard title="Cache Hit Rate" value={stats.cacheHitRate} sub="Saves latency & cost" icon={TrendingUp} colorClass="text-[var(--accent-green)]" />
        <StatCard title="Total Spend" value={stats.totalSpend} sub="Token cost estimation" icon={DollarSign} colorClass="text-[var(--accent-purple-light)]" />
        <StatCard title="Guardrail Blocks" value={stats.guardrailBlocks} sub="Presidio + Llama Guard" icon={ShieldAlert} colorClass="text-[var(--accent-red)]" />
      </div>

      <div className="grid grid-cols-2 gap-6 flex-1 min-h-[400px]">
        <div className="glass-panel p-6 flex flex-col h-full">
          <h3 className="text-[1.125rem] font-semibold tracking-tight mb-6 flex items-center gap-2">
            P99 Latency by Route
            <span className="text-xs font-normal text-[var(--text-muted)] bg-white/5 border border-white/5 px-2 py-1 rounded">ms</span>
          </h3>
          <div className="flex-1 relative min-h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={latencyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorHeavy" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-purple-light)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-purple-light)" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorFast" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-blue-light)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-blue-light)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="time" stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} dy={10} />
                <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} dx={-10} />
                <Tooltip 
                  contentStyle={{ background: 'var(--bg-dark)', border: '1px solid var(--border-color)', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)' }}
                  itemStyle={{ color: 'var(--text-primary)', fontSize: '13px' }}
                  labelStyle={{ color: 'var(--text-muted)', marginBottom: '4px', fontSize: '12px' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '20px' }} />
                <Area type="monotone" dataKey="heavy" name="Heavy Models (Claude/GPT-4o)" stroke="var(--accent-purple-light)" strokeWidth={2} fillOpacity={1} fill="url(#colorHeavy)" />
                <Area type="monotone" dataKey="fast" name="Fast Models (GPT-4o-mini)" stroke="var(--accent-blue-light)" strokeWidth={2} fillOpacity={1} fill="url(#colorFast)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-panel p-6 flex flex-col h-full">
          <h3 className="text-[1.125rem] font-semibold tracking-tight mb-6">Traffic Distribution</h3>
          <div className="flex-1 relative min-h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={routingData} layout="vertical" margin={{ top: 0, right: 30, left: 30, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                <XAxis type="number" stroke="var(--text-muted)" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis dataKey="name" type="category" stroke="var(--text-primary)" fontSize={12} tickLine={false} axisLine={false} width={100} />
                <Tooltip 
                  cursor={{fill: 'rgba(255,255,255,0.03)'}}
                  contentStyle={{ background: 'var(--bg-dark)', border: '1px solid var(--border-color)', borderRadius: '8px', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)' }}
                  itemStyle={{ color: 'var(--text-primary)', fontSize: '13px' }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={40}>
                  {routingData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={
                      entry.name === 'Cache Hit' ? 'var(--accent-green)' :
                      entry.name === 'Blocked' ? 'var(--accent-red)' :
                      entry.name.includes('heavy') || entry.name.includes('70b') ? 'var(--accent-purple-light)' : 'var(--accent-blue-light)'
                    }/>
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
