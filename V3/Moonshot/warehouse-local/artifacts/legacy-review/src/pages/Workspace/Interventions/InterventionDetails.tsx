import { usePersona } from '@/contexts/PersonaContext';
import { useIntervention } from '@/hooks/use-personas';
import { ArrowLeft, Activity, CheckCircle2, Clock } from 'lucide-react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { CorrectionWorkflow } from '@/components/personas/CorrectionWorkflow';

export default function InterventionDetails({ id }: { id: string }) {
  const { role } = usePersona();
  const { data: intervention, isLoading } = useIntervention(role, id);

  if (isLoading) {
    return <div className="p-6 max-w-4xl mx-auto space-y-4"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>;
  }

  if (!intervention) {
    return (
       <div className="p-6 max-w-4xl mx-auto text-center mt-20">
         <h2 className="text-xl font-bold">Intervention Not Found</h2>
         <p className="text-muted-foreground mt-2">The intervention may not exist or you don't have permission to view it.</p>
         <Link href={`/workspace/${role}`}>
           <Button className="mt-6">Return to Workspace</Button>
         </Link>
       </div>
    );
  }

  const isOwner = intervention.owner === role;
  
  const statusColors = {
    open: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    investigating: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    awaiting_approval: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
    resolved: 'bg-green-500/10 text-green-500 border-green-500/20',
  };

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center">
        <Link href={`/workspace/${role}`} className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4 mr-1" /> Back to Workspace
        </Link>
      </div>

      <div className="bg-card border rounded-lg p-6 shadow-sm">
        <div className="flex justify-between items-start mb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold">{intervention.title}</h1>
              <Badge variant="outline" className={cn("capitalize font-bold", statusColors[intervention.status])}>
                {intervention.status === 'resolved' && intervention.evidence?.manual_closure ? 'Closed' : intervention.status.replace('_', ' ')}
              </Badge>
              <Badge variant="secondary" className="font-mono text-xs capitalize">
                Owner: {intervention.owner}
              </Badge>
            </div>
            <p className="text-muted-foreground">{intervention.description}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4 border-y mb-6 font-mono text-sm">
          <div>
            <div className="text-xs text-muted-foreground font-bold uppercase tracking-widest mb-1">Intervention ID</div>
            <div>{intervention.id}</div>
          </div>
          <div>
             <div className="text-xs text-muted-foreground font-bold uppercase tracking-widest mb-1">Kind</div>
            <div>{intervention.kind.replace(/_/g, ' ')}</div>
          </div>
          <div>
             <div className="text-xs text-muted-foreground font-bold uppercase tracking-widest mb-1">Entity ID</div>
            <div>{intervention.entity_id}</div>
          </div>
          <div>
             <div className="text-xs text-muted-foreground font-bold uppercase tracking-widest mb-1">Warehouse</div>
            <div>{intervention.warehouse_id}</div>
          </div>
        </div>

        {/* Action Area */}
        <div className="bg-muted/30 border rounded-lg p-6 mb-8">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            Action Center
          </h2>
          
          {intervention.kind === 'inventory_mismatch' ? (
            <CorrectionWorkflow item={intervention} role={role} />
          ) : !isOwner ? (
             <div className="text-center p-6 border border-dashed rounded-md bg-background text-muted-foreground">
                This intervention is currently owned by the {intervention.owner.toUpperCase()} persona.
                You can view its details but cannot take action.
             </div>
          ) : intervention.status === 'resolved' ? (
             <div className="text-center p-6 border border-success/30 rounded-md bg-success/5 text-success">
                <CheckCircle2 className="h-8 w-8 mx-auto mb-2" />
                <div className="font-bold">Intervention Resolved</div>
                <div className="text-sm opacity-80 mt-1">No further action required.</div>
             </div>
           ) : <CorrectionWorkflow item={intervention} role={role} />}
        </div>

        {/* Proposed Action Display */}
        {intervention.proposed_action && (
           <div className="mb-8 border rounded-lg overflow-hidden">
              <div className="bg-muted px-4 py-2 font-bold text-sm flex items-center justify-between">
                <span>Proposed Action</span>
                {intervention.proposed_action.approved && (
                  <Badge variant="default" className="bg-green-600">Approved</Badge>
                )}
              </div>
              <div className="p-4 bg-card font-mono text-sm overflow-x-auto">
                 <pre>{JSON.stringify(intervention.proposed_action, null, 2)}</pre>
              </div>
           </div>
        )}

        {/* Event Timeline */}
        <div>
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Clock className="h-5 w-5 text-muted-foreground" />
            Intervention Timeline
          </h2>
          <div className="space-y-4">
             {intervention.events.map((event, i) => (
                <div key={i} className="flex gap-4">
                   <div className="flex flex-col items-center">
                     <div className="w-2 h-2 rounded-full bg-primary mt-1.5" />
                     {i < intervention.events.length - 1 && <div className="w-0.5 h-full bg-border my-1" />}
                   </div>
                   <div className="bg-muted/30 border rounded-lg p-4 flex-1 mb-2">
                     <div className="flex justify-between items-start mb-2">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="font-mono text-[10px]">{event.persona}</Badge>
                          <span className="font-bold text-sm uppercase tracking-wider">{event.action === 'manual_close' ? 'Marked as closed' : event.action}</span>
                        </div>
                        <span className="text-xs text-muted-foreground font-mono">{new Date(event.at).toLocaleString()}</span>
                     </div>
                     <p className="text-sm mb-2">{event.reason}</p>
                     
                     {event.details && Object.keys(event.details).length > 0 && (
                        <div className="bg-card border rounded p-2 text-xs font-mono overflow-x-auto mt-2">
                           <pre className="text-muted-foreground">{JSON.stringify(event.details, null, 2)}</pre>
                        </div>
                     )}
                   </div>
                </div>
             ))}
          </div>
        </div>

      </div>
    </div>
  );
}