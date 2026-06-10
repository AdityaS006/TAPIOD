import React, { useState, useEffect } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend, Cell } from 'recharts';
import { TrendingUp, Activity, DollarSign, ShieldAlert } from 'lucide-react';

const StatCard = ({ title, value, sub, icon: Icon, colorClass }) => (
  <div className="glass-panel" style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column' }}>
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-muted" style={{ fontSize: '0.875rem', fontWeight: 500 }}>{title}</h3>
      <div style={{ padding: '0.5rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
        <Icon size={20} className={colorClass} />
      </div>
    </div>
    <div className="heading-lg mb-1">{value}</div>
    <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
      {sub}
    </div>
  </div>
);

const Observability = () => {
  const [latencyData, setLatencyData] = useState([]);
  const [routingData, setRoutingData] = useState([]);
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
    <div>
      <div className="mb-8 flex justify-between items-end">
        <div>
          <h1 className="heading-lg mb-2">Observability Dashboard</h1>
          <p className="text-muted">Analytics, cost tracking, and gateway health.</p>
        </div>
        <select className="input-field" style={{ width: '150px', background: 'var(--bg-panel)' }}>
          <option>Last 24 Hours</option>
          <option>Last 7 Days</option>
          <option>Last 30 Days</option>
        </select>
      </div>

      <div className="grid grid-cols-4 mb-8">
        <StatCard title="Total Requests" value={stats.totalRequests} sub="Live Gateway Traffic" icon={Activity} colorClass="text-accent-blue" />
        <StatCard title="Cache Hit Rate" value={stats.cacheHitRate} sub="Saves latency & cost" icon={TrendingUp} colorClass="text-accent-green" />
        <StatCard title="Total Spend" value={stats.totalSpend} sub="Token cost estimation" icon={DollarSign} colorClass="text-accent-purple" />
        <StatCard title="Guardrail Blocks" value={stats.guardrailBlocks} sub="Presidio + Llama Guard" icon={ShieldAlert} colorClass="text-accent-red" />
      </div>

      <div className="grid grid-cols-2">
        <div className="glass-panel" style={{ padding: '1.5rem', height: '400px' }}>
          <h3 className="heading-sm mb-6">P99 Latency by Route (ms)</h3>
          <ResponsiveContainer width="100%" height="85%">
            <AreaChart data={latencyData}>
              <defs>
                <linearGradient id="colorHeavy" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent-purple)" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="var(--accent-purple)" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="colorFast" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--accent-blue)" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="var(--accent-blue)" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="time" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip 
                contentStyle={{ background: 'var(--bg-dark)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
                itemStyle={{ color: 'var(--text-primary)' }}
              />
              <Legend iconType="circle" />
              <Area type="monotone" dataKey="heavy" name="Heavy Models (Claude/GPT-4o)" stroke="var(--accent-purple)" fillOpacity={1} fill="url(#colorHeavy)" />
              <Area type="monotone" dataKey="fast" name="Fast Models (GPT-4o-mini)" stroke="var(--accent-blue)" fillOpacity={1} fill="url(#colorFast)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="glass-panel" style={{ padding: '1.5rem', height: '400px' }}>
          <h3 className="heading-sm mb-6">Traffic Distribution</h3>
          <ResponsiveContainer width="100%" height="85%">
            <BarChart data={routingData} layout="vertical" margin={{ top: 0, right: 30, left: 40, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
              <XAxis type="number" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis dataKey="name" type="category" stroke="var(--text-muted)" fontSize={12} tickLine={false} axisLine={false} width={120} />
              <Tooltip 
                cursor={{fill: 'rgba(255,255,255,0.05)'}}
                contentStyle={{ background: 'var(--bg-dark)', border: '1px solid var(--border-color)', borderRadius: '8px' }}
              />
              <Bar dataKey="value" fill="var(--accent-blue)" radius={[0, 4, 4, 0]}>
                {routingData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={
                    entry.name === 'Cache Hit' ? 'var(--accent-green)' :
                    entry.name === 'Blocked' ? 'var(--accent-red)' :
                    entry.name.includes('heavy') || entry.name.includes('70b') ? 'var(--accent-purple)' : 'var(--accent-blue)'
                  }/>
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default Observability;
