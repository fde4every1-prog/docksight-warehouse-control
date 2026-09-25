import { useId, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { Role } from '@/contexts/PersonaContext';
import { Intervention, InterventionIssue, useInterventionAction } from '@/hooks/use-personas';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

export function ManualLowStockClose({
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
      <div className="space-y-3 rounded-lg border border-green-600/30 bg-green-600/5 p-4" role="status" data-testid={`status-low-stock-closed-${item.id}`}>
        <div className="flex items-center gap-2 font-semibold text-green-700">
          <CheckCircle2 className="h-5 w-5" /> Alert closed
        </div>
        {closure?.comment && <p className="whitespace-pre-wrap text-sm" data-testid={`text-low-stock-comment-${item.id}`}>{closure.comment}</p>}
        {closure?.at && (
          <p className="text-xs text-muted-foreground">
            Closed by {closure.closed_by === 'supervisor' ? 'Supervisor' : closure.closed_by} · {new Date(closure.at).toLocaleString()}
          </p>
        )}
      </div>
    );
  }

  const canClose = role === 'supervisor' && item.allowed_actions.includes('manual_close');

  return (
    <form className="space-y-4" onSubmit={(event) => {
      event.preventDefault();
      if (!comment.trim() || mutation.isPending || !canClose) return;
      mutation.mutate(
        {
          action: 'manual_close',
          reason: comment.trim(),
          evidence: { condition_fingerprint: item.evidence?.condition_fingerprint },
        },
        { onSuccess: () => onSuccess?.() },
      );
    }}>
      <p className="text-sm text-muted-foreground">
        Closing records that this modeled low-stock alert was reviewed. It does not change
        inventory quantities, reservations, picked units, thresholds, or fulfillment work.
      </p>
      {canClose ? (
        <>
          <div className="space-y-2">
            <label htmlFor={commentId} className="text-sm font-medium">
              Closing comment <span className="text-muted-foreground">(required)</span>
            </label>
            <Textarea
              id={commentId}
              data-testid={`input-low-stock-comment-${item.id}`}
              required
              maxLength={2000}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="Describe the alert review and reason for closing it."
              className="min-h-28"
              disabled={mutation.isPending}
            />
          </div>
          {mutation.isError && (
            <p role="alert" data-testid={`error-low-stock-close-${item.id}`} className="text-sm text-destructive">
              {mutation.error.message}
            </p>
          )}
          <Button
            type="submit"
            data-testid={`button-low-stock-close-${item.id}`}
            disabled={!comment.trim() || mutation.isPending}
          >
            {mutation.isPending ? 'Closing…' : 'Close alert'}
          </Button>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Only an authorized supervisor can close this alert.</p>
      )}
    </form>
  );
}