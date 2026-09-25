import React from 'react';
import { Link, useLocation } from 'wouter';
import { useHealthCheck } from '@workspace/api-client-react';
import { Activity, LayoutDashboard, Box, FileText, Bot, Layers, Network, Wrench, Shield, Settings, LineChart, BarChart } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePersona } from '@/contexts/PersonaContext';

export function Layout({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();
  const { data: health } = useHealthCheck();
  const { role, setRole } = usePersona();

  const legacyNavItems = role === 'admin' ? [] : [
    { href: '/overview', label: 'Legacy Overview', icon: LayoutDashboard },
    { href: '/fleet', label: 'Fleet', icon: Bot },
    { href: '/inventory', label: 'Inventory', icon: Box },
    { href: '/tasks', label: 'Tasks', icon: Layers },
    { href: '/evidence', label: 'Evidence', icon: FileText },
    { href: '/allocator', label: 'Allocator', icon: Network },
  ];

  const roleNavItems = {
    fleet: [
      { href: '/workspace/fleet', label: 'Fleet Home', icon: Wrench },
      { href: '/fleet/predictive-maintenance', label: 'Predictive Maintenance Advisory', icon: Activity },
      { href: '/workspace/monthly-kpis', label: 'Metrics Dashboard', icon: BarChart },
    ],
    supervisor: [
      { href: '/fulfillment', label: 'Order Fulfillment', icon: Network },
      { href: '/workspace/supervisor', label: 'Supervisor Workspace', icon: Shield },
      { href: '/fulfillment/demand-forecasts', label: 'Demand Forecasts', icon: LineChart },
      { href: '/fleet/predictive-maintenance', label: 'Predictive Maintenance Advisory', icon: Activity },
      { href: '/workspace/monthly-kpis', label: 'Metrics Dashboard', icon: BarChart },
    ],
    admin: [
      { href: '/workspace/admin', label: 'Admin Home', icon: Settings },
      { href: '/fulfillment/resources', label: 'All Resources', icon: Box },
      { href: '/fulfillment/config', label: 'System Config', icon: Settings },
    ]
  };

  const currentRoleNavItems = roleNavItems[role];
  const allNavItems = [...currentRoleNavItems, ...legacyNavItems];

  return (
    <div className="min-h-[100dvh] flex flex-col bg-background text-foreground font-mono">
      <header className="h-14 border-b flex items-center px-6 justify-between bg-card text-card-foreground shrink-0 z-10 sticky top-0">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 bg-primary rounded-sm flex items-center justify-center font-bold text-primary-foreground text-xs">DS</div>
          <span className="font-bold text-sm tracking-widest uppercase text-foreground">DockSight</span>
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          <select 
            value={role} 
            onChange={(e: any) => setRole(e.target.value)}
            className="w-[180px] h-8 text-xs font-bold uppercase tracking-wider bg-secondary rounded-sm border px-2 focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="fleet">Fleet Manager</option>
            <option value="supervisor">Order Supervisor</option>
            <option value="admin">Admin Role</option>
          </select>
          <div className="flex items-center gap-1.5 text-muted-foreground ml-2 hidden md:flex">
            <Activity className="h-4 w-4" />
            <span className={cn(health?.status === 'ok' ? 'text-success' : 'text-warning')}>
              {health ? `SYS:${health.status.toUpperCase()}` : 'CONNECTING...'}
            </span>
          </div>
        </div>
      </header>
      <nav aria-label="Inspection views" className="md:hidden flex flex-wrap gap-1 border-b p-2 bg-card">
        {allNavItems.map(item => (
          <Link key={item.href} href={item.href}
            className={cn("px-3 py-2 text-xs rounded-sm", location === item.href || (location.startsWith(item.href) && item.href !== '/workspace/' + role) ? "bg-primary/10 text-primary font-bold" : "text-muted-foreground")}
            aria-current={location === item.href ? 'page' : undefined}>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-56 border-r bg-muted/30 shrink-0 hidden md:flex flex-col">
          <nav className="p-4 space-y-1 flex-1 overflow-y-auto">
            <div className="text-xs font-bold text-muted-foreground mb-4 mt-2 tracking-widest uppercase">{role} Workspace</div>
            {currentRoleNavItems.map((item) => {
              const active = item.href === '/fulfillment'
                ? location === '/fulfillment' || location.startsWith('/fulfillment/orders')
                : location === item.href || location.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm rounded-sm transition-colors",
                    active 
                      ? "bg-primary/10 text-primary font-bold border-l-2 border-primary" 
                      : "text-muted-foreground hover:bg-muted hover:text-foreground border-l-2 border-transparent"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </Link>
              );
            })}

            {legacyNavItems.length > 0 && <div className="text-xs font-bold text-muted-foreground mb-4 mt-8 tracking-widest uppercase">Legacy Views</div>}
            {legacyNavItems.map((item) => {
              const active = location === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 text-sm rounded-sm transition-colors",
                    active 
                      ? "bg-primary/10 text-primary font-bold border-l-2 border-primary" 
                      : "text-muted-foreground hover:bg-muted hover:text-foreground border-l-2 border-transparent"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </aside>
        
        <main className="flex-1 overflow-auto bg-background">
          {children}
        </main>
      </div>
    </div>
  );
}
