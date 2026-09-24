import { Link } from 'wouter';
import { MonitorDot, Shield } from 'lucide-react';
import { usePersona } from '@/hooks/use-persona';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export function Header() {
  const { persona, setPersona } = usePersona();

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-primary text-primary-foreground shadow-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="rounded-md bg-white/10 p-2">
            <MonitorDot className="h-5 w-5 text-accent" />
          </div>
          <div className="min-w-0">
            <Link href="/">
              <p className="truncate font-mono text-base font-bold tracking-tight hover:text-accent sm:text-lg transition-colors cursor-pointer">
                Fleet Simulator
              </p>
            </Link>
            <div className="hidden items-center gap-3 sm:flex">
              <p className="text-[10px] uppercase tracking-[0.18em] text-primary-foreground/60">
                Core-owned execution
              </p>
              <div className="h-3 w-px bg-primary-foreground/20" />
              <Link href="/batching">
                <p className="text-[10px] uppercase tracking-[0.18em] text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer">
                  Batching Advisor
                </p>
              </Link>
              <div className="h-3 w-px bg-primary-foreground/20" />
              <Link href="/transfer-lab">
                <p className="text-[10px] uppercase tracking-[0.18em] text-emerald-400 hover:text-emerald-300 transition-colors cursor-pointer">
                  Transfer Lab
                </p>
              </Link>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Shield className="hidden h-4 w-4 text-accent sm:block" />
          <span className="sr-only">Simulation role</span>
          <Select
            value={persona}
            onValueChange={(value: 'fleet' | 'supervisor' | 'admin') => setPersona(value)}
          >
            <SelectTrigger
              aria-label="Simulation role"
              className="h-9 w-[126px] border-primary-foreground/20 bg-primary/50 font-mono text-xs font-bold uppercase ring-offset-primary sm:w-[148px]"
            >
              <SelectValue placeholder="Select role" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fleet" className="font-mono text-xs font-medium uppercase">
                Fleet Ops
              </SelectItem>
              <SelectItem value="supervisor" className="font-mono text-xs font-medium uppercase">
                Supervisor
              </SelectItem>
              <SelectItem value="admin" className="font-mono text-xs font-medium uppercase">
                Admin
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </header>
  );
}