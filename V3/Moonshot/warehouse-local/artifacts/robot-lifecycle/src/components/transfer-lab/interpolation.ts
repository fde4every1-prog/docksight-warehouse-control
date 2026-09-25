export function getInterpolatedPosition(
  currentTime: number,
  robotEvents: any[],
  mapNodes: { id: string; x: number; y: number }[],
  robotStartNode: string,
  donorClaims: any[] = []
): { x: number; y: number; currentPath: { x: number; y: number }[] | null; isBusy: boolean; activeOrderIds: string[]; isDonorClaim: boolean } {
  let x = 0;
  let y = 0;
  let isBusy = false;
  let currentPath: { x: number; y: number }[] | null = null;
  let activeOrderIds: string[] = [];
  let isDonorClaim = false;

  // Events are half-open intervals. This matters when two actions meet at the
  // same timestamp: the new action must win rather than leaving the previous
  // action selected for one frame.
  const donorClaim = donorClaims.find((e: any) => currentTime >= e.start && currentTime < e.end);
  if (donorClaim) {
    const stationary = getInterpolatedPosition(
      Math.max(0, donorClaim.start - 0.000001),
      robotEvents,
      mapNodes,
      robotStartNode
    );
    return {
      ...stationary,
      currentPath: null,
      isBusy: true,
      activeOrderIds: donorClaim.order_ids || [],
      isDonorClaim: true,
    };
  }

  const currentEvent = robotEvents.find((e: any) => currentTime >= e.start && currentTime < e.end);

  if (currentEvent && currentEvent.path && currentEvent.path.length > 0) {
    isBusy = true;
    activeOrderIds = currentEvent.order_ids || [];

    // The map prepares these once for playback. Keep path resolution here as a
    // compatibility path for callers and focused tests.
    const pathNodes = (currentEvent.pathNodes || currentEvent.path
      .map((nid: string) => mapNodes.find((n) => n.id === nid))
      .filter(Boolean)) as { x: number; y: number }[];

    if (pathNodes.length > 0) {
      if (pathNodes.length === 1) {
        x = pathNodes[pathNodes.length - 1].x;
        y = pathNodes[pathNodes.length - 1].y;
      } else if (currentTime <= currentEvent.start) {
        x = pathNodes[0].x;
        y = pathNodes[0].y;
      } else {
        // The final fifth of a Pick is visibly stationary at the bin. Travel
        // remains illustrative within the existing service duration.
        const elapsed = (currentTime - currentEvent.start) / (currentEvent.end - currentEvent.start || 1);
        const progress = Math.min(1, elapsed / (currentEvent.action === 'pick' ? 0.8 : 1));
        const segmentLengths = currentEvent.segmentLengths || pathNodes.slice(1).map((point: { x: number; y: number }, index: number) =>
          Math.hypot(point.x - pathNodes[index].x, point.y - pathNodes[index].y)
        );
        const totalDistance = currentEvent.totalDistance ?? segmentLengths.reduce((sum: number, length: number) => sum + length, 0);
        const targetDistance = progress * totalDistance;
        let traversed = 0;
        let segmentIndex = 0;
        while (
          segmentIndex < segmentLengths.length - 1
          && traversed + segmentLengths[segmentIndex] < targetDistance
        ) {
          traversed += segmentLengths[segmentIndex];
          segmentIndex += 1;
        }
        const segmentLength = segmentLengths[segmentIndex] || 0;
        const segmentProgress = segmentLength > 0
          ? Math.min(1, (targetDistance - traversed) / segmentLength)
          : 1;
        const p1 = pathNodes[segmentIndex];
        const p2 = pathNodes[segmentIndex + 1] || p1;

        x = p1.x + (p2.x - p1.x) * segmentProgress;
        y = p1.y + (p2.y - p1.y) * segmentProgress;
      }
      currentPath = pathNodes;
    }
  } else {
    let lastEvent: any;
    for (const event of robotEvents) {
      if (event.end <= currentTime) lastEvent = event;
      else break;
    }
    if (lastEvent) {
      if (lastEvent.path && lastEvent.path.length > 0) {
        const p = lastEvent.pathNodes?.[lastEvent.pathNodes.length - 1]
          || mapNodes.find((n) => n.id === lastEvent.path[lastEvent.path.length - 1]);
        if (p) {
          x = p.x;
          y = p.y;
        }
      }
    } else {
      const startNode = mapNodes.find((n) => n.id === robotStartNode);
      if (startNode) {
        x = startNode.x;
        y = startNode.y;
      }
    }
  }

  return { x, y, currentPath, isBusy, activeOrderIds, isDonorClaim };
}
