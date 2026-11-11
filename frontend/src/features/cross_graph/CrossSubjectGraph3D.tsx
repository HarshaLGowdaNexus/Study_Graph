import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef, useCallback, useMemo } from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import { CrossLinkData } from "./CrossLinkDetailModal";

export const SUBJECT_PALETTE: string[] = [
  "#38bdf8", // Sky / Cyan
  "#a855f7", // Purple / Violet
  "#f97316", // Amber / Orange
  "#10b981", // Emerald / Mint
  "#ec4899", // Rose / Pink
  "#eab308", // Yellow / Gold
  "#6366f1", // Indigo
];

export const getSubjectColor = (subjectId?: string): string => {
  if (!subjectId) return "#94a3b8";
  let hash = 0;
  for (let i = 0; i < subjectId.length; i++) {
    hash = (hash << 5) - hash + subjectId.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % SUBJECT_PALETTE.length;
  return SUBJECT_PALETTE[index];
};

export const getClusterCenter = (subjectId: string, subjectsList: any[]): { x: number; y: number; z: number } => {
  const found = subjectsList.find((s) => s.id === subjectId);
  if (found?.center) return found.center;

  const idx = subjectsList.findIndex((s) => s.id === subjectId);
  const total = Math.max(1, subjectsList.length);
  const angle = ((idx >= 0 ? idx : 0) / total) * Math.PI * 2;
  const radius = 190;
  return {
    x: Math.cos(angle) * radius,
    y: Math.sin(angle * 2) * 70,
    z: Math.sin(angle) * radius,
  };
};

export interface CrossGraph3DHandle {
  resetCamera: () => void;
  flyToSubject: (subjectId: string, subjectCenter?: { x: number; y: number; z: number }) => void;
  toggleAutoRotate: (enabled: boolean) => void;
}

interface CrossSubjectGraph3DProps {
  nodes: any[];
  links: any[];
  subjects?: any[];
  focusedSubjectId?: string | null;
  onSelectLink: (link: CrossLinkData) => void;
  onAutoRotateChange?: (rotating: boolean) => void;
  fadeSameSubject?: boolean;
}

export const CrossSubjectGraph3D = forwardRef<CrossGraph3DHandle, CrossSubjectGraph3DProps>(
  (
    {
      nodes,
      links,
      subjects = [],
      focusedSubjectId = null,
      onSelectLink,
      onAutoRotateChange,
      fadeSameSubject = true,
    },
    ref
  ) => {
    const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
    const containerRef = useRef<HTMLDivElement>(null);
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
    const [isAutoRotating, setIsAutoRotating] = useState(false);
    const orbitAngleRef = useRef(0);

    // Memoize nodes separately from links so changing the strength filter
    // never resets or scrambles node positions in 3D space!
    const memoNodes = useMemo(() => {
      return nodes.map((n) => ({ ...n }));
    }, [nodes]);

    const memoLinks = useMemo(() => {
      return links.map((l) => ({
        ...l,
        source: typeof l.source === "object" ? l.source.id : l.source,
        target: typeof l.target === "object" ? l.target.id : l.target,
      }));
    }, [links]);

    const graphData = useMemo(
      () => ({ nodes: memoNodes, links: memoLinks }),
      [memoNodes, memoLinks]
    );

    // Measure container size
    useEffect(() => {
      const updateSize = () => {
        if (containerRef.current) {
          setDimensions({
            width: containerRef.current.clientWidth || 800,
            height: containerRef.current.clientHeight || 600,
          });
        }
      };
      updateSize();
      window.addEventListener("resize", updateSize);
      return () => window.removeEventListener("resize", updateSize);
    }, []);

    // Configure D3 cluster forces so subjects stay in clear separate 3D galaxies
    useEffect(() => {
      if (!fgRef.current) return;

      const clusterForce = (alpha: number) => {
        const currentData = (fgRef.current as any)?.graphData?.();
        if (!currentData?.nodes) return;
        const strength = 0.25 * alpha;
        for (const node of currentData.nodes) {
          const center = getClusterCenter(node.subject_id, subjects);
          node.vx = (node.vx || 0) + (center.x - (node.x || 0)) * strength;
          node.vy = (node.vy || 0) + (center.y - (node.y || 0)) * strength;
          node.vz = (node.vz || 0) + (center.z - (node.z || 0)) * strength;
        }
      };

      fgRef.current.d3Force("subjectCluster", clusterForce as any);

      const linkForce = fgRef.current.d3Force("link") as any;
      if (linkForce && typeof linkForce.distance === "function") {
        linkForce.distance((link: any) => (link.scope === "cross_subject" ? 210 : 40));
      }
    }, [subjects, graphData]);

    // Continuous 360-degree auto-rotation animation loop
    useEffect(() => {
      if (!isAutoRotating) return;
      let animId: number;

      const rotateStep = () => {
        if (fgRef.current) {
          orbitAngleRef.current += 0.008; // Smooth, cinematic rotation
          const radius = 420;
          const x = radius * Math.sin(orbitAngleRef.current);
          const z = radius * Math.cos(orbitAngleRef.current);
          const y = 85;
          fgRef.current.cameraPosition({ x, y, z }, { x: 0, y: 0, z: 0 }, 0);
        }
        animId = requestAnimationFrame(rotateStep);
      };

      animId = requestAnimationFrame(rotateStep);
      return () => cancelAnimationFrame(animId);
    }, [isAutoRotating]);

    // Imperative Camera Controls
    useImperativeHandle(ref, () => ({
      resetCamera: () => {
        setIsAutoRotating(false);
        onAutoRotateChange?.(false);
        if (!fgRef.current) return;
        fgRef.current.cameraPosition({ x: 0, y: 80, z: 450 }, { x: 0, y: 0, z: 0 }, 900);
      },
      flyToSubject: (subjectId: string, subjectCenter?: { x: number; y: number; z: number }) => {
        setIsAutoRotating(false);
        onAutoRotateChange?.(false);
        if (!fgRef.current) return;

        const center = subjectCenter || getClusterCenter(subjectId, subjects);
        let targetX = center.x;
        let targetY = center.y;
        let targetZ = center.z;

        const currentData = (fgRef.current as any).graphData?.();
        if (currentData?.nodes) {
          const subjNodes = currentData.nodes.filter(
            (n: any) => n.subject_id === subjectId && n.x !== undefined
          );
          if (subjNodes.length > 0) {
            targetX = subjNodes.reduce((sum: number, n: any) => sum + n.x, 0) / subjNodes.length;
            targetY = subjNodes.reduce((sum: number, n: any) => sum + n.y, 0) / subjNodes.length;
            targetZ = subjNodes.reduce((sum: number, n: any) => sum + n.z, 0) / subjNodes.length;
          }
        }

        // Compute dramatic offset looking directly into the subject galaxy
        const dist = Math.hypot(targetX, targetY, targetZ) || 1;
        const zoomDist = 140;
        const camX = targetX + (targetX / dist) * zoomDist;
        const camY = targetY + 40;
        const camZ = targetZ + (targetZ / dist) * zoomDist + (Math.abs(targetZ) < 15 ? 110 : 0);

        fgRef.current.cameraPosition(
          { x: camX, y: camY, z: camZ },
          { x: targetX, y: targetY, z: targetZ },
          900
        );
      },
      toggleAutoRotate: (enabled: boolean) => {
        if (enabled && fgRef.current) {
          const cam = fgRef.current.camera();
          if (cam) {
            orbitAngleRef.current = Math.atan2(cam.position.x, cam.position.z);
          }
        }
        setIsAutoRotating(enabled);
      },
    }));

    // Handle node click: fly camera to focus on that node
    const handleNodeClick = useCallback(
      (node: any) => {
        setIsAutoRotating(false);
        onAutoRotateChange?.(false);
        if (!fgRef.current || !node || node.x === undefined) return;
        const distance = 90;
        const distRatio = 1 + distance / (Math.hypot(node.x, node.y, node.z) || 1);
        fgRef.current.cameraPosition(
          { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
          { x: node.x, y: node.y, z: node.z },
          900
        );
      },
      [onAutoRotateChange]
    );

    // Handle link click: open evidence modal
    const handleLinkClick = useCallback(
      (link: any) => {
        if (onSelectLink) {
          onSelectLink(link as CrossLinkData);
        }
      },
      [onSelectLink]
    );

    return (
      <div
        ref={containerRef}
        className="relative w-full h-[620px] bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 shadow-2xl"
      >
        <ForceGraph3D
          ref={fgRef as any}
          width={dimensions.width}
          height={dimensions.height}
          graphData={graphData}
          backgroundColor="#090d16"
          showNavInfo={false}
          // Nodes
          nodeColor={(node: any) => {
            const baseColor = getSubjectColor(node.subject_id);
            if (focusedSubjectId) {
              return node.subject_id === focusedSubjectId ? baseColor : "rgba(100, 116, 139, 0.25)";
            }
            return baseColor;
          }}
          nodeVal={(node: any) => {
            if (focusedSubjectId) {
              return node.subject_id === focusedSubjectId ? 8.0 : 2.8;
            }
            return 5.0;
          }}
          nodeResolution={16}
          nodeLabel={(node: any) => `
            <div style="background: rgba(15, 23, 42, 0.95); border: 1px solid rgba(148, 163, 184, 0.4); border-radius: 8px; padding: 8px 12px; font-family: sans-serif; color: #f8fafc; max-width: 260px; box-shadow: 0 4px 16px rgba(0,0,0,0.4);">
              <div style="color: ${getSubjectColor(node.subject_id)}; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em;">${node.subject_name || "Subject"}</div>
              <div style="font-size: 13px; font-weight: 700; margin: 3px 0; color: #ffffff;">${node.keyword || node.name}</div>
              <div style="font-size: 11px; color: #cbd5e1; line-height: 1.35;">${node.explanation ? node.explanation.substring(0, 95) + '...' : ''}</div>
              <div style="font-size: 10px; color: #38bdf8; margin-top: 4px;">Click node to zoom in</div>
            </div>
          `}
          onNodeClick={handleNodeClick}
          // Links: Cross-subject bridges glow bright; same-subject links are faded
          linkColor={(link: any) => {
            if (link.scope === "cross_subject") {
              if (link.strength === 5) return "#f59e0b"; // Golden Amber
              if (link.strength === 4) return "#38bdf8"; // Bright Cyan
              if (link.strength === 3) return "#a855f7"; // Purple
              return "#94a3b8"; // Slate for low strength 1-2
            }
            return fadeSameSubject ? "rgba(148, 163, 184, 0.08)" : "rgba(148, 163, 184, 0.3)";
          }}
          linkWidth={(link: any) => {
            if (link.scope === "cross_subject") {
              return Math.max(1.8, (link.strength || 3) * 0.95);
            }
            return 0.4;
          }}
          linkOpacity={0.9}
          linkDirectionalParticles={(link: any) => {
            if (link.scope === "cross_subject") {
              return Math.max(1, Math.min(5, link.strength || 3));
            }
            return 0;
          }}
          linkDirectionalParticleWidth={(link: any) =>
            link.scope === "cross_subject" ? Math.max(1.8, (link.strength || 3) * 0.65) : 0
          }
          linkDirectionalParticleSpeed={(link: any) =>
            link.scope === "cross_subject" ? 0.003 + (link.strength || 3) * 0.001 : 0
          }
          linkDirectionalParticleColor={(link: any) =>
            link.strength >= 4 ? "#fbbf24" : "#38bdf8"
          }
          onLinkClick={handleLinkClick}
          // Physics tuning
          warmupTicks={40}
          cooldownTicks={100}
        />

        {/* 3D Visual Overlay Controls Hints */}
        <div className="absolute bottom-4 left-4 pointer-events-none text-slate-400 text-xs bg-slate-950/80 backdrop-blur-xs px-3.5 py-2 rounded-xl border border-slate-800 flex items-center gap-2 shadow-lg">
          <span className="font-semibold text-slate-200">Interactive Controls: </span>
          <span>Drag left to orbit • Drag right to pan • Scroll to zoom • Click bridge line to view proof</span>
        </div>

        {/* Auto-Rotating Indicator Badge */}
        {isAutoRotating && (
          <div className="absolute top-4 left-4 pointer-events-none px-3 py-1.5 rounded-lg bg-indigo-950/85 border border-indigo-500/50 text-indigo-200 text-xs font-semibold flex items-center gap-2 shadow-lg">
            <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
            <span>Auto-Orbiting 360°... Click Pause to stop</span>
          </div>
        )}
      </div>
    );
  }
);
