import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef, useCallback } from "react";
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from "react-force-graph-2d";
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
    const activeLinks = React.useMemo(() => {
      if (showWeakLinks) return links;
      return links.filter((l) => (l.strength || 1) >= weakLinkThreshold);
    }, [links, showWeakLinks, weakLinkThreshold]);

    // Graph data formatted for react-force-graph
    const graphData = React.useMemo(() => {
      return {
        nodes: nodes.map((n) => ({ ...n })),
        links: activeLinks.map((l) => ({ ...l })),
      };
    }, [nodes, activeLinks]);

    // Map clusters to distinct colors
    const clusterColorMap = React.useMemo(() => {
      const map: Record<string, string> = {};
      const uniqueClusters = Array.from(
        new Set(nodes.map((n) => n.parent_cluster_label || n.cluster_label || "default"))
      );
      uniqueClusters.forEach((c, idx) => {
        map[c] = CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
      });
      return map;
    }, [nodes]);

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
          fgRef.current.zoom(2.2, 1000);
        } else {
          fgRef.current.zoomToFit(1000, 60, (node: any) =>
            node.cluster_id === clusterId || node.parent_cluster_label === clusterId
          );
        }
      },
      resetView: () => {
        if (fgRef.current) {
          fgRef.current.zoomToFit(1000, 50);
        }
      },
      zoomIn: () => {
        if (fgRef.current) {
          const currentZoom = fgRef.current.zoom();
          fgRef.current.zoom(currentZoom * 1.4, 400);
        }
      },
      zoomOut: () => {
        if (fgRef.current) {
          const currentZoom = fgRef.current.zoom();
          fgRef.current.zoom(currentZoom * 0.7, 400);
        }
      },
    }));

    // Custom HTML5 Canvas Node Rendering for high performance (R14)
    const drawNode = useCallback(
      (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const isSelected = selectedNodeId === node.id;
        const isHovered = hoveredNode?.id === node.id;
        const clusterName = node.parent_cluster_label || node.cluster_label || "default";
        const color = clusterColorMap[clusterName] || "#6366f1";

        // Radius based on connectivity (degree)
        const baseRadius = 5;
        const radius = isSelected ? baseRadius + 3 : isHovered ? baseRadius + 2 : baseRadius;

        // Selection / Hover Halo Glow
        if (isSelected || isHovered) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI, false);
          ctx.fillStyle = isSelected ? "rgba(99, 102, 241, 0.35)" : "rgba(148, 163, 184, 0.3)";
          ctx.fill();
        }

        // Main Node Circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
        ctx.fillStyle = color;
        ctx.fill();

        // Border outline
        ctx.lineWidth = isSelected ? 2.5 : 1.5;
        ctx.strokeStyle = isSelected ? "#1e1b4b" : "#ffffff";
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

        // Draw Text Label
        // Render label if zoomed in (scale > 1.1) or if hovered/selected to prevent hairball clutter (R09)
        const shouldShowLabel = globalScale > 1.1 || isHovered || isSelected || nodes.length < 40;
        if (shouldShowLabel) {
          const label = node.keyword || node.name || "";
          const fontSize = Math.max(9 / globalScale, 3);
          ctx.font = `${isSelected ? "bold " : ""}${fontSize}px Inter, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";

          // Label text background pill for clean readability
          const textWidth = ctx.measureText(label).width;
          const bgHeight = fontSize + 3;
          const bgY = node.y + radius + 3;

          ctx.fillStyle = "rgba(255, 255, 255, 0.88)";
          ctx.fillRect(node.x - textWidth / 2 - 3, bgY - 1, textWidth + 6, bgHeight);

          ctx.fillStyle = isSelected ? "#312e81" : "#1e293b";
          ctx.fillText(label, node.x, bgY);
        }
      },
      [selectedNodeId, hoveredNode, clusterColorMap, nodes.length]
    );

    return (
      <div ref={containerRef} className="w-full h-full relative bg-slate-900 overflow-hidden select-none">
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
            ctx.arc(node.x, node.y, 8, 0, 2 * Math.PI, false);
            ctx.fill();
          }}
          // Link thickness determined strictly by strength (Task requirement)
          linkWidth={(link: any) => {
            const isSelected = selectedLinkId === link.id;
            const isHovered = hoveredLink?.id === link.id;
            const baseStrength = link.strength || 1;
            const width = Math.max(1, baseStrength * 0.9);
            return isSelected ? width + 2 : isHovered ? width + 1.2 : width;
          }}
          // Link color based on relationship type
          linkColor={(link: any) => {
            if (selectedLinkId === link.id) return "#818cf8";
            if (hoveredLink?.id === link.id) return "#cbd5e1";
            const typeColor = LINK_TYPE_COLORS[link.type] || "#94a3b8";
            // Dim weak links slightly
            return (link.strength || 1) < weakLinkThreshold ? "rgba(148, 163, 184, 0.35)" : typeColor;
          }}
          // Directional arrows: placed at the midpoint (0.5) so they are NEVER hidden behind node circles
          // Directional relationships (prerequisite, applies_in, part_of, example_of) get arrows
          // Symmetric relationships (same_concept, contrasts_with) have no arrow (two-way comparison)
          linkDirectionalArrowLength={(link: any) => {
            const directional = ["prerequisite_of", "applies_in", "part_of", "example_of"];
            return directional.includes(link.type) ? 6 : 0;
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
            onBackgroundClick();
          }}
          cooldownTicks={120}
          d3AlphaDecay={0.025}
          d3VelocityDecay={0.3}
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

