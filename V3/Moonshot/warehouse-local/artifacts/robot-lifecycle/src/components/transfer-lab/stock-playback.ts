import type { TransferMap, TransferTimelineEvent } from '@/hooks/use-transfer-batching';

/** Selected workload only, not a mutation of the warehouse's live inventory. */
export function remainingZonePicks(
  map: TransferMap,
  timeline: TransferTimelineEvent[],
  zoneId: string,
  currentTime: number,
) {
  const picks = timeline.filter(event =>
    event.action === 'pick' &&
    map.nodes.some(node => node.id === event.node_id && node.zone_id === zoneId),
  );
  return {
    total: picks.length,
    remaining: picks.filter(event => event.end > currentTime).length,
  };
}