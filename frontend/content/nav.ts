import { Activity, Settings, BarChart2, Terminal, Brain } from 'lucide-react';

export const NAV_LINKS = [
  { name: 'Live Traces',    path: '/',             icon: Activity  },
  { name: 'Input/Output',   path: '/playground',   icon: Terminal  },
  { name: 'Configuration',  path: '/config',       icon: Settings  },
  { name: 'Observability',  path: '/observability', icon: BarChart2 },
  { name: 'Memory',         path: '/memory',       icon: Brain     },
] as const;
