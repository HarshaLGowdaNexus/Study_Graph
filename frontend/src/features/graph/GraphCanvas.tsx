import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef, useCallback, useMemo } from "react";
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from "react-force-graph-2d";
import { forceCollide } from "d3-force-3d";
import { GraphNodeData } from "./NodeDetailPanel";
import { GraphLinkData } from "./LinkDetailPanel";

export interface GraphCanvasHandle {
  zoomToCluster: (clusterId: string) => void;
  resetView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
}

interface GraphCanvasProps {
  nodes: GraphNodeData[];
  links: GraphLinkData[];
  selectedNodeId?: string | null;
  selectedLinkId?: string | null;
  onNodeSelect: (node: GraphNodeData) => void;
  onLinkSelect: (link: GraphLinkData) => void;
  onBackgroundClick: () => void;
  showWeakLinks: boolean;
  weakLinkThreshold?: number;
}

const CLUSTER_COLORS = [
  "#4f46e5", // Indigo
  "#059669", // Emerald
  "#d97706", // Amber
  "#7c3aed", // Purple
  "#0284c7", // Sky
  "#e11d48", // Rose
  "#0d9488", // Teal
  "#ea580c", // Orange
  "#475569", // Slate
];

const LINK_TYPE_COLORS: Record<string, string> = {
  prerequisite_of: "#6366f1",
  same_concept: "#10b981",
  part_of: "#a855f7",
  contrasts_with: "#f59e0b",
  applies_in: "#06b6d4",
  example_of: "#0ea5e9",
};

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  (
    {
      nodes,
      links,
      selectedNodeId,
      selectedLinkId,
      onNodeSelect,
      onLinkSelect,
      onBackgroundClick,
      showWeakLinks,
      weakLinkThreshold = 3,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const fgRef = useRef<ForceGraphMethods<NodeObject<GraphNodeData>, LinkObject<GraphNodeData, GraphLinkData>> | undefined>(undefined);

    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
    const [hoveredNode, setHoveredNode] = useState<GraphNodeData | null>(null);
    const [hoveredLink, setHoveredLink] = useState<GraphLinkData | null>(null);

    // Responsive container auto-sizing
    useEffect(() => {
      const updateSize = () => {
        if (containerRef.current) {
          const { clientWidth, clientHeight } = containerRef.current;
          if (clientWidth > 0 && clientHeight > 0) {
            setDimensions({ width: clientWidth, height: clientHeight });
          }
        }
      };

      updateSize();
      window.addEventListener("resize", updateSize);
      const observer = new ResizeObserver(updateSize);
      if (containerRef.current) observer.observe(containerRef.current);

      return () => {
        window.removeEventListener("resize", updateSize);
        observer.disconnect();
      };
    }, []);

    // Filter links based on weak-link threshold (Rule 13.8, Risk R09)
    const activeLinks = useMemo(() => {
      if (showWeakLinks) return links;
      return links.filter((l) => (l.strength || 1) >= weakLinkThreshold);
    }, [links, showWeakLinks, weakLinkThreshold]);

    // Graph data formatted for react-force-graph
    const graphData = useMemo(() => {
      return {
        nodes: nodes.map((n) => ({ ...n })),
        links: activeLinks.map((l) => ({ ...l })),
      };
    }, [nodes, activeLinks]);

    // Map clusters to distinct colors
    const clusterColorMap = useMemo(() => {
      const map: Record<string, string> = {};
      const uniqueClusters = Array.from(
        new Set(nodes.map((n) => n.parent_cluster_label || n.cluster_label || "default"))
      );
      uniqueClusters.forEach((c, idx) => {
        map[c] = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
      });
      return map;
    }, [nodes]);

    // Compute connectivity map: node ID -> set of adjacent neighbor node IDs
    const neighborsMap = useMemo(() => {
      const map = new Map<string, Set<string>>();
      for (const l of activeLinks) {
        const srcId = typeof l.source === "object" ? (l.source as any).id : (l.source as string);
        const tgtId = typeof l.target === "object" ? (l.target as any).id : (l.target as string);
        if (!srcId || !tgtId) continue;
        if (!map.has(srcId)) map.set(srcId, new Set());
        if (!map.has(tgtId)) map.set(tgtId, new Set());
        map.get(srcId)!.add(tgtId);
        map.get(tgtId)!.add(srcId);
      }
      return map;
    }, [activeLinks]);

    // Compute node degree (connection count) for visual hierarchy & hub detection
    const nodeDegrees = useMemo(() => {
      const map = new Map<string, number>();
      for (const l of activeLinks) {
        const srcId = typeof l.source === "object" ? (l.source as any).id : (l.source as string);
        const tgtId = typeof l.target === "object" ? (l.target as any).id : (l.target as string);
        if (srcId) map.set(srcId, (map.get(srcId) || 0) + 1);
        if (tgtId) map.set(tgtId, (map.get(tgtId) || 0) + 1);
      }
      return map;
    }, [activeLinks]);

    // Active spotlight target: hovered node takes precedence, then selected node
    const activeFocusId = hoveredNode?.id || selectedNodeId || null;

    // Set of IDs that should stay fully visible (focused node + its direct neighbors)
    const spotlightNeighborIds = useMemo(() => {
      if (!activeFocusId) return null;
      const set = new Set<string>();
      set.add(activeFocusId);
      const nbrs = neighborsMap.get(activeFocusId);
      if (nbrs) {
        nbrs.forEach((id) => set.add(id));
      }
      return set;
    }, [activeFocusId, neighborsMap]);

    // Physics Engine Tuning: Adaptive spacing for real notes vs benchmark (T14B)
    // Small/Standard graphs (e.g. 20-100 real notes topics) need much stronger individual repulsion (-780)
    // and longer link springs (140px) to prevent clumping.
    // Massive benchmark graphs (500 topics) have huge collective mass, so they use tighter individual settings.
    useEffect(() => {
      const fg = fgRef.current;
      if (!fg) return;

      const nodeCount = nodes.length;
      const isRealNotes = nodeCount <= 120;

      // 1. Charge repulsion:
      // In a 47-node graph, -780 pushes each node far away so clusters form distinct open islands
      const chargeStrength = isRealNotes ? -780 : -320;
      const chargeForce: any = fg.d3Force("charge");
      if (chargeForce) {
        chargeForce.strength(chargeStrength);
        chargeForce.distanceMax(1200);
        chargeForce.distanceMin(35);
      }

      // 2. Link force:
      // 140px distance for real notes (instead of 85px) gives generous, airy breathing room
      const linkDistance = isRealNotes ? 140 : 65;
      const linkForce: any = fg.d3Force("link");
      if (linkForce) {
        linkForce.distance(linkDistance);
      }

      // 3. Collision force:
      // Minimum 32px radius (64px center-to-center) guarantees wide physical spacing between any two concepts
      const baseCollideRadius = isRealNotes ? 32 : 20;
      fg.d3Force(
        "collide",
        forceCollide((node: any) => {
          const degree = nodeDegrees.get(node.id) || 1;
          return baseCollideRadius + Math.min(degree * 2.5, 18);
        }).iterations(3)
      );

      // 4. Centering pull:
      // Weaken inward pull for real notes (0.018 vs 0.06) so the center doesn't collapse nodes inward
      const centerStrength = isRealNotes ? 0.018 : 0.06;
      const centerForce: any = fg.d3Force("center");
      if (centerForce) {
        centerForce.strength(centerStrength);
      }

      fg.d3ReheatSimulation();
    }, [graphData, nodeDegrees, nodes.length]);

    // Expose camera controls to parent component
    useImperativeHandle(ref, () => ({
      zoomToCluster: (clusterId: string) => {
        if (!fgRef.current) return;
        const targetNodes = nodes.filter(
          (n) => n.cluster_id === clusterId || n.parent_cluster_label === clusterId
        );
        if (targetNodes.length === 0) return;

        // Calculate centroid of the cluster nodes
        const xs = targetNodes.map((n) => n.x || 0).filter((x) => !isNaN(x));
        const ys = targetNodes.map((n) => n.y || 0).filter((y) => !isNaN(y));
        if (xs.length > 0 && ys.length > 0) {
          const avgX = xs.reduce((a, b) => a + b, 0) / xs.length;
          const avgY = ys.reduce((a, b) => a + b, 0) / ys.length;

          // Smooth cinematic 1000ms animation
          fgRef.current.centerAt(avgX, avgY, 1000);
          fgRef.current.zoom(2.0, 1000);
        } else {
          fgRef.current.zoomToFit(1000, 60, (node: any) =>
            node.cluster_id === clusterId || node.parent_cluster_label === clusterId
          );
        }
      },
      resetView: () => {
        if (fgRef.current) {
          fgRef.current.zoomToFit(900, 45);
        }
      },
      zoomIn: () => {
        if (fgRef.current) {
          const currentZoom = fgRef.current.zoom();
          fgRef.current.zoom(currentZoom * 1.35, 300);
        }
      },
      zoomOut: () => {
        if (fgRef.current) {
          const currentZoom = fgRef.current.zoom();
          fgRef.current.zoom(currentZoom * 0.72, 300);
        }
      },
    }));

    // Custom HTML5 Canvas Node Rendering with Progressive Disclosure & Dark Translucent Pills (T14B)
    const drawNode = useCallback(
      (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        if (node.x === undefined || node.y === undefined) return;

        const isSpotlightActive = spotlightNeighborIds !== null;
        const isRelevant = !isSpotlightActive || spotlightNeighborIds.has(node.id);
        const isSelected = selectedNodeId === node.id;
        const isHovered = hoveredNode?.id === node.id;
        const isFocusCenter = activeFocusId === node.id;
        const degree = nodeDegrees.get(node.id) || 0;
        const isHub = degree >= 3;

        const clusterName = node.parent_cluster_label || node.cluster_label || "default";
        const color = clusterColorMap[clusterName] || "#6366f1";

        ctx.save();
        try {
          // Dim unrelated nodes when spotlighting is active
          if (isSpotlightActive && !isRelevant) {
            ctx.globalAlpha = 0.2;
          }

          // Node radius with subtle hierarchy
          const baseRadius = 5.5 + Math.min(degree * 0.35, 2.5);
          const radius = isSelected
            ? baseRadius + 3.5
            : isHovered
            ? baseRadius + 2.5
            : isFocusCenter
            ? baseRadius + 2
            : baseRadius;

          // Halo / Glow for selected, hovered, or spotlighted neighbor nodes
          if (isSelected || isHovered) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius + 5, 0, 2 * Math.PI, false);
            ctx.fillStyle = isSelected
              ? "rgba(99, 102, 241, 0.45)"
              : "rgba(148, 163, 184, 0.35)";
            ctx.fill();
          } else if (isSpotlightActive && isRelevant && !isFocusCenter) {
            // Subtle indicator ring for connected neighbors
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI, false);
            ctx.fillStyle = "rgba(129, 140, 248, 0.28)";
            ctx.fill();
          }

          // Main Node Circle
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
          ctx.fillStyle = color;
          ctx.fill();

          ctx.lineWidth = isSelected ? 2.5 : isHovered ? 2 : 1.5;
          ctx.strokeStyle = isSelected ? "#ffffff" : isHovered ? "#f8fafc" : "rgba(255, 255, 255, 0.85)";
          ctx.stroke();

          // Reviewed indicator dot
          if (node.reviewed === false) {
            ctx.beginPath();
            ctx.arc(node.x + radius * 0.7, node.y - radius * 0.7, 2.5, 0, 2 * Math.PI, false);
            ctx.fillStyle = "#f59e0b"; // Amber warning dot
            ctx.fill();
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 1;
            ctx.stroke();
          }

          // Progressive Label Disclosure (T14B Anti-Clutter):
          // 1. Hovered or selected node ALWAYS shows label
          // 2. Direct neighbors of active focus node ALWAYS show label
          // 3. Cluster hubs (degree >= 3) show labels at normal zoom (scale >= 0.75)
          // 4. Medium nodes show labels when zoomed in (scale >= 1.1)
          // 5. All nodes show labels when deeply zoomed (scale >= 1.4) or in small graphs (<= 15 nodes)
          const isNeighborOfFocus = isSpotlightActive && spotlightNeighborIds.has(node.id);
          const shouldShowLabel =
            isHovered ||
            isSelected ||
            isNeighborOfFocus ||
            (isHub && globalScale >= 0.75) ||
            (degree >= 2 && globalScale >= 1.05) ||
            globalScale >= 1.35 ||
            nodes.length <= 15;

          if (shouldShowLabel) {
            const label = node.keyword || node.name || "";
            const fontSize = Math.max(9.5 / globalScale, 3.2);
            ctx.font = `${isSelected || isHovered ? "600 " : "500 "}${fontSize}px Inter, system-ui, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";

            const textMetrics = ctx.measureText(label);
            const padX = 6 / globalScale;
            const padY = 3.2 / globalScale;
            const pillW = textMetrics.width + padX * 2;
            const pillH = fontSize + padY * 2;
            const pillX = node.x - pillW / 2;
            const pillY = node.y + radius + 3.5 / globalScale;
            const pillR = Math.min(4 / globalScale, pillH / 2);

            // Draw sleek dark translucent pill badge
            ctx.beginPath();
            if (typeof (ctx as any).roundRect === "function") {
              (ctx as any).roundRect(pillX, pillY, pillW, pillH, pillR);
            } else {
              ctx.rect(pillX, pillY, pillW, pillH);
            }

            if (isSelected) {
              ctx.fillStyle = "rgba(49, 46, 129, 0.95)";
              ctx.strokeStyle = "#818cf8";
              ctx.lineWidth = 1.2 / globalScale;
            } else if (isHovered) {
              ctx.fillStyle = "rgba(15, 23, 42, 0.95)";
              ctx.strokeStyle = "#cbd5e1";
              ctx.lineWidth = 1.1 / globalScale;
            } else if (isNeighborOfFocus) {
              ctx.fillStyle = "rgba(30, 41, 59, 0.92)";
              ctx.strokeStyle = "rgba(129, 140, 248, 0.6)";
              ctx.lineWidth = 0.9 / globalScale;
            } else {
              ctx.fillStyle = "rgba(15, 23, 42, 0.82)";
              ctx.strokeStyle = "rgba(71, 85, 105, 0.45)";
              ctx.lineWidth = 0.75 / globalScale;
            }
            ctx.fill();
            ctx.stroke();

            // Label Text
            ctx.fillStyle = isSelected
              ? "#ffffff"
              : isHovered
              ? "#ffffff"
              : isNeighborOfFocus
              ? "#e2e8f0"
              : "#cbd5e1";
            ctx.fillText(label, node.x, pillY + pillH / 2);
          }
        } finally {
          ctx.restore();
        }
      },
      [
        selectedNodeId,
        hoveredNode,
        clusterColorMap,
        nodes.length,
        activeFocusId,
        spotlightNeighborIds,
        nodeDegrees,
      ]
    );

    return (
      <div ref={containerRef} className="w-full h-full relative bg-slate-900 overflow-hidden select-none">
        {/* Floating Quick Navigation & Interaction Hint */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          <div className="px-3.5 py-1 rounded-full bg-slate-900/85 backdrop-blur-md border border-slate-700/60 shadow-lg text-[11px] text-slate-300 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" />
            <span>Hover any node to spotlight connections • Scroll or pinch to zoom</span>
          </div>
        </div>

        {/* Floating Quick Canvas Zoom / Reset Controls */}
        <div className="absolute top-3 right-3 z-10 flex flex-col items-center gap-1 bg-slate-900/85 backdrop-blur-md p-1.5 rounded-xl border border-slate-700/60 shadow-xl">
          <button
            type="button"
            onClick={() => {
              if (fgRef.current) {
                const cur = fgRef.current.zoom();
                fgRef.current.zoom(cur * 1.35, 300);
              }
            }}
            className="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-800/80 hover:bg-indigo-600 text-slate-200 hover:text-white transition text-sm font-bold shadow-xs"
            title="Zoom In (+)"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => {
              if (fgRef.current) {
                const cur = fgRef.current.zoom();
                fgRef.current.zoom(cur * 0.72, 300);
              }
            }}
            className="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-800/80 hover:bg-indigo-600 text-slate-200 hover:text-white transition text-sm font-bold shadow-xs"
            title="Zoom Out (-)"
          >
            −
          </button>
          <button
            type="button"
            onClick={() => {
              if (fgRef.current) {
                fgRef.current.zoomToFit(800, 45);
              }
            }}
            className="w-7 h-7 flex items-center justify-center rounded-lg bg-slate-800/80 hover:bg-indigo-600 text-slate-200 hover:text-white transition text-xs font-semibold shadow-xs"
            title="Reset View / Fit Screen"
          >
            ⤢
          </button>
        </div>

        <ForceGraph2D
          ref={fgRef as any}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          nodeId="id"
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={(node: any, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI, false);
            ctx.fill();
          }}
          // Link thickness determined by strength and spotlight state
          linkWidth={(link: any) => {
            const isSelected = selectedLinkId === link.id;
            const isHovered = hoveredLink?.id === link.id;
            const baseStrength = link.strength || 1;
            const width = Math.max(1, baseStrength * 0.9);

            if (activeFocusId) {
              const srcId = typeof link.source === "object" ? link.source.id : link.source;
              const tgtId = typeof link.target === "object" ? link.target.id : link.target;
              const isConnected = srcId === activeFocusId || tgtId === activeFocusId;
              if (isConnected) return width + 2.2;
              return Math.max(0.6, width * 0.4);
            }

            return isSelected ? width + 2 : isHovered ? width + 1.2 : width;
          }}
          // Link color with spotlighting & dimming
          linkColor={(link: any) => {
            if (selectedLinkId === link.id) return "#818cf8";
            if (hoveredLink?.id === link.id) return "#cbd5e1";

            const srcId = typeof link.source === "object" ? link.source.id : link.source;
            const tgtId = typeof link.target === "object" ? link.target.id : link.target;

            if (activeFocusId) {
              const isConnected = srcId === activeFocusId || tgtId === activeFocusId;
              if (isConnected) {
                return "#818cf8"; // Bright highlighted connection
              }
              // Dim unrelated links strongly
              return "rgba(100, 116, 139, 0.12)";
            }

            const typeColor = LINK_TYPE_COLORS[link.type] || "#94a3b8";
            // Dim weak links slightly
            return (link.strength || 1) < weakLinkThreshold ? "rgba(148, 163, 184, 0.35)" : typeColor;
          }}
          // Directional arrows placed at midpoint (0.5) so they are NEVER hidden behind node circles
          linkDirectionalArrowLength={(link: any) => {
            const directional = ["prerequisite_of", "applies_in", "part_of", "example_of"];
            if (!directional.includes(link.type)) return 0;

            if (activeFocusId) {
              const srcId = typeof link.source === "object" ? link.source.id : link.source;
              const tgtId = typeof link.target === "object" ? link.target.id : link.target;
              const isConnected = srcId === activeFocusId || tgtId === activeFocusId;
              return isConnected ? 6.5 : 0;
            }
            return 5.5;
          }}
          linkDirectionalArrowRelPos={0.5}
          linkCurvature={0.08}
          // Interaction handlers
          onNodeClick={(node: any) => {
            onNodeSelect(node);
            if (fgRef.current && node.x !== undefined && node.y !== undefined) {
              fgRef.current.centerAt(node.x, node.y, 800);
            }
          }}
          onLinkClick={(link: any) => {
            onLinkSelect(link);
          }}
          onNodeHover={(node: any) => setHoveredNode(node || null)}
          onLinkHover={(link: any) => setHoveredLink(link || null)}
          onBackgroundClick={() => {
            setHoveredNode(null);
            setHoveredLink(null);
            onBackgroundClick();
          }}
          warmupTicks={40}
          cooldownTicks={140}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.28}
        />

        {/* Legend Overlay at bottom-left */}
        <div className="absolute bottom-4 left-4 z-10 bg-slate-900/90 backdrop-blur-md p-3.5 rounded-xl border border-slate-700/60 shadow-xl text-xs text-slate-300 pointer-events-none max-w-xs space-y-2.5">
          <div className="font-bold text-white flex items-center justify-between border-b border-slate-800 pb-1.5">
            <span>Visual Legend</span>
            <span className="text-[10px] text-slate-400">T14 Subject Graph</span>
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 shrink-0" />
              <span className="text-[11px]">Nodes = Concepts colored by Cluster</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-4 h-0.5 bg-indigo-400 shrink-0" />
              <span className="text-[11px]">Line Thickness = Strength (1-5)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-indigo-400 font-bold shrink-0 text-xs">→</span>
              <span className="text-[11px]">Midpoint Arrow = One-way flow (Prerequisite / Part of)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-0.5 bg-slate-400 shrink-0" />
              <span className="text-[11px]">Plain Line = Mutual comparison (Same concept / Contrasts)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
              <span className="text-[11px]">Amber Dot = Unreviewed topic</span>
            </div>
          </div>
        </div>
      </div>
    );
  }
);

GraphCanvas.displayName = "GraphCanvas";
