import { useId, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Role } from '@/contexts/PersonaContext';
import { Intervention, InterventionIssue, useInterventionAction } from '@/hooks/use-personas';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

export function ManualInventoryClose({
  item,
  role,
  onSuccess,
}: {
  item: Intervention | InterventionIssue;
  role: Role;
  onSuccess?: () => void;
}) {
  const [comment, setComment] = useState('');
  const commentId = useId();
  const mutation = useInterventionAction(role, item.id);
  const closure = item.evidence?.manual_closure;

  if (item.status === 'resolved') {
    return (
      <div className="space-y-3 rounded-lg border border-green-600/30 bg-green-600/5 p-4" role="status">
        <div className="flex items-center gap-2 font-semibold text-green-700">
          <CheckCircle2 className="h-5 w-5" /> Issue closed
        </div>
        {closure?.comment && <p className="whitespace-pre-wrap text-sm">{closure.comment}</p>}
        {Array.isArray(closure?.inventory_sync) && closure.inventory_sync.map((sync: {
          inventory_row_id: number;
          location: string;
          after: { wms_qty: number };
        }) => (
          <p key={sync.inventory_row_id} className="text-sm">
            {sync.location}: WMS, ERP and Vision quantities updated to {sync.after.wms_qty}.
          </p>
        ))}
        {closure?.at && (
          <p className="text-xs text-muted-foreground">Closed by Supervisor · {new Date(closure.at).toLocaleString()}</p>
        )}
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={(event) => {
      event.preventDefault();
      if (!comment.trim() || mutation.isPending || !item.allowed_actions.includes('manual_close')) return;
      mutation.mutate({ action: 'manual_close', reason: comment.trim() }, { onSuccess: () => onSuccess?.() });
    }}>
      <p className="text-sm text-muted-foreground">
        Closing sets this inventory location’s WMS, ERP and Vision quantities in the app to
        the highest of their current values and records your comment. Reserved and picked
        quantities stay unchanged. External WMS and ERP systems are not updated.
      </p>
      {item.allowed_actions.includes('manual_close') ? (
        <>
          <div className="space-y-2">
            <label htmlFor={commentId} className="text-sm font-medium">Closing comment <span className="text-muted-foreground">(required)</span></label>
            <Textarea id={commentId} required maxLength={2000} value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Describe your verification and reason for closing the mismatch."
              className="min-h-28" disabled={mutation.isPending} />
          </div>
          {mutation.isError && <p role="alert" className="text-sm text-destructive">{mutation.error.message}</p>}
          <Button type="submit" disabled={!comment.trim() || mutation.isPending}>
            {mutation.isPending ? 'Closing…' : 'Mark as closed'}
          </Button>
        </>
      ) : <p className="text-sm text-muted-foreground">Only an authorized supervisor can close this issue.</p>}
    </form>
  );
}