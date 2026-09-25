import React, { useState } from 'react';
import { usePersona } from '@/contexts/PersonaContext';
import { useMonthlyKpis, Metric, MetricValue } from '@/hooks/use-monthly-kpis';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Select } from '@/components/ui/select';
import { AlertCircle, ArrowDown, ArrowUp, BarChart, Info, RefreshCcw } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';

function formatValue(value: number | null, unit: string): string {
  if (value === null) return '—';
  
  if (unit === '%') {
    return `${value.toFixed(1)}%`;
  }
  if (unit === 'hours') {
    return `${value.toFixed(2)} h`;
  }
  if (unit === 'per 1,000 tasks') {
    return `${value.toFixed(2)}`;
  }
  return value.toString();
}

function MetricDetailsList({ title, value }: { title: string, value: MetricValue }) {
  const hasExclusions = Object.keys(value.exclusions).length > 0;
  return (
    <div className="text-xs space-y-1 mt-2 mb-4">
      <div className="font-semibold border-b pb-1 mb-1">{title}</div>
      <div className="grid grid-cols-[1fr_2fr] gap-x-2 gap-y-1">
        <span className="text-muted-foreground">Basis:</span>
        <span className="break-words min-w-0">{value.basis}</span>
        
        <span className="text-muted-foreground">Coverage:</span>
        <span className="break-all">{value.coverage.start ? `${value.coverage.start} to ${value.coverage.end}` : 'Undated / unavailable'}</span>
        
        <span className="text-muted-foreground">Calculation:</span>
        <span>
          {value.numerator.toLocaleString()} / {value.denominator.toLocaleString()} 
        </span>
        
        {hasExclusions && (
          <>
            <span className="text-muted-foreground mt-1">Data audit:</span>
            <div className="mt-1">
              {Object.entries(value.exclusions).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-dashed border-border/50 last:border-0">
                  <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}</span>
                  <span>{v.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function MetricRow({ metric }: { metric: Metric }) {
  const isPercent = metric.unit === '%';
  const hasChange = metric.change.absolute !== null;
  const isPositiveChange = hasChange && metric.change.absolute! > 0;
  const isNegativeChange = hasChange && metric.change.absolute! < 0;
  const isZeroChange = hasChange && metric.change.absolute === 0;

  let isGood = false;
  let isBad = false;
  if (hasChange && !isZeroChange) {
    if (metric.direction === 'higher') {
      isGood = isPositiveChange;
      isBad = isNegativeChange;
    } else {
      isGood = isNegativeChange;
      isBad = isPositiveChange;
    }
  }

  const changeDisplay = () => {
    if (!hasChange) return <span className="text-muted-foreground text-sm">No baseline available</span>;
    if (isZeroChange) return <span className="text-muted-foreground text-sm flex items-center"><ArrowDown className="h-4 w-4 mr-1 opacity-0" />0.0 change</span>;

    const Icon = isPositiveChange ? ArrowUp : ArrowDown;
    const colorClass = isGood ? 'text-green-500' : isBad ? 'text-destructive' : 'text-muted-foreground';
    
    let changeText = '';
    if (isPercent && metric.change.percentage_points !== null) {
      changeText = `${Math.abs(metric.change.percentage_points).toFixed(1)} pp`;
    } else {
      changeText = `${Math.abs(metric.change.absolute!).toFixed(2)} ${metric.unit}`;
    }

    return (
      <span className={`text-sm flex items-center font-medium ${colorClass}`}>
        <Icon className="h-4 w-4 mr-1" />
        {changeText}
      </span>
    );
  };

  return (
    <tbody className="border-b last:border-0">
      <tr className="align-top">
        <th scope="row" className="p-4 text-left font-normal">
          <div className="font-bold text-sm">{metric.label}{metric.id === 'interventions' ? ' (proxy)' : ''}</div>
          <div className="text-xs text-muted-foreground mt-2">{metric.unit} · {metric.direction === 'higher' ? 'Higher is better' : 'Lower is better'}</div>
        </th>
        {[metric.august, metric.september].map((value, index) => (
          <td key={index} className={`p-4 ${index === 1 ? 'text-primary' : ''}`}>
            <div className="text-xl font-bold tabular-nums whitespace-nowrap">{value.value === null ? 'Unavailable' : formatValue(value.value, metric.unit)}</div>
          </td>
        ))}
        <td className="p-4">{changeDisplay()}</td>
      </tr>
      <tr>
      <td colSpan={4} className="px-4 pb-3">
        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="details" className="border-none">
            <AccordionTrigger className="py-1 hover:no-underline text-xs font-medium text-muted-foreground">
              Metric Details & Calculation
            </AccordionTrigger>
            <AccordionContent className="pt-3 pb-1">
               <p className="text-xs mb-4"><strong>Formula: </strong>{metric.formula}</p>
              {metric.details.length > 0 && (
                <ul className="list-disc pl-4 space-y-1 text-xs text-foreground/80 mb-4 bg-muted/30 p-2 rounded-md">
                  {metric.details.map((detail, idx) => (
                    <li key={idx}>{detail}</li>
                  ))}
                </ul>
              )}
              
               <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2">
                <MetricDetailsList title="August" value={metric.august} />
                <MetricDetailsList title="September" value={metric.september} />
              </div>
              
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </td>
      </tr>
    </tbody>
  );
}

export default function MonthlyKpis() {
  const { role } = usePersona();
  const [warehouse, setWarehouse] = useState<string>('all');
  
  const { data, isLoading, error, refetch } = useMonthlyKpis(role, warehouse);

  if (isLoading) {
    return (
      <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-6">
          <div className="w-full max-w-md">
            <Skeleton className="h-8 w-3/4 mb-2" />
            <Skeleton className="h-4 w-full" />
          </div>
          <Skeleton className="h-10 w-48" />
        </div>
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 md:p-8 max-w-7xl mx-auto flex-1 flex items-center justify-center min-h-[60vh]">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error loading KPIs</AlertTitle>
          <AlertDescription className="mt-2 flex flex-col gap-4">
            <p>{error instanceof Error ? error.message : 'An unknown error occurred.'}</p>
            <Button onClick={() => refetch()} variant="outline" size="sm" className="w-fit self-end border-destructive/20 hover:bg-destructive/10">
              <RefreshCcw className="mr-2 h-4 w-4" />
              Try again
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-6 md:p-8 max-w-7xl mx-auto flex-1 flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4 text-muted-foreground">
          <BarChart className="h-12 w-12 mx-auto opacity-20" />
          <p>No monthly KPI data available.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 border-b pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight mb-2">Metrics Dashboard</h1>
          <p className="text-muted-foreground max-w-2xl text-sm">
            {data.note || 'Operational comparison of August baseline versus September full-month scenario.'}
          </p>
          <p className="text-xs text-muted-foreground max-w-2xl mt-3">
            August 2026 baseline versus a separate September 1–30 scenario.
            September is incomplete as of September 22; future scenario dates are not observed results.
          </p>
        </div>
        
        <div className="w-full md:w-64 shrink-0">
          <div className="text-xs font-semibold mb-2 uppercase tracking-wider text-muted-foreground">Filter Facility</div>
          <Select value={warehouse} onChange={(e) => setWarehouse(e.target.value)}>
            <option value="all">All Facilities</option>
            {data.warehouses.map((wh) => (
              <option key={wh} value={wh}>{wh}</option>
            ))}
          </Select>
        </div>
      </div>

      {data.metrics.length > 0 ? (
        <div className="border rounded-xl bg-card overflow-x-auto" role="region" aria-label="August and September metrics comparison" tabIndex={0}>
          <table className="w-full min-w-[680px] text-left">
            <caption className="sr-only">August and September 2026 metrics comparison</caption>
            <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground border-b">
              <tr>
                <th scope="col" className="p-4 w-[34%]">Metric</th>
                <th scope="col" className="p-4">Baseline</th>
                <th scope="col" className="p-4">Current</th>
                <th scope="col" className="p-4">Difference</th>
              </tr>
            </thead>
            {data.metrics.map(metric => <MetricRow key={metric.id} metric={metric} />)}
          </table>
        </div>
      ) : (
        <div className="py-12 text-center border rounded-xl bg-card/50">
          <p className="text-muted-foreground">No metrics found for the selected facility.</p>
        </div>
      )}

      <div className="mt-12">
        <Accordion type="single" collapsible className="w-full bg-card border rounded-xl px-6 py-2 shadow-sm">
          <AccordionItem value="methodology" className="border-none">
            <AccordionTrigger className="hover:no-underline py-4">
              <div className="flex items-center gap-2">
                <Info className="h-5 w-5 text-primary" />
                <span className="font-semibold text-lg tracking-tight">Methodology & Provenance</span>
              </div>
            </AccordionTrigger>
            <AccordionContent className="pb-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4 border-t">
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-3">Data Sources</h3>
                    <ul className="list-disc pl-5 space-y-1.5 text-sm">
                      {data.provenance.sources.map((source, idx) => (
                        <li key={idx} className="text-foreground/90">{source}</li>
                      ))}
                    </ul>
                  </div>
                  
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-3">Key Assumptions</h3>
                    <ul className="list-disc pl-5 space-y-1.5 text-sm">
                      {data.provenance.assumptions.map((assumption, idx) => (
                        <li key={idx} className="text-foreground/90">{assumption}</li>
                      ))}
                    </ul>
                  </div>
                </div>
                
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-3">Scenario Details</h3>
                    <div className="bg-muted p-3 rounded-md text-sm font-mono space-y-2 break-words">
                      <div className="flex flex-col sm:flex-row sm:justify-between pb-1 border-b border-border/50">
                        <span className="text-muted-foreground">Version:</span>
                        <span className="font-semibold">{data.provenance.scenario_version}</span>
                      </div>
                      <div className="flex flex-col sm:flex-row sm:justify-between pb-1 border-b border-border/50">
                        <span className="text-muted-foreground">August Period:</span>
                        <span className="font-semibold text-right">{data.periods.august.start} to {data.periods.august.end}</span>
                      </div>
                      <div className="flex flex-col sm:flex-row sm:justify-between pb-1 border-b border-border/50">
                        <span className="text-muted-foreground">September Period:</span>
                        <span className="font-semibold text-right">{data.periods.september.start} to {data.periods.september.end}</span>
                      </div>
                    </div>
                  </div>
                  
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
    </div>
  );
}