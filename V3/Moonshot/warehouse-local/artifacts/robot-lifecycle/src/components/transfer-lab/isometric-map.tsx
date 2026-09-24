import React, { useState, useMemo, useRef, useEffect } from 'react';
import { TransferMap, TransferRobot, TransferTimelineEvent } from '@/hooks/use-transfer-batching';
import { Bot, Maximize, Minimize, ZoomIn, ZoomOut, Focus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getInterpolatedPosition } from './interpolation';

interface IsometricMapProps {
  map: TransferMap;
  run?: any;
  robots: TransferRobot[];
  currentTime: number;
  title: string;
}

// Helper to convert 2D coordinates to Isometric
const toIso = (x: number, y: number) => {
  // Rotate by 45 degrees and scale y to create isometric perspective
  // Using a standard 2:1 isometric ratio
  const isoX = (x - y) * 0.866;
  const isoY = (x + y) * 0.5;
  return { x: isoX, y: isoY };
};

const completedBy = (sortedEndTimes: number[], currentTime: number) => {
  let low = 0;
  let high = sortedEndTimes.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (sortedEndTimes[middle] <= currentTime) low = middle + 1;
    else high = middle;
  }
  return low;
};

export function IsometricMap({ map, run, robots, currentTime, title }: IsometricMapProps) {
  const [selectedEntity, setSelectedEntity] = useState<{type: 'robot' | 'bin' | 'station', id: string} | null>(null);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  
  // Pan and Zoom state
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  };

  const handleZoomIn = () => setScale(s => Math.min(s * 1.2, 5));
  const handleZoomOut = () => setScale(s => Math.max(s / 1.2, 0.2));
  const handleFit = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const dx = (e.clientX - dragStart.x) * (minIsoX.width / (containerRef.current?.clientWidth || 1000)) / scale;
    const dy = (e.clientY - dragStart.y) * (minIsoX.height / (containerRef.current?.clientHeight || 800)) / scale;
    setPan(p => ({ x: p.x - dx, y: p.y - dy }));
    setDragStart({ x: e.clientX, y: e.clientY });
  };

  const handleMouseUp = () => setIsDragging(false);

  const parkingLeft = useMemo(() => {
    const corners = [
      { x: 0, y: 0 }, { x: map.width, y: 0 },
      { x: map.width, y: map.height }, { x: 0, y: map.height },
      ...map.zones.flatMap(z => [{ x: z.x, y: z.y }, { x: z.x + z.width, y: z.y + z.height }]),
    ];
    return Math.min(...corners.map(p => toIso(p.x, p.y).x)) - 375;
  }, [map]);

  const timeline: any[] = useMemo(() => run?.timeline || [], [run?.timeline]);

  // Prepare immutable playback data only when the run/map changes. The RAF
  // clock below now does O(robots) lookups rather than repeatedly filtering and
  // sorting the complete timeline or resolving every path node.
  const playbackData = useMemo(() => {
    const nodeById = new Map(map.nodes.map(node => [node.id, node]));
    const eventsByRobot = new Map<string, any[]>();
    const claimsByDonor = new Map<string, any[]>();
    const completedPicksByBatch = new Map<string, number[]>();

    timeline.forEach(event => {
      const robotId = event.robot_id || event.resource_id;
      if (robotId) {
        const events = eventsByRobot.get(robotId) || [];
        events.push(event);
        eventsByRobot.set(robotId, events);
      }
      if (event.donor_robot_id) {
        const claims = claimsByDonor.get(event.donor_robot_id) || [];
        claims.push(event);
        claimsByDonor.set(event.donor_robot_id, claims);
      }
      if (event.batch_id && event.action === 'pick') {
        const ends = completedPicksByBatch.get(event.batch_id) || [];
        ends.push(event.end);
        completedPicksByBatch.set(event.batch_id, ends);
      }
    });
    eventsByRobot.forEach(events => events.sort((a, b) => a.start - b.start));
    claimsByDonor.forEach(events => events.sort((a, b) => a.start - b.start));
    completedPicksByBatch.forEach(ends => ends.sort((a, b) => a - b));

    const preparedRobots = robots.map((robot, index) => {
      const robotEvents = eventsByRobot.get(robot.id) || [];
      const donorClaims = claimsByDonor.get(robot.id) || [];
      const parkingX = parkingLeft + (index % 3) * 108;
      const parkingY = 70 + Math.floor(index / 3) * 82;
      // Display-only origin: depart smoothly from the left parking bay.
      // Never change server routes, stock identities, or event durations.
      const parkingNode = {
        id: `parking:${robot.id}`,
        x: parkingY + parkingX / (2 * 0.866),
        y: parkingY - parkingX / (2 * 0.866),
      };
      const visualNodes = new Map<string, { id: string; x: number; y: number }>();
      visualNodes.set(parkingNode.id, parkingNode);
      const visualEvents = robotEvents.map((event, eventIndex) => {
        const path = eventIndex === 0 ? [parkingNode.id, ...(event.path || [])] : (event.path || []);
        const pathNodes = path.map((id: string) =>
          id === parkingNode.id ? parkingNode : nodeById.get(id)
        ).filter(Boolean);
        const segmentLengths = pathNodes.slice(1).map((point: any, pathIndex: number) =>
          Math.hypot(point.x - pathNodes[pathIndex].x, point.y - pathNodes[pathIndex].y)
        );
        return {
          ...event,
          path,
          pathNodes,
          segmentLengths,
          totalDistance: segmentLengths.reduce((sum: number, length: number) => sum + length, 0),
        };
      });
      return {
        robot,
        robotEvents,
        donorClaims,
        visualEvents,
        visualNodes: [...visualNodes.values()],
        parkingNodeId: parkingNode.id,
        firstStart: robotEvents[0]?.start,
      };
    });

    const zonePickEnds = new Map<string, number[]>();
    timeline.forEach(event => {
      if (event.action !== 'pick') return;
      const zoneId = nodeById.get(event.node_id)?.zone_id;
      if (!zoneId) return;
      const ends = zonePickEnds.get(zoneId) || [];
      ends.push(event.end);
      zonePickEnds.set(zoneId, ends);
    });
    zonePickEnds.forEach(ends => ends.sort((a, b) => a - b));

    return { preparedRobots, completedPicksByBatch, zonePickEnds };
  }, [map.nodes, parkingLeft, robots, timeline]);

  // Only interpolation and compact state labels depend on the RAF clock.
  const robotStates = useMemo(() => {
    return playbackData.preparedRobots.map(({ robot, robotEvents, donorClaims, visualEvents, visualNodes, parkingNodeId, firstStart }) => {
      const { x, y, isBusy, currentPath, activeOrderIds, isDonorClaim } = getInterpolatedPosition(
        currentTime,
        visualEvents,
        visualNodes,
        parkingNodeId,
        donorClaims
      );

      const isoPos = toIso(x, y);
      const activeEvent = visualEvents.find(event => currentTime >= event.start && currentTime < event.end);
      const donorEvent = donorClaims.find(event => currentTime >= event.start && currentTime < event.end);
      const activeBatch = activeEvent?.batch_id || donorEvent?.batch_id;
      const pickedStops = activeBatch
        ? completedBy(playbackData.completedPicksByBatch.get(activeBatch) || [], currentTime)
        : 0;
      const activityEvent = activeEvent || donorEvent;
      const activityProgress = activityEvent
        ? Math.max(0, Math.min(1, (currentTime - activityEvent.start) / (activityEvent.end - activityEvent.start || 1)))
        : null;
      const progressLabel = activityProgress === null ? '' : ` ${Math.round(activityProgress * 100)}%`;
      const activityLabel = donorEvent
        ? `Holding at pickup${progressLabel}`
        : activeEvent?.action === 'pick'
          ? `${activeEvent.totalDistance === 0 || (activityProgress !== null && activityProgress >= 0.8) ? 'Pick · at bin' : 'Picking'}${progressLabel}`
          : activeEvent?.action === 'transfer'
            ? `Transfer${progressLabel}`
            : firstStart !== undefined && firstStart <= currentTime ? 'Waiting' : 'Parked';

      return {
        id: robot.id,
        origX: x,
        origY: y,
        isoX: isoPos.x,
        isoY: isoPos.y,
        isBusy,
        available: robot.available,
        activeOrderIds,
        currentPath,
        isDonorClaim,
        hasStarted: firstStart !== undefined && firstStart <= currentTime,
        pickedStops,
        activityLabel,
        activityProgress,
      };
    });
  }, [currentTime, playbackData]);

  const zoneVisuals = useMemo(() => map.zones.map(zone => {
    const p1 = toIso(zone.x, zone.y);
    const p2 = toIso(zone.x + zone.width, zone.y);
    const p3 = toIso(zone.x + zone.width, zone.y + zone.height);
    const p4 = toIso(zone.x, zone.y + zone.height);
    return { zone, p1, p2, p3, p4 };
  }), [map.zones]);

  // viewBox calculation
  // Find min/max iso coordinates to center the map
  const minIsoX = useMemo(() => {
    let minX = 0, minY = 0, maxX = 0, maxY = 0;
    const allPoints = [
      {x: 0, y: 0},
      {x: map.width, y: 0},
      {x: map.width, y: map.height},
      {x: 0, y: map.height},
      ...map.zones.map(z => ({x: z.x, y: z.y})), 
      ...map.zones.map(z => ({x: z.x + z.width, y: z.y + z.height}))
    ];
    
    if (allPoints.length === 0) return { minX: -500, minY: -500, maxX: 500, maxY: 500, width: 1000, height: 1000 };
    
    allPoints.forEach(p => {
      const iso = toIso(p.x, p.y);
      if (iso.x < minX) minX = iso.x;
      if (iso.x > maxX) maxX = iso.x;
      if (iso.y < minY) minY = iso.y;
      if (iso.y > maxY) maxY = iso.y;
    });
    
    // Reserve a separate left-side parking area; this is display-only and
    // does not change the frozen start nodes or simulation timings.
    minX -= 360;
    maxY = Math.max(maxY, Math.ceil(robots.length / 3) * 82 + 70);
    // Add padding
    return { 
      minX: minX - 100, 
      minY: minY - 100, 
      maxX: maxX + 100, 
      maxY: maxY + 100,
      width: (maxX - minX) + 200,
      height: (maxY - minY) + 200
    } as { minX: number, minY: number, maxX: number, maxY: number, width: number, height: number };
  }, [map, robots.length]);

  const computedViewBox = useMemo(() => {
    const w = minIsoX.width / scale;
    const h = minIsoX.height / scale;
    const cx = minIsoX.minX + minIsoX.width / 2 + pan.x;
    const cy = minIsoX.minY + minIsoX.height / 2 + pan.y;
    return `${cx - w / 2} ${cy - h / 2} ${w} ${h}`;
  }, [minIsoX, scale, pan]);

  return (
    <div ref={containerRef} className="flex-1 flex flex-col min-w-0 border bg-card rounded-md shadow-sm overflow-hidden relative">
      <div className="p-3 border-b bg-muted/30 flex justify-between items-center z-10 relative">
        <h3 className="font-semibold font-mono text-sm">{title}</h3>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleZoomOut} title="Zoom Out">
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleFit} title="Fit to Screen">
            <Focus className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleZoomIn} title="Zoom In">
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={toggleFullscreen} title="Toggle Fullscreen">
            {isFullscreen ? <Minimize className="h-3.5 w-3.5" /> : <Maximize className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>
      <div 
        className="flex-1 relative overflow-hidden bg-slate-50 dark:bg-slate-900 cursor-move"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg
          viewBox={computedViewBox}
          className="w-full h-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <g aria-label="Robot parking">
            <rect x={minIsoX.minX + 30} y={0} width={330} height={Math.max(150, Math.ceil(robots.length / 3) * 82 + 70)} rx={16} fill="#e2e8f0" stroke="#94a3b8" strokeDasharray="6 5" className="dark:fill-slate-800" />
            <text x={minIsoX.minX + 195} y={27} textAnchor="middle" fontSize={15} className="font-mono font-bold fill-slate-500">ROBOT PARKING</text>
          </g>
          {/* Base Floor Plane */}
          <polygon 
            points={[
              {x: 0, y: 0},
              {x: map.width, y: 0},
              {x: map.width, y: map.height},
              {x: 0, y: map.height}
            ].map(p => {
              const iso = toIso(p.x, p.y);
              return `${iso.x},${iso.y}`;
            }).join(' ')}
            fill="#e2e8f0" 
            stroke="#cbd5e1"
            strokeWidth={2}
            className="dark:fill-slate-800 dark:stroke-slate-700"
          />

          {/* Zones */}
          {zoneVisuals.map(({ zone, p1, p2, p3, p4 }) => {
            const pickEnds = playbackData.zonePickEnds.get(zone.id) || [];
            const remainingPicks = pickEnds.length - completedBy(pickEnds, currentTime);
            const showStock = !run || remainingPicks > 0;
            
            return (
              <g key={zone.id}>
                {/* Zone Floor */}
                <polygon 
                  points={`${p1.x},${p1.y} ${p2.x},${p2.y} ${p3.x},${p3.y} ${p4.x},${p4.y}`}
                  fill="#f1f5f9"
                  stroke="#cbd5e1"
                  strokeWidth={1}
                  className="dark:fill-slate-800/80 dark:stroke-slate-600"
                />
                
                {/* Racks (3D effect) */}
                <path 
                  d={`M${p1.x},${p1.y} v-40 L${p2.x},${p2.y-40} v40 Z`}
                  fill="#94a3b8" 
                  opacity={0.3}
                />
                <path 
                  d={`M${p2.x},${p2.y} v-40 L${p3.x},${p3.y-40} v40 Z`}
                  fill="#64748b" 
                  opacity={0.3}
                />

                {/* Safety Barriers (Yellow) around the zone */}
                <polyline 
                  points={`${p1.x},${p1.y} ${p1.x},${p1.y-10} ${p4.x},${p4.y-10} ${p4.x},${p4.y}`}
                  stroke="#facc15" 
                  fill="none"
                  strokeWidth={4} 
                  strokeDasharray="10, 5"
                />

                {/* Label */}
                <text 
                  x={(p1.x + p3.x) / 2} 
                  y={(p1.y + p3.y) / 2}
                  textAnchor="middle" 
                  fontSize={14} 
                  className="font-mono font-bold fill-slate-500 pointer-events-none"
                  transform={`translate(0, -20)`} // lift up to appear floating
                >
                  {zone.label}
                </text>
                {/* Stock stays in its zone, separate from the robot markers. */}
                {showStock && <g transform={`translate(${(p1.x + p3.x) / 2}, ${(p1.y + p3.y) / 2 + 6})`} aria-label={`${zone.label} stock`} data-zone-stock={zone.id} data-remaining-picks={run ? remainingPicks : undefined}>
                  <title>{zone.label}: {run ? `${remainingPicks} remaining pickup stops` : 'stock'}</title>
                  <polygon points="0,-12 14,-5 0,2 -14,-5" fill="#fcd34d" />
                  <polygon points="-14,-5 0,2 0,17 -14,10" fill="#eab308" />
                  <polygon points="0,2 14,-5 14,10 0,17" fill="#ca8a04" />
                  <path d="M-7,-8 7,-1 V6" stroke="#fef3c7" strokeWidth={3} fill="none" />
                  {run && remainingPicks > 1 && <text x={22} y={10} fontSize={12} className="font-mono font-bold fill-amber-700">{remainingPicks}</text>}
                </g>}
              </g>
            );
          })}

          {/* Conveyor */}
          {(() => {
            const transferDest = map.conveyor?.node_id;
            const cvNode = map.nodes.find(n => n.id === transferDest);
            if (!cvNode) return null;
            const p = toIso(cvNode.x, cvNode.y);
            return (
              <g transform={`translate(${p.x}, ${p.y})`}>
                <polygon 
                  points="0,0 40,20 0,40 -40,20"
                  fill="#475569"
                />
                <polygon 
                  points="-40,20 0,40 0,50 -40,30"
                  fill="#334155"
                />
                <polygon 
                  points="0,40 40,20 40,30 0,50"
                  fill="#1e293b"
                />
                <text y={-10} textAnchor="middle" fontSize={12} className="font-mono font-bold fill-white">
                  CONVEYOR
                </text>
              </g>
            );
          })()}

          {/* Active Paths */}
          {robotStates.map(r => {
            if (!r.isBusy || !r.currentPath || r.currentPath.length < 2) return null;
            return (
              <polyline
                key={`path-${r.id}`}
                points={r.currentPath.map(p => {
                  const iso = toIso(p.x, p.y);
                  return `${iso.x},${iso.y}`;
                }).join(' ')}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={3}
                strokeDasharray="6,4"
                opacity={0.6}
              />
            );
          })}

          {/* Robots */}
          {robotStates.map((r) => {
            return (
              <g 
                key={r.id}
                transform={`translate(${r.isoX}, ${r.isoY})`}
                data-robot-id={r.id}
                data-robot-state={r.isBusy ? 'active' : r.hasStarted ? 'finished-or-waiting' : 'parked'}
                data-robot-activity={r.activityLabel}
                className="cursor-pointer hover:opacity-90"
              >
                {/* Robot shadow */}
                <ellipse cx={0} cy={18} rx={29} ry={13} fill="rgba(0,0,0,0.2)" />
                
                <title>{r.id}: {r.activityLabel}</title>
                <circle r={26} fill={!r.available ? "#fee2e2" : r.isBusy ? "#d1fae5" : "#f8fafc"} stroke={!r.available ? "#dc2626" : r.isBusy ? "#059669" : "#64748b"} strokeWidth={2} />
                <Bot x={-20} y={-20} width={40} height={40} color={!r.available ? "#dc2626" : r.isBusy ? "#047857" : "#475569"} strokeWidth={2} />

                {/* Carried Load (if busy) */}
                {r.isBusy && r.pickedStops > 0 && (
                  <g transform="translate(0, -38)">
                    <polygon points="0,-10 10,-5 0,0 -10,-5" fill="#fcd34d" />
                    <polygon points="-10,-5 0,0 0,10 -10,5" fill="#eab308" />
                    <polygon points="0,0 10,-5 10,5 0,10" fill="#ca8a04" />
                    <text y={-12} textAnchor="middle" fontSize={10} className="font-mono font-bold fill-amber-900 pointer-events-none">
                      {r.pickedStops}
                    </text>
                  </g>
                )}

                {/* Blocked indicator */}
                {!r.available && (
                  <g transform="translate(0, -34)">
                    <circle cx={0} cy={0} r={8} fill="#ef4444" />
                    <path d="M-4,-4 L4,4 M-4,4 L4,-4" stroke="white" strokeWidth={2} strokeLinecap="round" />
                  </g>
                )}

                <g transform="translate(0, 46)" className="pointer-events-none">
                  <rect x={-62} y={-11} width={124} height={r.isBusy ? 38 : 28} rx={4} fill="#0f172a" opacity={0.92} />
                  <text y={2} textAnchor="middle" fontSize={10} className="font-mono font-bold fill-white">
                    {r.id}
                  </text>
                  <text y={16} textAnchor="middle" fontSize={9} className="font-mono fill-slate-200">
                    {r.activityLabel}
                  </text>
                </g>
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-2 right-2 bg-background/80 backdrop-blur-sm border rounded p-2 text-[10px] font-mono pointer-events-none shadow-sm">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-emerald-500 rounded-sm"></div> Busy / Transferring
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-slate-400 rounded-sm"></div> Idle / Parked left
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 bg-red-500 rounded-sm"></div> Blocked / Ineligible
            </div>
            <div className="flex items-center gap-2 mt-1">
              <div className="w-3 h-1 bg-amber-400"></div> Safety Barrier
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
