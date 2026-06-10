"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Settings, BarChart2, Terminal, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

const Sidebar = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const pathname = usePathname();

  const navItems = [
    { name: 'Live Traces', path: '/', icon: Activity },
    { name: 'Input/Output', path: '/playground', icon: Terminal },
    { name: 'Configuration', path: '/config', icon: Settings },
    { name: 'Observability', path: '/observability', icon: BarChart2 },
  ];

  return (
    <motion.aside 
      initial={false}
      animate={{ width: isCollapsed ? 88 : 260 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="glass-panel flex flex-col rounded-none border-y-0 border-l-0 relative z-20 shrink-0" 
      style={{ height: '100vh', padding: '24px 16px', overflow: 'visible' }}
    >
      {/* Header */}
      <div className="flex items-center mb-8 h-10 px-1 overflow-visible whitespace-nowrap">
        <div className="w-8 h-8 flex items-center justify-center shrink-0">
          <img src="/logo.png" alt="TAPIOD Logo" className="w-full h-full object-contain" />
        </div>
        <AnimatePresence>
          {!isCollapsed && (
            <motion.h1 
              initial={{ opacity: 0, width: 0, marginLeft: 0 }}
              animate={{ opacity: 1, width: 'auto', marginLeft: 12 }}
              exit={{ opacity: 0, width: 0, marginLeft: 0 }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="text-xl font-medium tracking-wide text-white font-sans overflow-hidden"
            >
              TAPIOD
            </motion.h1>
          )}
        </AnimatePresence>
      </div>

      {/* Navigation */}
      <nav className="flex-col gap-2 flex-1 flex">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          
          return (
            <Link
              key={item.path}
              href={item.path}
              className="group relative flex items-center p-3 rounded-[var(--radius-md)] text-sm font-medium transition-colors"
              style={{
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                backgroundColor: isActive ? 'rgba(147, 51, 234, 0.1)' : 'transparent',
                border: isActive ? '1px solid rgba(147, 51, 234, 0.2)' : '1px solid transparent',
                boxShadow: isActive ? 'inset 0 0 12px rgba(147, 51, 234, 0.05)' : 'none'
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.color = 'var(--text-secondary)';
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              <div className="flex items-center justify-center shrink-0 w-6 h-6">
                <item.icon size={20} style={{ opacity: 0.9 }} />
              </div>
              
              <AnimatePresence>
                {!isCollapsed && (
                  <motion.span 
                    initial={{ opacity: 0, width: 0, marginLeft: 0 }}
                    animate={{ opacity: 1, width: 'auto', marginLeft: 12 }}
                    exit={{ opacity: 0, width: 0, marginLeft: 0 }}
                    transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                    className="whitespace-nowrap overflow-hidden"
                  >
                    {item.name}
                  </motion.span>
                )}
              </AnimatePresence>
              
              {/* Tooltip for collapsed state */}
              {isCollapsed && (
                <div className="absolute left-full ml-4 px-3 py-1.5 bg-[#1a1b1e] border border-white/10 rounded-md text-xs font-medium text-white opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity whitespace-nowrap z-50 shadow-xl">
                  {item.name}
                </div>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer Area */}
      <div className="mt-auto flex flex-col gap-4">
        {/* Status Panel */}
        <AnimatePresence>
          {!isCollapsed && (
            <motion.div 
              initial={{ opacity: 0, height: 0, marginBottom: 0 }}
              animate={{ opacity: 1, height: 'auto', marginBottom: 8 }}
              exit={{ opacity: 0, height: 0, marginBottom: 0, padding: 0, border: 'none' }}
              transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
              className="p-4 bg-[#1e1e20] rounded-lg border border-white/5 flex flex-col justify-center overflow-hidden whitespace-nowrap"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>Status</span>
                <span className="badge badge-success flex items-center gap-1">
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
                  Online
                </span>
              </div>
              <div className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                LiteLLM Proxy: <span style={{ color: 'var(--text-primary)', fontFamily: 'monospace' }}>v1.42.0</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Toggle Button */}
        <button 
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="flex items-center p-3 rounded-lg transition-colors cursor-pointer group whitespace-nowrap overflow-hidden"
          style={{ color: 'var(--text-secondary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--text-primary)';
            e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.05)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-secondary)';
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          <div className="flex items-center justify-center shrink-0 w-6 h-6">
            {isCollapsed ? <PanelLeftOpen size={20} className="group-hover:text-accent-purple transition-colors" /> : <PanelLeftClose size={20} className="group-hover:text-accent-purple transition-colors" />}
          </div>
          <AnimatePresence>
            {!isCollapsed && (
              <motion.span 
                initial={{ opacity: 0, width: 0, marginLeft: 0 }}
                animate={{ opacity: 1, width: 'auto', marginLeft: 12 }}
                exit={{ opacity: 0, width: 0, marginLeft: 0 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                className="font-medium text-sm overflow-hidden"
              >
                Collapse Sidebar
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  );
};

export default Sidebar;
