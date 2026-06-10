import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, Settings, BarChart2, Shield, Terminal } from 'lucide-react';

const Sidebar = () => {
  const navItems = [
    { name: 'Live Traces', path: '/', icon: Activity },
    { name: 'Input/Output', path: '/playground', icon: Terminal },
    { name: 'Configuration', path: '/config', icon: Settings },
    { name: 'Observability', path: '/observability', icon: BarChart2 },
  ];

  return (
    <aside className="glass-panel" style={{ 
      width: '260px', 
      height: 'calc(100vh - 2rem)', 
      position: 'sticky', 
      top: '1rem',
      display: 'flex',
      flexDirection: 'column',
      padding: '1.5rem',
      margin: '1rem'
    }}>
      <div className="flex items-center gap-2 mb-8">
        <Shield className="text-accent-purple" size={28} />
        <h1 className="heading-sm text-gradient">TAPIOD</h1>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-sm)',
              color: isActive ? 'white' : 'var(--text-secondary)',
              background: isActive ? 'rgba(139, 92, 246, 0.15)' : 'transparent',
              textDecoration: 'none',
              fontWeight: 500,
              transition: 'all var(--transition-fast)',
              border: isActive ? '1px solid rgba(139, 92, 246, 0.3)' : '1px solid transparent'
            })}
          >
            <item.icon size={20} style={{ 
              color: 'inherit',
              opacity: 0.8
            }} />
            {item.name}
          </NavLink>
        ))}
      </nav>

      <div style={{
        padding: '1rem',
        background: 'rgba(0,0,0,0.2)',
        borderRadius: 'var(--radius-sm)',
        marginTop: 'auto'
      }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-muted" style={{ fontSize: '0.75rem' }}>Status</span>
          <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>Online</span>
        </div>
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          LiteLLM Proxy: v1.42.0
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
