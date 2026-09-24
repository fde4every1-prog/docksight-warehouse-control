import React, { useState, useEffect } from 'react';
import { useCatalog, useResources, useUpdateResourceRow, useResetResourceRow, useResetScenario } from '@/hooks/use-fulfillment';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { Database, Filter, Layers, DatabaseZap, Edit2, RotateCcw, AlertCircle, Save, Lock, Info } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { usePersona } from '@/contexts/PersonaContext';

// Add a helper component for rendering JSON cells
function JsonCell({ value }: { value: any }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground/30">-</span>;
  if (typeof value === 'object') {
    return <span className="text-muted-foreground/70">{JSON.stringify(value)}</span>;
  }
  return <span>{String(value)}</span>;
}

export default function FulfillmentResources() {
  const { role } = usePersona();
  const { data: catalog, isLoading: isCatalogLoading } = useCatalog();
  const [selectedDataset, setSelectedDataset] = useState<string>('');
  const [warehouseFilter, setWarehouseFilter] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // Editor State
  const [editingRow, setEditingRow] = useState<any>(null);
  const [draftValues, setDraftValues] = useState<Record<string, any>>({});
  const [editorRevision, setEditorRevision] = useState<number>(0);
  const [errorMsg, setErrorMsg] = useState<string>('');

  const allDatasets = catalog?.datasets || [];
  
  // Filter datasets based on persona
  const datasets = allDatasets.filter(ds => {
    if (role === 'admin') return true;
    if (role === 'fleet') return ['warehouses', 'robots', 'robot_aliases', 'vendors', 'control_assets', 'maintenance', 'charging_state', 'telemetry', 'safety_events', 'zones'].includes(ds.name);
    if (role === 'supervisor') return ['warehouses', 'inventory', 'orders', 'tasks', 'skus', 'shipments', 'priorities', 'labor_capacity', 'vision_observations'].includes(ds.name);
    return false;
  });

  // Safely default selectedDataset
  useEffect(() => {
    if (datasets.length > 0 && (!selectedDataset || !datasets.find(d => d.name === selectedDataset))) {
      setSelectedDataset(datasets[0].name);
    }
  }, [datasets, selectedDataset]);

  const { data: resourceData, isLoading: isResourceLoading } = useResources(
    selectedDataset, 
    warehouseFilter !== 'all' ? warehouseFilter : undefined
  );

  const updateRow = useUpdateResourceRow(selectedDataset);
  const resetRow = useResetResourceRow(selectedDataset);
  const resetScenario = useResetScenario();

  // Reset page when dataset or search changes
  useEffect(() => { setPage(1); }, [selectedDataset, search, warehouseFilter]);

  const handleEditClick = (row: any) => {
    const editorRow = { ...row };
    if (selectedDataset === 'inventory') {
      for (const field of ['wms_qty', 'erp_qty', 'vision_qty']) {
        if (row[`effective_${field}`] !== undefined) {
          editorRow[field] = row[`effective_${field}`];
        }
      }
    }
    setEditingRow(editorRow);
    // Initialize draft with editable fields only
    const draft: Record<string, any> = {};
    const editableFields = resourceData?.editable_fields || [];
    editableFields.forEach(f => {
      draft[f] = editorRow[f] !== undefined ? editorRow[f] : null;
    });
    setDraftValues(draft);
    setEditorRevision(resourceData?.revision || 0);
    setErrorMsg('');
  };

  const handleSave = () => {
    if (!editingRow) return;
    
    // Convert drafts based on field types
    const parsedValues: Record<string, any> = {};
    let hasError = false;
    
    const fieldTypes = resourceData?.field_types || {};
    const editableFields = resourceData?.editable_fields || [];
    
    for (const field of editableFields) {
      if (draftValues[field] === undefined) continue;
      
      const type = fieldTypes[field] || 'string';
      const raw = draftValues[field];
      const orig = editingRow[field];
      
      if (raw === orig) continue;
      
      let parsed = raw;
      if (raw !== null && raw !== '') {
        try {
          if (type === 'number') {
            parsed = Number(raw);
            if (!Number.isFinite(parsed)) throw new Error(`Invalid number for ${field}`);
          } else if (type === 'json') {
            if (typeof raw === 'string') {
              parsed = JSON.parse(raw);
            }
          } else if (type === 'boolean') {
            parsed = ['true', 'yes', 'y', '1'].includes(String(raw).toLowerCase());
          }
        } catch (e: any) {
          setErrorMsg(e.message || `Invalid format for ${field}`);
          hasError = true;
          break;
        }
      } else if (raw === '') {
        // Only convert to null if the original was also null, otherwise keep as empty string for string types
        // For numbers, empty string usually means null
        if (type === 'number' || type === 'json' || orig === null) {
          parsed = null;
        } else {
          parsed = '';
        }
      }
      
      let isChanged = false;
      if (type === 'json') {
        isChanged = JSON.stringify(parsed) !== JSON.stringify(orig);
      } else if (type === 'number') {
        if (orig === '' || orig === undefined) isChanged = parsed !== orig;
        else if (parsed === null && orig !== null) isChanged = true;
        else if (parsed !== null && orig === null) isChanged = true;
        else if (Number(parsed) !== Number(orig)) isChanged = true;
      } else if (type === 'boolean') {
        const origBool = orig === true || ['true', 'yes', 'y', '1'].includes(String(orig).toLowerCase());
        isChanged = parsed !== origBool;
      } else {
        isChanged = parsed !== orig;
      }
      
      if (isChanged) {
        parsedValues[field] = parsed;
      }
    }
    
    if (hasError) return;
    
    if (Object.keys(parsedValues).length === 0) {
      setEditingRow(null); // No changes
      return;
    }
    
    updateRow.mutate({ 
      id: editingRow._scenario_row_id, 
      values: parsedValues, 
      revision: editorRevision 
    }, {
      onSuccess: () => {
        setEditingRow(null);
      },
      onError: (err: any) => {
        setErrorMsg(err.message || 'Failed to update row');
      }
    });
  };

  const handleResetRow = () => {
    if (!editingRow) return;
    if (!window.confirm('Reset this row to its original dataset values?')) return;
    resetRow.mutate({ 
      id: editingRow._scenario_row_id, 
      revision: editorRevision 
    }, {
      onSuccess: () => {
        setEditingRow(null);
      },
      onError: (err: any) => {
        setErrorMsg(err.message || 'Failed to reset row');
      }
    });
  };

  const handleResetAll = () => {
    if (!window.confirm('Reset ALL scenario overrides? Note: Simulated order history and consumption will remain, but data values will revert to original.')) return;
    resetScenario.mutate({ revision: catalog?.scenario_revision ?? catalog?.revision ?? resourceData?.revision ?? 0 }, {
      onError: (err: any) => {
        alert(err.message || 'Failed to reset scenario');
      }
    });
  };

  if (isCatalogLoading) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="resources" />
        <Skeleton className="h-[600px] w-full" />
      </div>
    );
  }

  const warehouses = catalog?.warehouses || [];
  const currentDatasetInfo = datasets.find(d => d.name === selectedDataset);
  
  let rows = resourceData?.rows || [];
  if (search) {
    const q = search.toLowerCase();
    rows = rows.filter(row => Object.values(row).some(v => 
      (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)).toLowerCase().includes(q)
    ));
  }

  const rawBaseFields = resourceData?.fields || currentDatasetInfo?.fields || [];
  const baseFields = rawBaseFields.filter(f => !f.startsWith('_scenario_'));
  const editableFields = resourceData?.editable_fields || [];
  // Exclude _scenario_* from the extra computed fields if they exist
  const extraFields = rows.length > 0 
    ? Array.from(new Set(rows.flatMap(r => Object.keys(r)))).filter(f => !baseFields.includes(f) && !f.startsWith('_scenario_'))
    : [];
  
  const fields = Array.from(new Set([...baseFields, ...extraFields]));

  const rowsPerPage = 100;
  const totalPages = Math.ceil(rows.length / rowsPerPage);
  const paginatedRows = rows.slice((page - 1) * rowsPerPage, page * rowsPerPage);

  const scenarioModifiedCount = resourceData?.scenario_modified_count || catalog?.scenario_modified_count || 0;

  return (
    <div className="p-6 space-y-6 min-h-[100dvh] flex flex-col">
      <FulfillmentNav active="resources" />
      
      <div className="flex flex-col md:flex-row gap-4 justify-between items-start md:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <DatabaseZap className="h-6 w-6 text-primary" />
            Resource Explorer
          </h1>
          <p className="text-muted-foreground text-sm">Inspect complete base dataset contents for the POC.</p>
        </div>
        {role === 'admin' && scenarioModifiedCount > 0 && (
          <Button variant="destructive" onClick={handleResetAll} className="gap-2">
            <RotateCcw className="h-4 w-4" />
            Reset All Scenarios ({scenarioModifiedCount})
          </Button>
        )}
      </div>

      <div className="grid md:grid-cols-4 gap-6 flex-1">
        <div className="md:col-span-1 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Database className="h-4 w-4" /> Datasets
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y border-t">
                {datasets.map(ds => (
                  <button
                    key={ds.name}
                    onClick={() => { setSelectedDataset(ds.name); setSearch(''); }}
                    className={`w-full text-left p-3 hover:bg-muted/50 transition-colors flex items-center justify-between group ${selectedDataset === ds.name ? 'bg-primary/5 border-l-2 border-primary' : 'border-l-2 border-transparent'}`}
                  >
                    <div className="flex flex-col">
                      <span className={`text-sm font-medium ${selectedDataset === ds.name ? 'text-primary font-bold' : ''}`}>{ds.name}</span>
                      <span className="text-xs text-muted-foreground font-mono">{ds.count.toLocaleString()} rows</span>
                    </div>
                    <Layers className={`h-4 w-4 ${selectedDataset === ds.name ? 'text-primary' : 'text-muted-foreground opacity-0 group-hover:opacity-100'}`} />
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="md:col-span-3 flex flex-col h-full">
          <Card className="flex-1 flex flex-col overflow-hidden">
            <CardHeader className="pb-4 border-b shrink-0 bg-muted/20">
              <div className="flex flex-col gap-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <CardTitle className="font-mono">{selectedDataset}</CardTitle>
                    <CardDescription>
                      {rows.length} records {search && '(filtered)'}
                    </CardDescription>
                  </div>
                  
                  <div className="flex items-center gap-3 w-full sm:w-auto">
                    <div className="relative flex-1 sm:w-64">
                      <Filter className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                      <Input 
                        placeholder="Filter records..." 
                        className="pl-9 h-9 text-sm font-mono"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </div>
                    
                    {fields.includes('warehouse_id') && (
                      <select 
                        onChange={(e: any) => setWarehouseFilter(e.target.value)} 
                        value={warehouseFilter}
                        className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      >
                        <option value="all">All Warehouses</option>
                        {warehouses.map(w => (
                          <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_id}</option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>
                {resourceData?.planning_impact && (
                  <div className="text-xs text-muted-foreground bg-card p-3 rounded-md border flex items-start gap-2 mt-1">
                    <Info className="h-4 w-4 shrink-0 text-primary" />
                    <p className="leading-relaxed"><strong className="text-foreground font-medium">Planning Impact:</strong> {resourceData.planning_impact}</p>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent className="p-0 flex-1 overflow-auto bg-card min-h-[400px]">
              {isResourceLoading ? (
                <div className="p-8 space-y-4">
                  {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} className="h-12 w-full" />)}
                </div>
              ) : rows.length === 0 ? (
                <div className="p-12 text-center text-muted-foreground">
                  No records found matching filters.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <div className="flex justify-between items-center p-2 bg-muted/10 border-b text-xs text-muted-foreground font-mono">
                    <div>
                      Source Fields: {baseFields.length} | Computed Fields: {extraFields.length}
                    </div>
                  </div>
                  <Table>
                    <TableHeader className="bg-muted/40 sticky top-0 z-10 backdrop-blur-sm">
                      <TableRow>
                        <TableHead className="w-10"></TableHead>
                        {fields.map(field => {
                          const isSource = baseFields.includes(field);
                          return (
                            <TableHead key={field} className="font-mono text-xs whitespace-nowrap">
                              <span className={isSource ? 'font-semibold text-foreground' : 'italic text-muted-foreground'}>
                                {field}
                              </span>
                              {!isSource && <span className="ml-1 text-[10px] text-muted-foreground/50">(computed)</span>}
                            </TableHead>
                          );
                        })}
                        <TableHead className="sticky right-0 bg-muted/40 backdrop-blur-sm w-20 text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedRows.map((row, i) => {
                        const isModified = row._scenario_modified;
                        return (
                          <TableRow key={i} className={`hover:bg-muted/30 ${isModified ? 'bg-amber-500/5' : ''}`}>
                            <TableCell className="w-10">
                              {isModified && (
                                <div title="Scenario override active" className="w-2 h-2 rounded-full bg-amber-500 mx-auto" />
                              )}
                            </TableCell>
                            {fields.map(field => (
                              <TableCell key={field} className="font-mono text-xs whitespace-nowrap py-2 max-w-[200px] truncate">
                                <JsonCell value={row[field]} />
                              </TableCell>
                            ))}
                            <TableCell className="sticky right-0 bg-card/80 backdrop-blur-sm py-2 text-right">
                              <Button 
                                variant="ghost" 
                                size="sm" 
                                className="h-7 px-2"
                                onClick={() => handleEditClick(row)}
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between p-4 bg-muted/10 border-t">
                      <div className="text-xs text-muted-foreground font-mono">
                        Showing {(page - 1) * rowsPerPage + 1} to {Math.min(page * rowsPerPage, rows.length)} of {rows.length} rows
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                          Previous
                        </Button>
                        <span className="text-xs font-mono">Page {page} of {totalPages}</span>
                        <Button variant="outline" size="sm" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Editor Sheet */}
      <Sheet open={!!editingRow} onOpenChange={(open) => !open && setEditingRow(null)}>
        <SheetContent className="sm:max-w-[500px] w-[90vw] overflow-y-auto flex flex-col gap-0 p-0 border-l">
          <SheetHeader className="p-6 border-b shrink-0 bg-muted/20">
            <div className="flex items-center justify-between">
              <div>
                <SheetTitle className="text-xl">Edit Resource Row</SheetTitle>
                <SheetDescription className="font-mono text-xs mt-1">
                  ID: {editingRow?._scenario_row_id} • Dataset: {selectedDataset}
                </SheetDescription>
              </div>
              {editingRow?._scenario_modified && (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/20">
                  Scenario Override
                </Badge>
              )}
            </div>
            {selectedDataset === 'inventory' && (
              <Alert className="mt-4">
                <AlertTitle>Free-stock adjustments</AlertTitle>
                <AlertDescription className="text-xs">
                  WMS, ERP and vision edits here are unallocated stock, initialized from the live effective quantities.
                  Source table columns remain imported observations; effective_* columns show current balances.
                  Reservations and picked units are ledger-controlled. Use Supervisor corrections for observed total-on-hand counts.
                </AlertDescription>
              </Alert>
            )}
            {errorMsg && (
              <Alert variant="destructive" className="mt-4">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Error</AlertTitle>
                <AlertDescription className="text-xs break-words">
                  {errorMsg}
                </AlertDescription>
              </Alert>
            )}
          </SheetHeader>

          <div className="p-6 flex-1 overflow-y-auto">
            {editingRow && (
              <div className="space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold">Editable Fields</h3>
                  </div>
                  {editableFields.length === 0 ? (
                    <p className="text-xs text-muted-foreground italic">No editable fields available.</p>
                  ) : (
                    editableFields.map(field => {
                      const type = resourceData?.field_types?.[field] || 'string';
                      const isBoolean = type === 'boolean';
                      return (
                        <div key={field} className="space-y-2">
                          <Label className="font-mono text-xs text-muted-foreground flex justify-between">
                            <span>{field} <span className="opacity-50 text-[10px]">({type})</span></span>
                          </Label>
                          {isBoolean ? (
                            <div className="flex items-center space-x-2 h-9">
                              <Switch 
                                checked={draftValues[field] === true || ['true', 'yes', 'y', '1'].includes(String(draftValues[field]).toLowerCase())} 
                                onCheckedChange={(c) => setDraftValues(prev => ({...prev, [field]: c}))}
                              />
                            </div>
                          ) : type === 'json' || type === 'string' && typeof draftValues[field] === 'object' && draftValues[field] !== null ? (
                            <Textarea 
                              className="font-mono text-xs min-h-[100px]"
                              value={
                                typeof draftValues[field] === 'string' 
                                  ? draftValues[field] 
                                  : draftValues[field] === null || draftValues[field] === undefined
                                    ? ''
                                    : JSON.stringify(draftValues[field], null, 2)
                              }
                              onChange={(e) => setDraftValues(prev => ({...prev, [field]: e.target.value}))}
                              placeholder="null"
                            />
                          ) : (
                            <Input 
                              type={type === 'number' ? 'number' : 'text'}
                              className="font-mono text-xs"
                              value={draftValues[field] === null || draftValues[field] === undefined ? '' : draftValues[field]}
                              onChange={(e) => setDraftValues(prev => ({...prev, [field]: e.target.value}))}
                              placeholder="null"
                            />
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                <div className="space-y-4 pt-4 border-t">
                  <div className="flex items-center gap-2">
                    <Lock className="h-4 w-4 text-muted-foreground" />
                    <h3 className="text-sm font-semibold text-muted-foreground">Locked Fields</h3>
                  </div>
                  <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Identity references and computed fields (e.g., poc_*) are generated by the server and cannot be modified directly.
                  </p>
                  
                  <div className="grid gap-3">
                    {fields.filter(f => !editableFields.includes(f) && !f.startsWith('_scenario_')).map(field => (
                      <div key={field} className="grid grid-cols-[120px_1fr] gap-2 items-start opacity-75">
                        <Label className="font-mono text-[10px] text-muted-foreground break-all pt-1">
                          {field}
                        </Label>
                        <div className="bg-muted/30 rounded px-2 py-1 font-mono text-[10px] min-h-6 break-words whitespace-pre-wrap">
                          <JsonCell value={editingRow[field]} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <SheetFooter className="p-4 border-t shrink-0 bg-muted/10 flex-row justify-between sm:justify-between items-center gap-4">
            <div>
              {editingRow?._scenario_modified && (
                <Button variant="outline" size="sm" onClick={handleResetRow} className="text-destructive hover:bg-destructive/10 hover:text-destructive gap-2 h-9">
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reset Row
                </Button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setEditingRow(null)} className="h-9">
                Cancel
              </Button>
              <Button onClick={handleSave} size="sm" className="gap-2 h-9" disabled={updateRow.isPending}>
                <Save className="h-3.5 w-3.5" />
                {updateRow.isPending ? 'Saving...' : 'Save Draft'}
              </Button>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}