import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Role } from '@/contexts/PersonaContext';
import {
  Intervention,
  InterventionActionPayload,
  InterventionIssue,
  useInterventionAction,
} from '@/hooks/use-personas';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { ManualInventoryClose } from './ManualInventoryClose';
import { ManualLowStockClose } from './ManualLowStockClose';

type WorkflowItem = Intervention | InterventionIssue;

const ROBOT_FIELDS = ['health_status', 'safety_cert_status', 'calibration_status', 'connectivity', 'battery_soc', 'payload_kg'];
const MAINTENANCE_FIELDS = ['cmms_status', 'fleet_availability'];
const ASSET_FIELDS = ['state', 'maintenance_state'];
const FIELD_VALUES: Record<string, string[]> = {
  health_status: ['HEALTHY', 'DEGRADED', 'FAILED', 'UNKNOWN'],
  safety_cert_status: ['VALID', 'EXPIRED', 'INVALID', 'UNKNOWN'],
  calibration_status: ['VALID', 'INVALID', 'EXPIRED', 'UNKNOWN'],
  connectivity: ['ONLINE', 'INTERMITTENT', 'OFFLINE', 'UNKNOWN'],
  cmms_status: ['OPEN', 'IN_PROGRESS', 'PLANNED', 'CLOSED', 'COMPLETE'],
  fleet_availability: ['AVAILABLE', 'UNAVAILABLE', 'OUT_OF_SERVICE', 'UNKNOWN'],
  state: ['AVAILABLE', 'UNAVAILABLE', 'OFFLINE', 'BLOCKED', 'UNKNOWN'],
  maintenance_state: ['CLEAR', 'DUE', 'BLOCKED', 'UNKNOWN'],
};

function evidence(notes: string, phase: string) {
  return {
    source: 'modeled_control_tower',
    method: 'simulation_review',
    phase,
    notes: notes.trim(),
    physical_verification: false,
  };
}

function revisionFor(item: WorkflowItem, entityType: string, entityId: string): number | '' {
  const state = item.current_state || {};
  const evidenceRevision = item.evidence?.revision;
  const editableRevision = Array.isArray(item.evidence?.editable_contexts)
    ? item.evidence.editable_contexts.find((context: any) => context.entity_type === entityType && context.entity_id === entityId)?.revision
    : undefined;
  const candidates = [
    editableRevision,
    state.revisions?.[entityType]?.[entityId],
    state.revisions?.[entityId],
    state.source_revisions?.[entityType]?.[entityId],
    state.source_revision,
    state.revision,
    evidenceRevision,
  ];
  const exact = candidates.find(value => Number.isInteger(value) && value >= 0);
  return typeof exact === 'number' ? exact : '';
}

function remainingBlockers(item: WorkflowItem): string[] {
  const state = (item.proposed_action?.after && typeof item.proposed_action.after === 'object')
    ? item.proposed_action.after
    : item.current_state || {};
  const raw = state.remaining_blockers ?? state.unsafe_reasons ?? item.evidence?.unsafe_reasons ?? state.blockers ?? [];
  const blockers = Array.isArray(raw) ? raw.map(String) : raw ? [String(raw)] : [];
  if (state.opening_discrepancy) blockers.push('Opening source discrepancy remains active');
  if (state.blocked_allocation) blockers.push('Allocation remains blocked');
  return [...new Set(blockers)];
}

type WorkflowProps = { item: WorkflowItem; role: Role; onSuccess?: () => void };

export function CorrectionWorkflow(props: WorkflowProps) {
  return props.item.kind === 'inventory_mismatch'
    ? <ManualInventoryClose {...props} />
    : props.item.kind === 'replenishment_alert'
      ? <ManualLowStockClose {...props} />
    : <StructuredCorrectionWorkflow {...props} />;
}

function StructuredCorrectionWorkflow({
  item,
  role,
  onSuccess,
}: {
  item: WorkflowItem;
  role: Role;
  onSuccess?: () => void;
}) {
  const mutation = useInterventionAction(role, item.id);
  const state = item.current_state || {};
  const inventory = item.kind === 'inventory_mismatch' || item.kind === 'replenishment_alert';
  const fleet = item.kind === 'fleet_readiness' || item.kind === 'control_asset_readiness';
  const defaultEntityType = item.kind === 'control_asset_readiness' ? 'control_asset' : 'robot';
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [source, setSource] = useState('wms');
  const [basis, setBasis] = useState<'free' | 'total'>('free');
  const [quantity, setQuantity] = useState<string>('');
  const [entityType, setEntityType] = useState(defaultEntityType);
  const [entityId, setEntityId] = useState(item.entity_id);
  const [field, setField] = useState(item.kind === 'control_asset_readiness' ? 'state' : 'health_status');
  const [fieldValue, setFieldValue] = useState('');
  const [revision, setRevision] = useState<number | ''>(() => revisionFor(item, defaultEntityType, item.entity_id));
  const [fleetMode, setFleetMode] = useState<'source' | 'hold'>('source');
  const [legacyValue, setLegacyValue] = useState('');
  const [assignedTo, setAssignedTo] = useState('');
  const [resume, setResume] = useState(false);
  const [verifiedBy, setVerifiedBy] = useState('');
  const [countMethod, setCountMethod] = useState('modeled_source_review');
  const [units, setUnits] = useState('units');
  const [observationSource, setObservationSource] = useState('effective_modeled_source');
  const approvedState = (item.proposed_action?.after && typeof item.proposed_action.after === 'object')
    ? item.proposed_action.after
    : state;
  const openingReview = Boolean(approvedState.blocked_allocation || approvedState.opening_discrepancy);
  const [observationBasis, setObservationBasis] = useState<'free' | 'total_on_hand'>(() => openingReview ? 'total_on_hand' : 'free');
  const protectedQuantity = Number(approvedState.reserved_qty ?? 0) + Number(approvedState.picked_qty ?? 0);
  const observationValue = (field: string, selectedBasis: 'free' | 'total_on_hand') =>
    approvedState[field] === null || approvedState[field] === undefined
      ? ''
      : String(Number(approvedState[field]) + (selectedBasis === 'total_on_hand' ? protectedQuantity : 0));
  const [observedWms, setObservedWms] = useState<string>(() => observationValue('wms_qty', openingReview ? 'total_on_hand' : 'free'));
  const [observedErp, setObservedErp] = useState<string>(() => observationValue('erp_qty', openingReview ? 'total_on_hand' : 'free'));
  const [observedVision, setObservedVision] = useState<string>(() => observationValue('vision_qty', openingReview ? 'total_on_hand' : 'free'));
  const [observedRevision, setObservedRevision] = useState<number | ''>(() => {
    const value = approvedState.revision;
    return Number.isInteger(value) && value >= 0 ? value : '';
  });
  const blockers = remainingBlockers(item);
  const canVerify = item.allowed_actions.includes('verify');
  const editableContexts = Array.isArray(item.evidence?.editable_contexts) ? item.evidence.editable_contexts : [];
  const contextTypes = [...new Set(editableContexts.map((context: any) => String(context.entity_type)))];
  const entityContexts = editableContexts.filter((context: any) => context.entity_type === entityType);

  const fields = entityType === 'robot' ? ROBOT_FIELDS : entityType === 'maintenance' ? MAINTENANCE_FIELDS : ASSET_FIELDS;
  const enumValues = FIELD_VALUES[field];
  const isNumeric = field === 'battery_soc' || field === 'payload_kg';
  const sourceQty = state[`${source}_qty`];

  useEffect(() => {
    if (sourceQty !== null && sourceQty !== undefined) setQuantity(String(sourceQty));
    else setQuantity('');
  }, [source, sourceQty]);

  useEffect(() => {
    const nextFields = entityType === 'robot' ? ROBOT_FIELDS : entityType === 'maintenance' ? MAINTENANCE_FIELDS : ASSET_FIELDS;
    setField(nextFields[0]);
    setFieldValue('');
    setRevision(revisionFor(item, entityType, entityId));
  }, [entityType, entityId]);

  useEffect(() => {
    if (!canVerify || !inventory) return;
    const nextBasis = approvedState.blocked_allocation || approvedState.opening_discrepancy ? 'total_on_hand' : 'free';
    setObservationBasis(nextBasis);
    const protectedUnits = Number(approvedState.reserved_qty ?? 0) + Number(approvedState.picked_qty ?? 0);
    const observed = (field: string) => approvedState[field] === null || approvedState[field] === undefined
      ? ''
      : String(Number(approvedState[field]) + (nextBasis === 'total_on_hand' ? protectedUnits : 0));
    setObservedWms(observed('wms_qty'));
    setObservedErp(observed('erp_qty'));
    setObservedVision(observed('vision_qty'));
    const value = approvedState.revision;
    setObservedRevision(Number.isInteger(value) && value >= 0 ? value : '');
  }, [
    approvedState.erp_qty,
    approvedState.revision,
    approvedState.blocked_allocation,
    approvedState.opening_discrepancy,
    approvedState.picked_qty,
    approvedState.reserved_qty,
    approvedState.vision_qty,
    approvedState.wms_qty,
    inventory,
    canVerify,
  ]);

  const error = mutation.error instanceof Error ? mutation.error.message : '';
  const canSubmitBase = reason.trim().length > 0;

  const submit = (payload: InterventionActionPayload) => {
    mutation.mutate(payload, {
      onSuccess: () => {
        setReason('');
        setNotes('');
        onSuccess?.();
      },
    });
  };

  const submitSimple = (action: 'investigate' | 'approve' | 'handoff') => {
    if (!canSubmitBase || !notes.trim()) return;
    submit({ action, reason: reason.trim(), evidence: evidence(notes, action) });
  };

  const proposalReady = useMemo(() => {
    if (!canSubmitBase || !notes.trim()) return false;
    if (inventory) return quantity !== '' && Number.isInteger(Number(quantity)) && Number(quantity) >= 0 && revision !== '' && Number.isInteger(revision) && !!verifiedBy.trim() && !!countMethod && !!units.trim();
    if (fleet && fleetMode === 'source') {
      const validValue = isNumeric
        ? Number.isFinite(Number(fieldValue)) && Number(fieldValue) >= 0 && (field !== 'battery_soc' || Number(fieldValue) <= 100) && (field !== 'payload_kg' || Number(fieldValue) > 0)
        : !!fieldValue.trim();
      return !!entityId.trim() && validValue && revision !== '' && Number.isInteger(revision) && !!verifiedBy.trim();
    }
    if (fleet && fleetMode === 'hold') return !!legacyValue;
    if (item.kind === 'priority_override' || item.kind === 'task_completion_conflict') return !!legacyValue.trim();
    return true;
  }, [canSubmitBase, countMethod, entityId, field, fieldValue, fleet, fleetMode, inventory, isNumeric, item.kind, legacyValue, notes, quantity, revision, units, verifiedBy]);

  const submitProposal = () => {
    if (!proposalReady) return;
    const payload: InterventionActionPayload = {
      action: 'propose',
      reason: reason.trim(),
      evidence: inventory
        ? {
            count_method: countMethod,
            verified_by: verifiedBy.trim(),
            units: units.trim(),
            notes: notes.trim(),
            physical_verification: false,
          }
        : fleet && fleetMode === 'source'
          ? {
              source: 'effective_modeled_source',
              verified_by: verifiedBy.trim(),
              notes: notes.trim(),
              physical_verification: false,
            }
          : evidence(notes, 'proposal'),
    };
    if (inventory) {
      payload.value = {
        source,
        quantity: Number(quantity),
        basis,
        revision,
        location: state.location ?? item.entity_id.split('@')[1] ?? '',
      };
    } else if (fleet) {
      payload.value = fleetMode === 'hold'
        ? legacyValue
        : {
            entity_type: entityType,
            entity_id: entityId.trim(),
            field,
            value: isNumeric ? Number(fieldValue) : fieldValue.trim(),
            revision,
          };
    } else if (item.kind === 'priority_override' || item.kind === 'task_completion_conflict') {
      payload.value = legacyValue.trim();
    } else if (item.kind === 'resource_failure' && assignedTo.trim()) {
      payload.assigned_to = assignedTo.trim();
    }
    submit(payload);
  };

  const submitVerify = () => {
    if (!canSubmitBase || !notes.trim()) return;
    let verification: Record<string, any> = evidence(notes, 'verification');
    if (inventory) {
      verification = {
        verified_by: verifiedBy.trim(),
        current_observations: {
          revision: observedRevision,
          basis: observationBasis,
          wms_qty: Number(observedWms),
          erp_qty: Number(observedErp),
          vision_qty: Number(observedVision),
          attestation: notes.trim(),
        },
      };
    } else if (fleet && item.proposed_action?.type === 'fleet_source_correction') {
      verification = {
        verified_by: verifiedBy.trim(),
        observed_entity_id: item.proposed_action.entity_id,
        observation_source: observationSource,
        notes: notes.trim(),
        physical_verification: false,
      };
    }
    if (item.kind === 'resource_failure') {
      Object.assign(verification, {
        resume,
        ...(assignedTo.trim() ? { assigned_to: assignedTo.trim() } : {}),
      });
    }
    submit({ action: 'verify', reason: reason.trim(), evidence: verification });
  };

  if (!item.allowed_actions.length) return null;

  return (
    <div className="space-y-4" data-testid={`workflow-${item.id}`}>
      {blockers.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3" data-testid={`status-blockers-${item.id}`}>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><AlertTriangle className="h-4 w-4" />Remaining modeled blockers</div>
          <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">{blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul>
        </div>
      )}

      {item.allowed_actions.includes('propose') && (
        <div className="space-y-4 rounded-md border bg-background p-4">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Propose correction</h3>
          {inventory && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1 text-xs font-bold uppercase">Source
                  <select data-testid={`select-source-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={source} onChange={event => setSource(event.target.value)}>
                    <option value="wms">WMS free quantity</option><option value="erp">ERP free quantity</option><option value="vision">Vision free quantity</option>
                  </select>
                </label>
                <label className="space-y-1 text-xs font-bold uppercase">Quantity basis
                  <select data-testid={`select-basis-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={basis} onChange={event => setBasis(event.target.value as 'free' | 'total')}>
                    <option value="free">Free stock</option><option value="total">Total on hand</option>
                  </select>
                </label>
              </div>
              <label className="block space-y-1 text-xs font-bold uppercase">{basis === 'free' ? `${source.toUpperCase()} free stock` : `${source.toUpperCase()} total on hand`}
                <Input data-testid={`input-quantity-${item.id}`} type="number" min={0} step={1} value={quantity} onChange={event => setQuantity(event.target.value)} />
              </label>
              <p className="text-xs text-muted-foreground">{basis === 'free' ? 'Free stock excludes reserved and picked units.' : `Total on hand includes units still onsite; the server protects reserved (${state.reserved_qty ?? 'unknown'}) and picked (${state.picked_qty ?? 'unknown'}) units exactly once.`}</p>
              <label className="block space-y-1 text-xs font-bold uppercase">Required source revision
                <Input data-testid={`input-revision-${item.id}`} type="number" min={0} step={1} value={revision} onChange={event => setRevision(event.target.value === '' ? '' : Number(event.target.value))} />
              </label>
              {revision === '' && <div className="text-xs"><Badge variant="destructive">Revision missing from current state</Badge><span className="ml-2 text-muted-foreground">Enter the exact current revision; no fallback is applied.</span></div>}
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="space-y-1 text-xs font-bold uppercase">Count method
                  <select data-testid={`select-count-method-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={countMethod} onChange={event => setCountMethod(event.target.value)}>
                    <option value="modeled_source_review">Modeled source review</option><option value="simulation_reconciliation">Simulation reconciliation</option>
                  </select>
                </label>
                <label className="space-y-1 text-xs font-bold uppercase">Reviewed by<Input data-testid={`input-proposal-verified-by-${item.id}`} value={verifiedBy} onChange={event => setVerifiedBy(event.target.value)} /></label>
                <label className="space-y-1 text-xs font-bold uppercase">Units<Input data-testid={`input-units-${item.id}`} value={units} onChange={event => setUnits(event.target.value)} /></label>
              </div>
            </>
          )}
          {fleet && (
            <>
              {item.kind === 'fleet_readiness' && (
                <label className="space-y-1 text-xs font-bold uppercase">Proposal type
                  <select data-testid={`select-fleet-mode-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={fleetMode} onChange={event => setFleetMode(event.target.value as 'source' | 'hold')}>
                    <option value="source">Modeled source correction</option><option value="hold">Durable safety hold/release</option>
                  </select>
                </label>
              )}
              {fleetMode === 'hold' ? (
                <label className="space-y-1 text-xs font-bold uppercase">Safety action
                  <select data-testid={`select-safety-action-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={legacyValue} onChange={event => setLegacyValue(event.target.value)}>
                    <option value="">Select action</option><option value="hold">Apply hold</option><option value="release">Release hold</option>
                  </select>
                </label>
              ) : (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs font-bold uppercase">Source entity type
                      <select data-testid={`select-entity-type-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={entityType} onChange={event => {
                        const nextType = event.target.value;
                        setEntityType(nextType);
                        const first = editableContexts.find((context: any) => context.entity_type === nextType);
                        if (first?.entity_id) setEntityId(String(first.entity_id));
                      }}>
                        {(contextTypes.length ? contextTypes : ['robot', 'maintenance', 'control_asset']).map(type => <option key={type} value={type}>{type === 'maintenance' ? 'Maintenance work order' : type === 'control_asset' ? 'Control asset' : 'Robot'}</option>)}
                      </select>
                    </label>
                    <label className="space-y-1 text-xs font-bold uppercase">Source entity ID
                      {entityContexts.length ? (
                        <select data-testid={`select-entity-id-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={entityId} onChange={event => setEntityId(event.target.value)}>
                          {entityContexts.map((context: any) => <option key={context.entity_id} value={context.entity_id}>{context.entity_id}{context.blocking ? ' — blocking' : ''}</option>)}
                        </select>
                      ) : <Input data-testid={`input-entity-id-${item.id}`} value={entityId} onChange={event => setEntityId(event.target.value)} />}
                    </label>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="space-y-1 text-xs font-bold uppercase">Field
                      <select data-testid={`select-field-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={field} onChange={event => { setField(event.target.value); setFieldValue(''); }}>
                        {fields.map(option => <option key={option} value={option}>{option}</option>)}
                      </select>
                    </label>
                    <label className="space-y-1 text-xs font-bold uppercase">Modeled source value
                      {enumValues ? (
                        <select data-testid={`select-field-value-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={fieldValue} onChange={event => setFieldValue(event.target.value)}>
                          <option value="">Select value</option>{enumValues.map(option => <option key={option} value={option}>{option}</option>)}
                        </select>
                      ) : <Input data-testid={`input-field-value-${item.id}`} type="number" min={0} max={field === 'battery_soc' ? 100 : undefined} step="any" value={fieldValue} onChange={event => setFieldValue(event.target.value)} />}
                    </label>
                  </div>
                  <label className="block space-y-1 text-xs font-bold uppercase">Required source revision
                    <Input data-testid={`input-revision-${item.id}`} type="number" min={0} step={1} value={revision} onChange={event => setRevision(event.target.value === '' ? '' : Number(event.target.value))} />
                  </label>
                  {revision === '' && <p className="text-xs text-destructive">The API did not provide a revision for this source entity. Enter the current non-negative source revision; no fallback revision will be invented.</p>}
                  <label className="block space-y-1 text-xs font-bold uppercase">Reviewed by
                    <Input data-testid={`input-proposal-verified-by-${item.id}`} value={verifiedBy} onChange={event => setVerifiedBy(event.target.value)} placeholder="Operator or reviewer name" />
                  </label>
                </>
              )}
            </>
          )}
          {item.kind === 'priority_override' && <label className="space-y-1 text-xs font-bold uppercase">Target priority<select data-testid={`select-priority-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={legacyValue} onChange={event => setLegacyValue(event.target.value)}><option value="">Select priority</option><option value="standard">Standard</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>}
          {item.kind === 'task_completion_conflict' && <label className="space-y-1 text-xs font-bold uppercase">Modeled outcome<Input data-testid={`input-outcome-${item.id}`} value={legacyValue} onChange={event => setLegacyValue(event.target.value)} placeholder="Simulation outcome; do not claim physical verification" /></label>}
          {item.kind === 'resource_failure' && <label className="space-y-1 text-xs font-bold uppercase">Replacement resource (optional)<Input data-testid={`input-assigned-${item.id}`} value={assignedTo} onChange={event => setAssignedTo(event.target.value)} /></label>}
          <EvidenceFields itemId={item.id} reason={reason} notes={notes} setReason={setReason} setNotes={setNotes} />
          <Button data-testid={`button-propose-${item.id}`} className="w-full" onClick={submitProposal} disabled={mutation.isPending || !proposalReady}>Submit proposal</Button>
        </div>
      )}

      {canVerify && (
        <div className="space-y-4 rounded-md border bg-background p-4">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Verify effective modeled state</h3>
          <p className="text-xs text-muted-foreground">This records simulation/model evidence only; it does not claim a physical inspection.</p>
          {inventory && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Review and record the effective modeled values returned after approval. All three observations and the exact revision are included in the audit evidence.</p>
              <div className="grid grid-cols-3 gap-2">
                <label className="space-y-1 text-xs font-bold uppercase">Current WMS
                  <Input data-testid={`input-verify-wms-${item.id}`} type="number" min={0} step={1} value={observedWms} onChange={event => setObservedWms(event.target.value)} />
                </label>
                <label className="space-y-1 text-xs font-bold uppercase">Current ERP
                  <Input data-testid={`input-verify-erp-${item.id}`} type="number" min={0} step={1} value={observedErp} onChange={event => setObservedErp(event.target.value)} />
                </label>
                <label className="space-y-1 text-xs font-bold uppercase">Current Vision
                  <Input data-testid={`input-verify-vision-${item.id}`} type="number" min={0} step={1} value={observedVision} onChange={event => setObservedVision(event.target.value)} />
                </label>
              </div>
              <label className="block space-y-1 text-xs font-bold uppercase">Observation basis
                <select data-testid={`select-verify-basis-${item.id}`} className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm" value={observationBasis} onChange={event => {
                  const next = event.target.value as 'free' | 'total_on_hand';
                  setObservationBasis(next);
                  setObservedWms(observationValue('wms_qty', next));
                  setObservedErp(observationValue('erp_qty', next));
                  setObservedVision(observationValue('vision_qty', next));
                }}>
                  <option value="free">Free stock</option><option value="total_on_hand">Total on hand</option>
                </select>
              </label>
              <label className="block space-y-1 text-xs font-bold uppercase">Current inventory revision
                <Input data-testid={`input-verify-revision-${item.id}`} type="number" min={0} step={1} value={observedRevision} onChange={event => setObservedRevision(event.target.value === '' ? '' : Number(event.target.value))} />
              </label>
              <label className="block space-y-1 text-xs font-bold uppercase">Verified by
                <Input data-testid={`input-verify-verified-by-${item.id}`} value={verifiedBy} onChange={event => setVerifiedBy(event.target.value)} />
              </label>
            </div>
          )}
          {fleet && item.proposed_action?.type === 'fleet_source_correction' && <>
            <label className="block space-y-1 text-xs font-bold uppercase">Verified by<Input data-testid={`input-verify-verified-by-${item.id}`} value={verifiedBy} onChange={event => setVerifiedBy(event.target.value)} /></label>
            <label className="block space-y-1 text-xs font-bold uppercase">Observation source<Input data-testid={`input-observation-source-${item.id}`} value={observationSource} onChange={event => setObservationSource(event.target.value)} /></label>
            <div className="text-xs font-mono">Observed entity: {item.proposed_action.entity_id}</div>
          </>}
          {item.kind === 'resource_failure' && <>
            <label className="flex items-center gap-2 text-sm"><input data-testid={`checkbox-resume-${item.id}`} type="checkbox" checked={resume} onChange={event => setResume(event.target.checked)} />Queue remaining simulated work after verification</label>
            {resume && <label className="space-y-1 text-xs font-bold uppercase">Replacement resource<Input data-testid={`input-verify-assigned-${item.id}`} value={assignedTo} onChange={event => setAssignedTo(event.target.value)} /></label>}
          </>}
          <EvidenceFields itemId={item.id} reason={reason} notes={notes} setReason={setReason} setNotes={setNotes} />
          <Button data-testid={`button-verify-${item.id}`} className="w-full bg-green-600 text-white hover:bg-green-700" onClick={submitVerify} disabled={mutation.isPending || !canSubmitBase || !notes.trim() || ((inventory || (fleet && item.proposed_action?.type === 'fleet_source_correction')) && !verifiedBy.trim()) || (inventory && ([observedWms, observedErp, observedVision].some(value => value === '' || !Number.isInteger(Number(value)) || Number(value) < 0) || observedRevision === '' || !Number.isInteger(observedRevision)))}>Verify and resolve</Button>
        </div>
      )}

      {(['investigate', 'approve', 'handoff'] as const).map(action => item.allowed_actions.includes(action) && (
        <div key={action} className="space-y-3 rounded-md border bg-background p-4">
          <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground">{action === 'investigate' ? 'Start investigation' : action === 'approve' ? 'Approve proposed change' : 'Handoff to supervisor'}</h3>
          {action === 'approve' && <p className="text-xs text-muted-foreground">Approval applies the proposal; verification remains a separate modeled-state check.</p>}
          <EvidenceFields itemId={`${item.id}-${action}`} reason={reason} notes={notes} setReason={setReason} setNotes={setNotes} />
          <Button data-testid={`button-${action}-${item.id}`} variant={action === 'approve' ? 'default' : 'outline'} onClick={() => submitSimple(action)} disabled={mutation.isPending || !canSubmitBase || !notes.trim()}>{action === 'investigate' ? 'Start investigation' : action === 'approve' ? 'Approve proposal' : 'Handoff to supervisor'}</Button>
        </div>
      ))}

      {error && <div role="alert" data-testid={`error-action-${item.id}`} className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
      {mutation.isSuccess && <div data-testid={`status-action-success-${item.id}`} className="flex items-center gap-2 text-sm text-green-600"><CheckCircle2 className="h-4 w-4" />Action recorded in intervention history.</div>}
    </div>
  );
}

function EvidenceFields({ itemId, reason, notes, setReason, setNotes }: {
  itemId: string;
  reason: string;
  notes: string;
  setReason: (value: string) => void;
  setNotes: (value: string) => void;
}) {
  return <>
    <label className="block space-y-1 text-xs font-bold uppercase">Reason (required)<Input data-testid={`input-reason-${itemId}`} value={reason} onChange={event => setReason(event.target.value)} placeholder="Why this workflow action is needed" /></label>
    <label className="block space-y-1 text-xs font-bold uppercase">Modeled / simulation evidence (required)<Textarea data-testid={`input-evidence-${itemId}`} value={notes} onChange={event => setNotes(event.target.value)} className="min-h-[80px] font-mono text-sm" placeholder="Describe the modeled source evidence reviewed. Do not claim a physical inspection." /></label>
  </>;
}