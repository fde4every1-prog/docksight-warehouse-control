import { useState, useMemo } from 'react';
import { ScenarioMap, Run, ScenarioRobot } from '@/hooks/use-batching';
import { X, Battery, Box, Activity, Zap, CheckCircle2 } from 'lucide-react';

interface MapPanelProps {
  map: ScenarioMap;
  run?: Run;
  robots: ScenarioRobot[];
  currentTime: number;
  title: string;
}

export function MapPanel({ map, run, robots, currentTime, title }: MapPanelProps) {
  const [selectedEntity, setSelectedEntity] = useState<{type: 'robot' | 'bin' | 'station', id: string} | null>(null);

  // Compute robot positions and states
  const robotStates = useMemo(() => {
    return robots.map(robot => {
      let x = 0;
      let y = 0;
      let activeOrderIds: string[] = [];
      let currentStage: string | undefined = undefined;
      let currentToteIds: string[] = [];
      let isBusy = false;
      let currentPath: {x: number, y: number}[] | null = null;
      let available = robot.available;

      const timeline = run?.timeline || [];
      const robotEvents = timeline.filter(e => e.resource_id === robot.id).sort((a, b) => a.start - b.start);
      const currentEvent = robotEvents.find(e => currentTime >= e.start && currentTime <= e.end);
      
      if (currentEvent && currentEvent.path && currentEvent.path.length > 0) {
        isBusy = true;
        activeOrderIds = currentEvent.order_ids || [];
        currentStage = currentEvent.stage;
        currentToteIds = currentEvent.tote_ids || [];
        currentPath = currentEvent.path;
        
        const path = currentEvent.path;
        if (currentTime <= path[0].at) {
          x = path[0].x;
          y = path[0].y;
        } else if (currentTime >= path[path.length - 1].at) {
          x = path[path.length - 1].x;
          y = path[path.length - 1].y;
        } else {
          for (let i = 0; i < path.length - 1; i++) {
            const p1 = path[i];
            const p2 = path[i + 1];
            if (currentTime >= p1.at && currentTime <= p2.at) {
              const progress = (currentTime - p1.at) / (p2.at - p1.at || 1);
              x = p1.x + (p2.x - p1.x) * progress;
              y = p1.y + (p2.y - p1.y) * progress;
              break;
            }
          }
        }
      } else {
        const pastEvents = robotEvents.filter(e => e.end < currentTime);
        if (pastEvents.length > 0) {
          const lastEvent = pastEvents[pastEvents.length - 1];
          if (lastEvent.path && lastEvent.path.length > 0) {
            const p = lastEvent.path[lastEvent.path.length - 1];
            x = p.x;
            y = p.y;
          }
        } else {
          const startNode = map.nodes.find(n => n.id === robot.start_node);
          if (startNode) {
            x = startNode.x;
            y = startNode.y;
          }
        }
      }

      return {
        id: robot.id,
        x,
        y,
        isBusy,
        available,
        activeOrderIds,
        currentStage,
        currentToteIds,
        currentPath,
        capacity_kg: robot.capacity_kg,
        battery_percent: robot.battery_percent,
        capabilities: robot.capabilities,
        blocked_reason: robot.blocked_reason
      };
    });
  }, [robots, run, currentTime, map.nodes]);

  const parkedByNode = useMemo(() => {
    const mapObj = new Map<string, typeof robotStates[0][]>();
    robotStates.forEach(r => {
      if (!r.isBusy) {
        const k = `${Math.round(r.x)},${Math.round(r.y)}`;
        if (!mapObj.has(k)) mapObj.set(k, []);
        mapObj.get(k)!.push(r);
      }
    });
    return mapObj;
  }, [robotStates]);

  const binsByNode = useMemo(() => {
    const mapObj = new Map<string, typeof map.bins>();
    for (const bin of map.bins) {
      if (!mapObj.has(bin.node_id)) mapObj.set(bin.node_id, []);
      mapObj.get(bin.node_id)!.push(bin);
    }
    return mapObj;
  }, [map.bins]);

  const padding = 60;
  const viewBox = `-${padding} -${padding} ${map.width + padding * 2} ${map.height + padding * 2}`;
  
  return (
    <div className="relative self-start h-auto w-full rounded-md border bg-card flex flex-col shadow-sm">
      <div className="p-3 border-b flex items-center justify-between bg-muted/20">
        <h3 className="font-mono font-bold text-sm flex items-center gap-2">
          <span className="bg-primary text-primary-foreground px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider">Synthetic</span>
          {title}
        </h3>
        {run && (
          <div className="font-mono text-sm text-muted-foreground">
            <span className="text-foreground font-bold">{Math.floor(currentTime)}s</span> / {Math.floor(run.metrics.makespan_seconds)}s projected
          </div>
        )}
      </div>

      {selectedEntity && (
        <div className="absolute top-16 left-4 z-20 bg-card border shadow-lg rounded-md p-4 min-w-[240px] text-sm font-mono flex flex-col gap-3">
          <div className="flex items-start justify-between border-b pb-2">
            <span className="font-bold flex items-center gap-2 text-primary">
              {selectedEntity.type === 'robot' && <Activity className="h-4 w-4" />}
              {selectedEntity.type === 'bin' && <Box className="h-4 w-4" />}
              {selectedEntity.type === 'station' && <CheckCircle2 className="h-4 w-4" />}
              {selectedEntity.type.toUpperCase()}: {selectedEntity.id}
            </span>
            <button 
              className="text-muted-foreground hover:text-foreground p-1 rounded-sm hover:bg-muted"
              onClick={() => setSelectedEntity(null)}
              aria-label="Close details"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          
          {selectedEntity.type === 'robot' && (() => {
            const r = robotStates.find(rs => rs.id === selectedEntity.id);
            if (!r) return null;
            return (
              <div className="space-y-3">
                <div className="text-muted-foreground flex items-center gap-2 text-xs uppercase tracking-wider font-bold">
                  <span className={`h-2 w-2 rounded-full ${!r.available ? 'bg-destructive' : r.isBusy ? 'bg-accent' : 'bg-muted-foreground'}`} />
                  {!r.available ? 'Unavailable' : r.isBusy ? 'Busy' : 'Parked'}
                </div>
                
                <div className="grid grid-cols-2 gap-3 text-xs bg-muted/30 p-2 rounded">
                  <div className="flex flex-col gap-1" title="Battery"><span className="text-muted-foreground">Battery</span><span className="flex items-center gap-1 font-bold"><Battery className="h-3 w-3" /> {r.battery_percent}%</span></div>
                  <div className="flex flex-col gap-1" title="Capacity"><span className="text-muted-foreground">Capacity</span><span className="flex items-center gap-1 font-bold"><Box className="h-3 w-3" /> {r.capacity_kg}kg</span></div>
                </div>

                {r.capabilities && r.capabilities.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {r.capabilities.map(cap => (
                      <span key={cap} className="bg-primary/10 text-primary px-1.5 py-0.5 rounded text-[10px] uppercase flex items-center gap-1"><Zap className="h-3 w-3" /> {cap}</span>
                    ))}
                  </div>
                )}

                {!r.available && r.blocked_reason && (
                  <div className="text-destructive text-xs border border-destructive/20 bg-destructive/10 p-2 rounded">{r.blocked_reason}</div>
                )}
                
                {r.isBusy && (
                  <div className="pt-2 border-t space-y-2">
                    {r.currentStage && (
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Stage:</span>
                        <span className="font-bold uppercase text-accent-foreground">{r.currentStage}</span>
                      </div>
                    )}
                    {r.activeOrderIds.length > 0 && (
                      <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground text-xs">Active Orders:</span>
                        <span className="font-bold break-all bg-card border px-2 py-1 rounded">{r.activeOrderIds.join(', ')}</span>
                      </div>
                    )}
                    {r.currentToteIds.length > 0 && (
                      <div className="flex flex-col gap-1">
                        <span className="text-muted-foreground text-xs">Totes:</span>
                        <span className="font-bold break-all">{r.currentToteIds.join(', ')}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          {selectedEntity.type === 'bin' && (() => {
            const b = map.bins.find(bin => bin.id === selectedEntity.id);
            if (!b) return null;
            return (
              <div className="space-y-3">
                <div className="bg-muted/30 p-2 rounded grid grid-cols-2 gap-2 text-xs">
                  <div className="flex flex-col gap-1"><span className="text-muted-foreground">Zone</span><span className="font-bold">{b.zone}</span></div>
                  <div className="flex flex-col gap-1"><span className="text-muted-foreground">Node</span><span className="font-bold">{b.node_id}</span></div>
                </div>
                <div className="border border-primary/20 bg-primary/5 p-3 rounded space-y-1">
                  <div className="text-xs text-muted-foreground uppercase tracking-wider">Inventory</div>
                  <div className="font-bold text-lg">{b.sku}</div>
                  <div className="text-emerald-600 font-bold">{b.stock} units available</div>
                </div>
              </div>
            );
          })()}

          {selectedEntity.type === 'station' && (() => {
            const destEntry = Object.entries(map.destinations).find(([_, id]) => id === selectedEntity.id);
            if (!destEntry) return null;
            return (
              <div className="space-y-3">
                <div className="bg-muted/30 p-2 rounded flex justify-between text-xs">
                  <span className="text-muted-foreground">Node ID</span>
                  <span className="font-bold">{destEntry[1]}</span>
                </div>
                <div className="text-xs bg-primary/10 text-primary p-2 rounded">
                  Designated for <span className="font-bold uppercase">{destEntry[0].replace('_', ' ')}</span> operations.
                </div>
              </div>
            );
          })()}
        </div>
      )}

      <div 
        className="w-full relative min-h-[240px] flex items-center justify-center p-4" 
        onClick={(e) => {
          if ((e.target as SVGElement).tagName === 'svg') setSelectedEntity(null);
        }}
      >
        <svg viewBox={viewBox} className="w-full h-auto max-h-[70vh] cursor-crosshair drop-shadow-sm">
          {/* Zones */}
          {map.zones.map(zone => {
            const isPickup = zone.label.toLowerCase().includes('pick');
            return (
              <g key={zone.id}>
                <rect
                  x={zone.x}
                  y={zone.y}
                  width={zone.width}
                  height={zone.height}
                  fill={isPickup ? "rgb(20, 184, 166)" : "var(--color-muted)"}
                  fillOpacity={isPickup ? 0.08 : 0.2}
                  stroke={isPickup ? "rgb(13, 148, 136)" : "var(--color-muted-foreground)"}
                  strokeOpacity={0.4}
                  strokeDasharray="8 4"
                  strokeWidth={4}
                  rx={8}
                />
                <text
                  x={zone.x + 12}
                  y={zone.y + 24}
                  className="font-mono uppercase font-bold"
                  fontSize={16}
                  fill={isPickup ? "rgb(15, 118, 110)" : "var(--color-muted-foreground)"}
                  opacity={0.7}
                >
                  {zone.label}
                </text>
              </g>
            );
          })}

          {/* Edges (Aisles) */}
          {map.edges.map(edge => {
            const fromNode = map.nodes.find(n => n.id === edge.from);
            const toNode = map.nodes.find(n => n.id === edge.to);
            if (!fromNode || !toNode) return null;
            return (
              <line
                key={`${edge.from}-${edge.to}`}
                x1={fromNode.x}
                y1={fromNode.y}
                x2={toNode.x}
                y2={toNode.y}
                stroke="var(--color-border)"
                strokeWidth={8}
                strokeLinecap="round"
              />
            );
          })}

          {/* Bins (Shelves) */}
          {Array.from(binsByNode.entries()).map(([nodeId, bins]) => {
            const node = map.nodes.find(n => n.id === nodeId);
            if (!node) return null;
            
            return bins.map((bin, i) => {
              const isSelected = selectedEntity?.id === bin.id;
              const binX = node.x - 26;
              const binY = node.y + 24 + i * 42;
              
              return (
                <g 
                  key={bin.id} 
                  onClick={(e) => { e.stopPropagation(); setSelectedEntity({type: 'bin', id: bin.id}); }}
                  onKeyDown={(e) => { if(e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); setSelectedEntity({type: 'bin', id: bin.id}); } }}
                  className="cursor-pointer hover:opacity-90 outline-none"
                  role="button"
                  tabIndex={0}
                  aria-label={`Bin ${bin.id} containing ${bin.stock} of ${bin.sku}`}
                >
                  <line x1={node.x} y1={node.y} x2={node.x} y2={binY} stroke="var(--color-muted-foreground)" strokeDasharray="6 4" strokeWidth={2} />
                  
                  <rect
                    x={binX}
                    y={binY}
                    width={52}
                    height={36}
                    fill={isSelected ? "var(--color-primary)" : "var(--color-card)"}
                    stroke={isSelected ? "var(--color-ring)" : "var(--color-border)"}
                    strokeWidth={isSelected ? 4 : 2}
                    rx={4}
                  />
                  <text x={binX + 26} y={binY + 14} textAnchor="middle" fontSize={12} className={`font-mono font-bold ${isSelected ? 'fill-primary-foreground' : 'fill-foreground'}`}>
                    {bin.id}
                  </text>
                  <text x={binX + 26} y={binY + 28} textAnchor="middle" fontSize={10} className={`font-mono ${isSelected ? 'fill-primary-foreground' : 'fill-muted-foreground'}`}>
                    {bin.stock}
                  </text>
                </g>
              );
            });
          })}

          {/* Nodes / Stations */}
          {Object.entries(map.destinations).map(([key, nodeId]) => {
            const node = map.nodes.find(n => n.id === nodeId);
            if (!node) return null;
            const isSelected = selectedEntity?.id === nodeId;
            const isOutbound = key === 'stage' || key === 'pack_feed';
            
            return (
              <g 
                key={key} 
                onClick={(e) => { e.stopPropagation(); setSelectedEntity({type: 'station', id: nodeId}); }}
                onKeyDown={(e) => { if(e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); setSelectedEntity({type: 'station', id: nodeId}); } }}
                className="cursor-pointer hover:opacity-90 transition-opacity outline-none"
                role="button"
                tabIndex={0}
                aria-label={`Station ${key.replace('_', ' ')}`}
              >
                <circle 
                  cx={node.x} cy={node.y} r={16} 
                  fill={isOutbound ? "rgb(59, 130, 246)" : "var(--color-primary)"} 
                  stroke={isSelected ? "var(--color-ring)" : "var(--color-card)"}
                  strokeWidth={isSelected ? 4 : 2}
                />
                <text x={node.x + 22} y={node.y + 5} fontSize={14} className="font-mono fill-foreground capitalize font-bold">
                  {key.replace('_', ' ')}
                </text>
              </g>
            );
          })}

          {/* Active Robot Paths */}
          {robotStates.map(r => {
            if (!r.isBusy || !r.currentPath || r.currentPath.length < 2) return null;
            return (
              <polyline
                key={`path-${r.id}`}
                points={r.currentPath.map(p => `${p.x},${p.y}`).join(' ')}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={6}
                strokeLinejoin="round"
                opacity={0.6}
              />
            );
          })}

          {/* Robots */}
          {robotStates.map(r => {
            const isSelected = selectedEntity?.id === r.id;
            let rx = r.x;
            let ry = r.y;
            let isParked = !r.isBusy;
            
            if (isParked) {
              const k = `${Math.round(r.x)},${Math.round(r.y)}`;
              const group = parkedByNode.get(k) || [r];
              const idx = group.findIndex(gr => gr.id === r.id);
              if (idx >= 0) {
                rx += 30;
                ry += (idx - (group.length - 1) / 2) * 32;
              }
            }

            return (
              <g 
                key={r.id} 
                transform={`translate(${rx}, ${ry})`} 
                className="transition-transform duration-75 cursor-pointer hover:opacity-90 outline-none"
                onClick={(e) => { e.stopPropagation(); setSelectedEntity({type: 'robot', id: r.id}); }}
                onKeyDown={(e) => { if(e.key === 'Enter' || e.key === ' ') { e.stopPropagation(); setSelectedEntity({type: 'robot', id: r.id}); } }}
                role="button"
                tabIndex={0}
                aria-label={`Robot ${r.id} - ${r.isBusy ? 'Busy' : 'Parked'}`}
              >
                {isParked && (
                  <line x1={r.x - rx} y1={r.y - ry} x2={0} y2={0} stroke="var(--color-muted-foreground)" strokeDasharray="4 4" strokeWidth={2} />
                )}
                
                <circle
                  cx={0}
                  cy={0}
                  r={14}
                  fill={!r.available ? "var(--color-destructive)" : r.isBusy ? "var(--color-accent)" : "var(--color-muted-foreground)"}
                  stroke={isSelected ? "var(--color-ring)" : "var(--color-card)"}
                  strokeWidth={isSelected ? 4 : 2}
                />
                
                {r.isBusy && r.activeOrderIds.length > 0 && (
                  <text x={0} y={4} textAnchor="middle" fontSize={12} className="font-mono font-bold fill-accent-foreground pointer-events-none">
                    {r.activeOrderIds.length}
                  </text>
                )}
                
                {isParked && (
                  <text x={0} y={-18} textAnchor="middle" fontSize={10} className="font-mono font-bold fill-muted-foreground pointer-events-none bg-card px-1">
                    PARKED
                  </text>
                )}
                
                {!r.available && (
                  <path d="M-6,-6 L6,6 M-6,6 L6,-6" stroke="var(--color-card)" strokeWidth={3} className="pointer-events-none" strokeLinecap="round" />
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}