import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef, useCallback, useMemo } from "react";
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from "react-force-graph-2d";
import { getSubjectColor } from "./CrossSubjectGraph3D";
import { CrossLinkData } from "./CrossLinkDetailModal";
import { GraphNodeData } from "../graph/NodeDetailPanel";

export interface CrossGraph2DHandle {
  resetView: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  focusNode: (nodeId: string) => void;
}

interface CrossSubjectGraph2DProps {
  nodes: any[];
  links: any[];
  focusedSubjectId?: string | null;
  focusedTopicId?: string | null;
  selectedNodeId?: string | null;
  onSelectNode: (node: GraphNodeData) => void;
  onSelectLink: (link: CrossLinkData) => void;
  onBackgroundClick?: () => void;
  fadeSameSubject?: boolean;
}

/**
 * Lightweight 2D HTML5 Canvas fallback renderer for Cross-Subject & Focused Graphs (D03, F15, R14).
 * Uses the exact same { nodes, links } structure as CrossSubjectGraph3D so mode switches
 * never lose the student's focused topic or selected links.
 */
export const CrossSubjectGraph2D = forwardRef<CrossGraph2DHandle, CrossSubjectGraph2DProps>(
  (
    {
      nodes,
      links,
      focusedSubjectId = null,
      focusedTopicId = null,
      selectedNodeId = null,
      onSelectNode,
      onSelectLink,
      onBackgroundClick,
      fadeSameSubject = true,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const fgRef = useRef<ForceGraphMethods<NodeObject<any>, LinkObject<any, any>> | undefined>(undefined);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
    const [hoveredNode, setHoveredNode] = useState<any | null>(null);
    const [hoveredLink, setHoveredLink] = useState<any | null>(null);

    const memoNodes = useMemo(() => nodes.map((n) => ({ ...n })), [nodes]);
    const memoLinks = useMemo(
      () =>
        links.map((l) => ({
          ...l,
          source: typeof l.source === "object" ? l.source.id : l.source,
          target: typeof l.target === "object" ? l.target.id : l.target,
        })),
      [links]
    );

    const graphData = useMemo(
      () => ({ nodes: memoNodes, links: memoLinks }),
      [memoNodes, memoLinks]
    );

    // Responsive container sizing (works cleanly on mobile screens too)
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

    // Auto-frame the graph cleanly when switching into 2D or focusing a new topic
    useEffect(() => {
      const timer = setTimeout(() => {
        if (!fgRef.current) return;
        if (focusedTopicId) {
          const target = memoNodes.find((n) => n.id === focusedTopicId);
          if (target && target.x !== undefined && target.y !== undefined) {
            fgRef.current.centerAt(target.x, target.y, 600);
            fgRef.current.zoom(2.0, 600);
            return;
          }
        }
        fgRef.current.zoomToFit(600, 45);
      }, 250);
      return () => clearTimeout(timer);
    }, [focusedTopicId, memoNodes.length]);

    useImperativeHandle(ref, () => ({
      resetView: () => {
        fgRef.current?.zoomToFit(700, 45);
      },
      zoomIn: () => {
        if (fgRef.current) {
          fgRef.current.zoom(fgRef.current.zoom() * 1.4, 350);
        }
      },
      zoomOut: () => {
        if (fgRef.current) {
          fgRef.current.zoom(fgRef.current.zoom() * 0.7, 350);
        }
      },
      focusNode: (nodeId: string) => {
        if (!fgRef.current) return;
        const currentNodes = (fgRef.current as any).graphData?.()?.nodes || memoNodes;
        const target = currentNodes.find((n: any) => n.id === nodeId);
        if (target && target.x !== undefined && target.y !== undefined) {
          fgRef.current.centerAt(target.x, target.y, 700);
          fgRef.current.zoom(2.2, 700);
        } else {
          fgRef.current.zoomToFit(700, 50);
        }
      },
    }));

    const drawNode = useCallback(
      (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const isFocused = focusedTopicId === node.id || Boolean(node.is_focus);
        const isSelected = selectedNodeId === node.id;
        const isHovered = hoveredNode?.id === node.id;
        const isDimmedSubject = focusedSubjectId && node.subject_id !== focusedSubjectId;

        const baseColor = getSubjectColor(node.subject_id);
        const radius = isFocused ? 8.5 : isSelected ? 7.5 : isHovered ? 6.5 : 5.2;

        if (isFocused || isSelected || isHovered) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius + 5, 0, 2 * Math.PI, false);
          ctx.fillStyle = isFocused
            ? "rgba(251, 191, 36, 0.35)"
            : "rgba(99, 102, 241, 0.32)";
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
        ctx.fillStyle = isDimmedSubject ? "rgba(100, 116, 139, 0.35)" : baseColor;
        ctx.fill();

        ctx.lineWidth = isFocused ? 2.8 : isSelected ? 2.2 : 1.3;
        ctx.strokeStyle = isFocused ? "#fbbf24" : isSelected ? "#e0e7ff" : "#0f172a";
        ctx.stroke();

        // Always show labels when focused/hovered/selected or in compact focused views
        const showLabel =
          isFocused ||
          isSelected ||
          isHovered ||
          globalScale > 1.05 ||
          nodes.length <= 45;

        if (showLabel) {
          const label = node.keyword || node.name || "";
          const fontSize = Math.max(10 / globalScale, 3.5);
          ctx.font = `${isFocused || isSelected ? "bold " : ""}${fontSize}px Inter, sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "top";

          const textWidth = ctx.measureText(label).width;
          const bgY = node.y + radius + 3;
          ctx.fillStyle = isFocused
            ? "rgba(251, 191, 36, 0.95)"
            : "rgba(15, 23, 42, 0.88)";
          ctx.fillRect(node.x - textWidth / 2 - 4, bgY - 1.5, textWidth + 8, fontSize + 4);

          ctx.fillStyle = isFocused ? "#0f172a" : "#f8fafc";
          ctx.fillText(label, node.x, bgY);
        }
      },
      [focusedTopicId, selectedNodeId, hoveredNode, focusedSubjectId, nodes.length]
    );

    return (
      <div
        ref={containerRef}
        className="relative w-full h-[540px] sm:h-[620px] bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 shadow-2xl select-none"
      >
        <ForceGraph2D
          ref={fgRef as any}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          backgroundColor="#090d16"
          nodeId="id"
          nodeCanvasObject={drawNode}
          nodePointerAreaPaint={(node: any, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI, false);
            ctx.fill();
          }}
          linkColor={(link: any) => {
            if (hoveredLink?.id === link.id) return "#ffffff";
            if (link.scope === "cross_subject") {
              if (link.strength === 5) return "#f59e0b";
              if (link.strength === 4) return "#38bdf8";
              if (link.strength === 3) return "#a855f7";
              return "#94a3b8";
            }
            return fadeSameSubject ? "rgba(148, 163, 184, 0.16)" : "rgba(148, 163, 184, 0.45)";
          }}
          linkWidth={(link: any) => {
            const base = link.scope === "cross_subject" ? Math.max(1.8, (link.strength || 3) * 0.9) : 1.0;
            return hoveredLink?.id === link.id ? base + 1.5 : base;
          }}
          linkDirectionalArrowLength={(link: any) =>
            link.scope === "cross_subject" || ["prerequisite_of", "applies_in", "part_of", "example_of"].includes(link.type)
              ? 5
              : 0
          }
          linkDirectionalArrowRelPos={0.5}
          linkCurvature={0.08}
          onNodeClick={(node: any) => {
            onSelectNode(node as GraphNodeData);
            if (fgRef.current && node.x !== undefined && node.y !== undefined) {
              fgRef.current.centerAt(node.x, node.y, 600);
            }
          }}
          onLinkClick={(link: any) => onSelectLink(link as CrossLinkData)}
          onNodeHover={(node: any) => setHoveredNode(node || null)}
          onLinkHover={(link: any) => setHoveredLink(link || null)}
          onBackgroundClick={() => onBackgroundClick?.()}
          cooldownTicks={90}
          d3AlphaDecay={0.03}
          d3VelocityDecay={0.32}
        />

        {/* Lightweight 2D Hint Overlay */}
        <div className="absolute bottom-4 left-4 pointer-events-none text-slate-300 text-xs bg-slate-900/90 backdrop-blur-xs px-3.5 py-2 rounded-xl border border-slate-700/80 shadow-lg">
          <span className="font-semibold text-emerald-300">2D Focus Mode: </span>
          <span>Drag to pan • Pinch/scroll to zoom • Click any concept for its Theory Card</span>
        </div>
      </div>
    );
  }
);

CrossSubjectGraph2D.displayName = "CrossSubjectGraph2D";

