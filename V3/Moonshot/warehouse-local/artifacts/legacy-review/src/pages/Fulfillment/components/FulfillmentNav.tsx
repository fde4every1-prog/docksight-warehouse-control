import React from 'react';
import { Link, useLocation } from 'wouter';
import { cn } from '@/lib/utils';
import { Database, Settings, LineChart } from 'lucide-react';
import { usePersona } from '@/contexts/PersonaContext';

export function FulfillmentNav({ active }: { active: string }) {
  const [location] = useLocation();
  const { role } = usePersona();

  const links = [
    ...(role !== 'supervisor' ? [
      { href: '/fulfillment/resources', label: 'Resources', icon: Database, id: 'resources' }
    ] : []),
    ...(active !== 'dashboard' && (role === 'supervisor' || role === 'admin') ? [
      { href: '/fulfillment/demand-forecasts', label: 'Demand Forecasts', icon: LineChart, id: 'demand-forecasts' },
    ] : []),
    ...(role === 'admin' ? [
      { href: '/fulfillment/config', label: 'Config', icon: Settings, id: 'config' }
    ] : []),
  ];

  if (links.length === 0) return null;

  return (
    <div className="flex items-center gap-1 border-b border-border/60 pb-4 mb-4 overflow-x-auto hide-scrollbar">
      {links.map((link) => {
        const Icon = link.icon;
        const isActive = active === link.id || location === link.href;
        return (
          <Link
            key={link.id}
            href={link.href}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
              isActive 
                ? "bg-primary text-primary-foreground" 
                : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {link.label}
          </Link>
        );
      })}
      <div className="flex-1" />
    </div>
  );
}