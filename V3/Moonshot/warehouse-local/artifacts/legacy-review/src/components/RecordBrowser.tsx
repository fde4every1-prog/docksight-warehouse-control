import React, { useState, useEffect, useRef } from 'react';
import { useGetReviewRecords, useGetReviewOverview, ReviewRecord } from '@workspace/api-client-react';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Search, Filter, AlertTriangle, ChevronLeft, ChevronRight, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface RecordBrowserProps {
  dataset: 'robots' | 'inventory' | 'tasks' | 'maintenance' | 'priorities' | 'zones' | 'telemetry';
  title: string;
  description: string;
  headerContent?: React.ReactNode;
}

export function RecordBrowser({ dataset, title, description, headerContent }: RecordBrowserProps) {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [site, setSite] = useState<string>('');
  const [flagged, setFlagged] = useState<boolean>(false);
  const [page, setPage] = useState(0);
  const [selectedRecord, setSelectedRecord] = useState<ReviewRecord | null>(null);

  const limit = 50;

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0); // reset page on search
    }, 400);
    return () => clearTimeout(timer);
  }, [search]);

  // Reset page on filter changes
  useEffect(() => {
    setPage(0);
  }, [site, flagged]);

  const { data: overview } = useGetReviewOverview();
  
  const { data: recordsData, isLoading, isError } = useGetReviewRecords(dataset, {
    search: debouncedSearch || undefined,
    site: site || undefined,
    flagged: flagged || undefined,
    offset: page * limit,
    limit
  }, { query: { keepPreviousData: true } as any });

  const total = recordsData?.total || 0;
  const maxPage = Math.max(0, Math.ceil(total / limit) - 1);

  return (
    <div className="flex flex-col h-full font-sans">
      <div className="p-6 border-b shrink-0 bg-card flex flex-col gap-6">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
            <p className="text-muted-foreground text-sm max-w-2xl mt-1">{description}</p>
          </div>
          <Badge variant="outline" className="font-mono bg-muted">{total} records</Badge>
        </div>

        {headerContent && (
          <div className="w-full">
            {headerContent}
          </div>
        )}

        <div className="flex flex-wrap gap-4 items-end">
          <div className="flex-1 min-w-[200px] max-w-sm relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input 
              placeholder="Search values..." 
              className="pl-9 font-mono text-sm"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          
          <div className="w-48">
            <Select value={site} onChange={(e) => setSite(e.target.value)} className="font-mono text-sm">
              <option value="">All Sites</option>
              {overview?.sites.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </div>

          <Button 
            variant={flagged ? 'default' : 'outline'} 
            onClick={() => setFlagged(!flagged)}
            className="font-mono text-sm gap-2"
          >
            <Filter className="h-4 w-4" />
            Flagged Only
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6 bg-muted/20">
        {isLoading && !recordsData ? (
          <div className="space-y-2">
            {[...Array(10)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : isError ? (
          <div className="p-8 text-center text-destructive bg-destructive/10 rounded-sm border border-destructive/20">
            <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
            <p>Error loading records</p>
          </div>
        ) : recordsData?.records.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground border-2 border-dashed rounded-sm">
            <Filter className="h-8 w-8 mx-auto mb-3 opacity-20" />
            <p>No records found matching current filters.</p>
          </div>
        ) : (
          <div className="bg-card border rounded-sm shadow-sm overflow-hidden">
             <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">Row</TableHead>
                  {recordsData?.columns.slice(0, 5).map(col => (
                    <TableHead key={col} className="font-mono text-xs max-w-[200px] truncate">{col}</TableHead>
                  ))}
                  <TableHead className="w-32 text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recordsData?.records.map((record) => (
                  <TableRow 
                    key={record.rowNumber} 
                    className="cursor-pointer hover:bg-muted/50 group"
                    onClick={() => setSelectedRecord(record)}
                  >
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      #{record.rowNumber}
                    </TableCell>
                    {recordsData.columns.slice(0, 5).map(col => (
                      <TableCell key={col} className="font-mono text-xs max-w-[200px] truncate">
                        {record.values[col] || '-'}
                      </TableCell>
                    ))}
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {record.legacyAvailable !== undefined && (
                          <span className={cn(
                            "text-xs font-mono font-bold", 
                            record.legacyAvailable > 0 ? "text-success" : "text-destructive"
                          )}>
                            AVAIL: {record.legacyAvailable}
                          </span>
                        )}
                        {record.flags && record.flags.length > 0 && (
                          <Badge variant="warning" className="h-5 rounded-sm px-1.5 font-mono text-[10px]">
                            {record.flags.length} FLAGS
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      {/* Pagination Footer */}
      <div className="h-14 border-t bg-card px-6 flex items-center justify-between shrink-0 font-mono text-sm">
        <div className="text-muted-foreground">
          Showing {recordsData ? (page * limit) + 1 : 0} to {recordsData ? Math.min((page + 1) * limit, total) : 0} of {total}
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" 
            size="sm" 
            disabled={page === 0} 
            onClick={() => setPage(p => Math.max(0, p - 1))}
          >
            <ChevronLeft className="h-4 w-4 mr-1" /> Prev
          </Button>
          <span className="px-4 text-xs font-bold bg-muted py-1.5 rounded-sm">
            PAGE {page + 1} / {maxPage + 1 || 1}
          </span>
          <Button 
            variant="outline" 
            size="sm" 
            disabled={page >= maxPage} 
            onClick={() => setPage(p => p + 1)}
          >
            Next <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </div>

      {/* Record Inspector Dialog */}
      <Dialog open={!!selectedRecord} onOpenChange={(open) => !open && setSelectedRecord(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col font-sans">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              <span className="font-mono text-muted-foreground">#{selectedRecord?.rowNumber}</span>
              Record Inspector
            </DialogTitle>
            <DialogDescription>
              Inspecting raw legacy data and synthetic review annotations.
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex-1 overflow-auto py-4 space-y-6">
            {selectedRecord?.flags && selectedRecord.flags.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-bold tracking-tight uppercase text-warning flex items-center gap-2 border-b pb-1">
                  <AlertTriangle className="h-4 w-4" /> Review Annotations (Flags)
                </h3>
                <div className="flex flex-col gap-2">
                  {selectedRecord.flags.map((flag, i) => (
                    <div key={i} className="bg-warning/10 text-warning-foreground border border-warning/20 p-3 text-sm font-mono rounded-sm">
                      {flag}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {selectedRecord?.flags?.length === 0 && (
              <div className="bg-success/10 text-success-foreground border border-success/20 p-3 text-sm font-mono rounded-sm flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4" /> No anomalies detected in this record.
              </div>
            )}

            {selectedRecord?.legacyAvailable !== undefined && (
              <div className="space-y-2">
                 <h3 className="text-sm font-bold tracking-tight uppercase text-muted-foreground border-b pb-1">Computed Availability</h3>
                 <div className="font-mono text-2xl font-bold">
                    {selectedRecord.legacyAvailable}
                 </div>
              </div>
            )}

            <div className="space-y-2">
              <h3 className="text-sm font-bold tracking-tight uppercase text-muted-foreground border-b pb-1">Raw Source Fields</h3>
              <div className="bg-muted p-4 rounded-sm border text-sm font-mono overflow-auto max-h-[300px]">
                <table className="w-full">
                  <tbody>
                    {selectedRecord?.values && Object.entries(selectedRecord.values).map(([key, value]) => (
                      <tr key={key} className="border-b border-border/50 last:border-0 hover:bg-black/5">
                        <td className="py-2 pr-4 text-muted-foreground font-semibold align-top whitespace-nowrap w-1/3">{key}</td>
                        <td className="py-2 break-all align-top">{value || <span className="text-muted-foreground/50">null</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
