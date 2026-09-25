import React, { useState } from 'react';
import { usePersona } from '@/contexts/PersonaContext';
import { usePolicyMatrix, useAddResource } from '@/hooks/use-personas';
import { Settings, ShieldAlert, Plus, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { useCatalog } from '@/hooks/use-fulfillment';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Select } from '@/components/ui/select';
import { WorkspaceQueryError } from '../WorkspaceQueryError';

export default function AdminWorkspace() {
  const { role } = usePersona();
  const { data: policyData, isLoading: policyLoading, error: policyError, refetch: retryPolicy } = usePolicyMatrix(role);

  if (policyError) return <WorkspaceQueryError error={policyError} retry={() => { void retryPolicy(); }} />;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="h-6 w-6 text-primary" />
            Admin Workspace
          </h1>
          <p className="text-muted-foreground mt-1">Manage policies and register resources.</p>
        </div>
        <AddResourceDialog />
      </div>

      <div className="grid grid-cols-1 gap-6">
        <div className="space-y-4">
          <h2 className="text-lg font-bold border-b pb-2 flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-muted-foreground" />
            Persona Capabilities Policy
          </h2>
          
          {policyLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className="space-y-4">
              {policyData?.roles.map(r => (
                <div key={r.id} className="bg-card border rounded-lg p-4 shadow-sm">
                  <div className="flex justify-between items-center mb-4 border-b pb-2">
                    <h3 className="font-bold text-lg capitalize">{r.label}</h3>
                    <Badge variant="outline" className="font-mono">{r.id}</Badge>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">Allowed Actions</div>
                      <div className="flex flex-wrap gap-2">
                        {r.actions.map((action: string) => (
                          <Badge key={action} variant="secondary" className="bg-primary/10 text-primary hover:bg-primary/20">
                            {action}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    
                    <div>
                      <div className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2">Allowed Views</div>
                      <div className="flex flex-wrap gap-2">
                        {r.views.map((view: string) => (
                          <Badge key={view} variant="outline" className="text-muted-foreground">
                            {view}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

const REGISTERABLE_DATASETS = [
  { id: 'warehouses', label: 'Warehouse', fields: ['warehouse_id', 'region', 'manager_email'] },
  { id: 'skus', label: 'SKU', fields: ['sku', 'description', 'unit_weight_kg', 'category'] },
  { id: 'robots', label: 'Robot', fields: ['robot_id', 'warehouse_id', 'model', 'battery_capacity', 'status'] },
  { id: 'control_assets', label: 'Control Asset', fields: ['asset_id', 'warehouse_id', 'type', 'status'] }
];

function AddResourceDialog() {
  const { role } = usePersona();
  const { data: catalog } = useCatalog();
  const [open, setOpen] = useState(false);
  const [dataset, setDataset] = useState('warehouses');
  const [formData, setFormData] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const addResource = useAddResource(role, dataset);

  const currentDataset = REGISTERABLE_DATASETS.find(d => d.id === dataset);

  const handleDatasetChange = (v: string) => {
    setDataset(v);
    setFormData({});
    setError(null);
    setSuccess(null);
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Filter out empty strings before sending
    const cleanData = Object.fromEntries(
      Object.entries(formData).filter(([_, v]) => v.trim() !== '')
    );

    addResource.mutate(cleanData, {
      onSuccess: (res) => {
        setSuccess(`Successfully registered ${res.row_id}`);
        setFormData({});
      },
      onError: (err: any) => {
        setError(err.message || "Failed to register resource");
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => {
      setOpen(o);
      if (!o) {
        setFormData({});
        setError(null);
        setSuccess(null);
      }
    }}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          Register Resource
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register New Resource</DialogTitle>
          <p className="text-sm text-muted-foreground">Add new physical assets or configuration to the environment.</p>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-4">
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase text-muted-foreground">Resource Type</label>
            <Select 
              value={dataset} 
              onChange={(e: any) => handleDatasetChange(e.target.value)} 
              disabled={addResource.isPending}
            >
              {REGISTERABLE_DATASETS.map(d => (
                <option key={d.id} value={d.id}>{d.label}</option>
              ))}
            </Select>
          </div>

          <div className="space-y-4 border rounded-lg p-4 bg-muted/10">
            {currentDataset?.fields.map(field => {
              const isWarehouseLinked = ['robots', 'control_assets'].includes(dataset) && field === 'warehouse_id';
              
              if (isWarehouseLinked) {
                return (
                  <div key={field} className="space-y-1">
                     <label className="text-xs font-bold uppercase text-muted-foreground">{field} <span className="text-destructive">*</span></label>
                     <Select 
                      value={formData[field] || ''} 
                      onChange={(e: any) => handleInputChange(field, e.target.value)}
                      required
                     >
                       <option value="">Select warehouse...</option>
                       {catalog?.warehouses?.map(w => (
                         <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_id}</option>
                       ))}
                     </Select>
                  </div>
                );
              }

              const isIdentity = ['warehouse_id', 'sku', 'robot_id', 'asset_id'].includes(field);

              return (
                <div key={field} className="space-y-1">
                  <label className="text-xs font-bold uppercase text-muted-foreground">
                    {field} {isIdentity && <span className="text-destructive">*</span>}
                  </label>
                  <Input 
                    value={formData[field] || ''}
                    onChange={(e) => handleInputChange(field, e.target.value)}
                    required={isIdentity}
                    placeholder={`Enter ${field}...`}
                  />
                </div>
              );
            })}
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="bg-success/10 text-success border-success/20">
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>{success}</AlertDescription>
            </Alert>
          )}

          <div className="flex justify-end pt-4">
            <Button type="submit" disabled={addResource.isPending}>
              {addResource.isPending ? 'Registering...' : 'Register Resource'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}