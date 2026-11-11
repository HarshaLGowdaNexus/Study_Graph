import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  RotateCcw,
  Play,
  Pause,
  List,
  Box,
  Layers,
  Sparkles,
  ShieldCheck,
  Activity,
  Sliders,
  Filter,
  Eye,
  EyeOff,
  RefreshCw,
  X,
  Compass,
} from "lucide-react";
import { CrossSubjectGraph3D, CrossGraph3DHandle, getSubjectColor } from "./CrossSubjectGraph3D";
import { CrossSubjectTextList } from "./CrossSubjectTextList";
import { CrossLinkDetailModal, CrossLinkData } from "./CrossLinkDetailModal";

interface SubjectSummary {
  id: string;
  name: string;
  center?: { x: number; y: number; z: number };
}

interface CrossGraphResponse {
  scope: string;
  subjects: SubjectSummary[];
  nodes: any[];
  links: any[];
  stats: {
    node_count: number;
    link_count: number;
    cross_subject_links: number;
    same_subject_links?: number;
    is_synthetic?: boolean;
  };
}

// Isolated FPS Monitor Badge so 2Hz frame rate updates never re-render the 3D WebGL graph
const FpsBadge: React.FC = () => {
  const [fps, setFps] = useState<number>(60);

  useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let animId: number;

    const tick = (now: number) => {
      frameCount++;
      if (now - lastTime >= 500) {
        setFps(Math.round((frameCount * 1000) / (now - lastTime)));
        frameCount = 0;
        lastTime = now;
      }
      animId = requestAnimationFrame(tick);
    };
    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, []);

  return (
    <div
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-mono font-bold text-[11px] ${
        fps >= 45
          ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
          : fps >= 25
          ? "bg-amber-950/60 text-amber-300 border-amber-800/60"
          : "bg-rose-950/60 text-rose-300 border-rose-800/60"
      }`}
      title="Real-time WebGL rendering frames per second on your machine"
    >
      <Activity className="w-3.5 h-3.5" />
      <span>{fps} FPS</span>
      <span className="text-[10px] font-sans font-normal text-emerald-400 hidden sm:inline">
        (G08 ≥ 30)
      </span>
    </div>
  );
};

export const CrossSubjectGraphPage: React.FC = () => {
  const [data, setData] = useState<CrossGraphResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // View state
  const [viewMode, setViewMode] = useState<"3d" | "text">("3d");
  const [isBenchmarkMode, setIsBenchmarkMode] = useState<boolean>(false);
  const [minStrength, setMinStrength] = useState<number>(3); // Default strength >= 3 per Golden Rule & R19
  const [fadeSameSubject, setFadeSameSubject] = useState<boolean>(true); // Faded by default
  const [isAutoRotating, setIsAutoRotating] = useState<boolean>(false);
  const [focusedSubjectId, setFocusedSubjectId] = useState<string | null>(null);
  const [selectedLink, setSelectedLink] = useState<CrossLinkData | null>(null);

  const graph3DRef = useRef<CrossGraph3DHandle>(null);

  // Fetch cross-subject graph
  const fetchGraphData = async (forceBenchmark = false) => {
    setLoading(true);
    setError(null);
    setFocusedSubjectId(null);
    try {
      const url = forceBenchmark
        ? "/api/graphs/cross-subject/benchmark"
        : "/api/graphs/cross-subject?fresh=true";
      const res = await fetch(url, {
        headers: {
          "x-test-user-id": "11111111-1111-4111-8111-111111111111",
          "x-test-user-email": "alex@university.edu",
        },
      });
      if (!res.ok) {
        const benchRes = await fetch("/api/graphs/cross-subject/benchmark");
        if (benchRes.ok) {
          const benchData = await benchRes.json();
          setData(benchData);
          setIsBenchmarkMode(true);
          setLoading(false);
          return;
        }
        throw new Error(`Failed to load cross-subject graph (${res.status})`);
      }
      const json = await res.json();
      // Check if returned data is benchmark or has < 3 cross links
      const isBench = Boolean(json?.stats?.is_synthetic) || forceBenchmark;
      if (!forceBenchmark && (json?.stats?.cross_subject_links || 0) < 3) {
        const benchRes = await fetch("/api/graphs/cross-subject/benchmark");
        if (benchRes.ok) {
          const benchData = await benchRes.json();
          setData(benchData);
          setIsBenchmarkMode(true);
          setLoading(false);
          return;
        }
      }
      setData(json);
      setIsBenchmarkMode(isBench);
    } catch (err: any) {
      console.warn("Loading benchmark cross-subject data due to API notice:", err.message);
      try {
        const fallbackRes = await fetch("/api/graphs/cross-subject/benchmark");
        if (fallbackRes.ok) {
          const fallbackJson = await fallbackRes.json();
          setData(fallbackJson);
          setIsBenchmarkMode(true);
        } else {
          setError(err.message || "Failed to load cross-subject graph.");
        }
      } catch (benchErr: any) {
        setError(benchErr.message || "Failed to connect to backend.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphData(false);
  }, []);

  // Memoize nodes and subjects so filter/UI updates never mutate/reset node positions
  const memoNodes = useMemo(() => data?.nodes || [], [data]);
  const memoSubjects = useMemo(() => data?.subjects || [], [data]);

  // Filter cross-subject links by strength threshold
  const { visibleCrossLinks, sameSubjectLinks, allDisplayLinks } = useMemo(() => {
    if (!data) return { visibleCrossLinks: [], sameSubjectLinks: [], allDisplayLinks: [] };

    const cross = data.links.filter(
      (l) => l.scope === "cross_subject" && (l.strength || 3) >= minStrength
    );
    const same = data.links.filter((l) => l.scope === "same_subject");

    // Both views receive identical cross-subject link representations
    const displayLinks = fadeSameSubject ? [...cross, ...same] : cross;

    return {
      visibleCrossLinks: cross,
      sameSubjectLinks: same,
      allDisplayLinks: displayLinks,
    };
  }, [data, minStrength, fadeSameSubject]);

  // Handle subject jump
  const handleFlyToSubject = (subjectId: string) => {
    setFocusedSubjectId(subjectId);
    const subj = data?.subjects?.find((s) => s.id === subjectId);

    if (viewMode !== "3d") {
      setViewMode("3d");
      setTimeout(() => {
        graph3DRef.current?.flyToSubject(subjectId, subj?.center);
      }, 100);
    } else {
      graph3DRef.current?.flyToSubject(subjectId, subj?.center);
    }
  };

  // Clear subject focus
  const handleClearSubjectFocus = () => {
    setFocusedSubjectId(null);
    graph3DRef.current?.resetCamera();
  };

  // Toggle Auto-Rotate
  const handleToggleAutoRotate = () => {
    const nextState = !isAutoRotating;
    setIsAutoRotating(nextState);
    graph3DRef.current?.toggleAutoRotate(nextState);
  };

  // Reset Camera
  const handleResetCamera = () => {
    setFocusedSubjectId(null);
    setIsAutoRotating(false);
    graph3DRef.current?.toggleAutoRotate(false);
    graph3DRef.current?.resetCamera();
  };

  const activeSubject = data?.subjects?.find((s) => s.id === focusedSubjectId);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-6">
      {/* Top Header & Overview */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl text-white">
        <div className="space-y-1">
          <div className="flex items-center flex-wrap gap-2">
            <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 font-semibold text-xs border border-indigo-500/30 flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              Task T15 • Feature F12
            </span>
            <button
              onClick={() => fetchGraphData(!isBenchmarkMode)}
              className={`px-2.5 py-0.5 rounded-full font-medium text-[11px] border transition ${
                isBenchmarkMode
                  ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 hover:bg-cyan-500/30"
                  : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30"
              }`}
              title="Click to switch between your uploaded study notes and the 4-subject benchmark"
            >
              {isBenchmarkMode ? "4-Subject Benchmark (Switch to My Notes)" : "Live Database Notes (Switch to Benchmark)"}
            </button>
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white">
            Cross-Subject 3D Knowledge Map
          </h1>
          <p className="text-sm text-slate-400 max-w-2xl">
            Multi-subject concept galaxies in a rotatable 3D sphere. High-confidence connections (Strength ≥ {minStrength}) bridge disciplines with verbatim quotes from both sides.
          </p>
        </div>

        {/* View Switcher Tabs */}
        <div className="flex items-center gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800 self-start md:self-auto">
          <button
            onClick={() => setViewMode("3d")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
              viewMode === "3d"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Box className="w-4 h-4" />
            3D Galaxy View
          </button>
          <button
            onClick={() => setViewMode("text")}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition ${
              viewMode === "text"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <List className="w-4 h-4" />
            Synchronized Text List
          </button>
        </div>
      </div>

      {/* Interactive Controls & Filters Bar */}
      <div className="p-4 bg-slate-900/90 border border-slate-800 rounded-xl space-y-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Subject Jump Constellations */}
          <div className="flex items-center flex-wrap gap-2">
            <span className="text-slate-400 font-semibold mr-1 flex items-center gap-1">
              <Compass className="w-3.5 h-3.5 text-indigo-400" />
              Fly to Subject:
            </span>
            {data?.subjects?.map((subj) => {
              const color = getSubjectColor(subj.id);
              const isSelected = focusedSubjectId === subj.id;
              return (
                <button
                  key={subj.id}
                  onClick={() => handleFlyToSubject(subj.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition font-medium ${
                    isSelected
                      ? "bg-indigo-950/90 border-indigo-500 text-white shadow-[0_0_12px_rgba(99,102,241,0.4)] ring-1 ring-indigo-400"
                      : "bg-slate-950 hover:bg-slate-800 border-slate-800 text-slate-300 hover:text-white"
                  }`}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full transition-transform duration-200"
                    style={{
                      backgroundColor: color,
                      boxShadow: isSelected ? `0 0 10px ${color}` : `0 0 5px ${color}`,
                      transform: isSelected ? "scale(1.25)" : "scale(1)",
                    }}
                  />
                  <span>{subj.name}</span>
                  {isSelected && <span className="ml-1 text-[10px] text-indigo-300 font-bold">● Focused</span>}
                </button>
              );
            })}
          </div>

          {/* Strength Filter and FPS Monitor */}
          <div className="flex items-center flex-wrap gap-3">
            {/* Minimum Strength Interactive Slider & Buttons */}
            <div className="flex items-center gap-2.5 bg-slate-950 px-3.5 py-1.5 rounded-lg border border-slate-800 text-slate-300">
              <Sliders className="w-3.5 h-3.5 text-amber-400" />
              <span className="font-semibold text-slate-300">Strength:</span>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={minStrength}
                onChange={(e) => setMinStrength(Number(e.target.value))}
                className="w-20 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
                title={`Slider: ${minStrength}+`}
              />
              <div className="flex items-center gap-1 font-bold">
                {[1, 2, 3, 4, 5].map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setMinStrength(lvl)}
                    className={`w-5 h-5 rounded text-[11px] flex items-center justify-center transition ${
                      minStrength === lvl
                        ? "bg-amber-500 text-slate-950 font-black shadow-md shadow-amber-500/40"
                        : "text-slate-400 hover:text-white hover:bg-slate-800"
                    }`}
                    title={`Filter strength >= ${lvl}`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
              <span className="px-2 py-0.5 rounded font-black text-amber-400 bg-amber-500/10 border border-amber-500/30 text-[11px]">
                {visibleCrossLinks.length} bridges
              </span>
            </div>

            {/* Same-Subject Fading Toggle */}
            {viewMode === "3d" && (
              <button
                onClick={() => setFadeSameSubject(!fadeSameSubject)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition ${
                  fadeSameSubject
                    ? "bg-indigo-950/60 text-indigo-300 border-indigo-800/80"
                    : "bg-slate-950 text-slate-400 border-slate-800 hover:text-white"
                }`}
                title="Toggle fading of links within the same subject"
              >
                {fadeSameSubject ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                <span>{fadeSameSubject ? "Same-Subject Faded" : "Same-Subject Visible"}</span>
              </button>
            )}

            {/* 3D Camera Controls */}
            {viewMode === "3d" && (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={handleResetCamera}
                  className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-white rounded-lg border border-slate-800 transition"
                  title="Reset Camera to Home Position"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Reset Orbit</span>
                </button>
                <button
                  onClick={handleToggleAutoRotate}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition font-medium ${
                    isAutoRotating
                      ? "bg-indigo-600 text-white border-indigo-500 shadow-md shadow-indigo-600/30"
                      : "bg-slate-950 hover:bg-slate-800 text-slate-300 border-slate-800"
                  }`}
                  title="Toggle continuous 360-degree automatic camera rotation"
                >
                  {isAutoRotating ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 text-indigo-400" />}
                  <span>{isAutoRotating ? "Pause Orbit" : "Auto-Orbit 360°"}</span>
                </button>
              </div>
            )}

            {/* Live Machine FPS Counter (Quality Gate G08) */}
            <FpsBadge />
          </div>
        </div>

        {/* Active Subject Focus Banner */}
        {focusedSubjectId && activeSubject && (
          <div className="flex items-center justify-between p-2.5 bg-indigo-950/40 border border-indigo-500/40 rounded-lg text-indigo-200 animate-in fade-in duration-150">
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{
                  backgroundColor: getSubjectColor(focusedSubjectId),
                  boxShadow: `0 0 8px ${getSubjectColor(focusedSubjectId)}`,
                }}
              />
              <span className="font-semibold text-white">Focused Galaxy: {activeSubject.name}</span>
              <span className="text-slate-400 text-[11px]">
                (Camera zoomed into this subject's neighborhood; other galaxies dimmed)
              </span>
            </div>
            <button
              onClick={handleClearSubjectFocus}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-indigo-400/40 text-xs font-semibold text-indigo-300 hover:text-white transition"
            >
              <X className="w-3 h-3" />
              Reset & Show All Subjects
            </button>
          </div>
        )}
      </div>

      {/* Main Display Area */}
      {loading ? (
        <div className="h-[550px] flex flex-col items-center justify-center bg-slate-950 rounded-2xl border border-slate-800 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-500 mb-3" />
          <p className="text-sm font-medium">Assembling multi-subject 3D knowledge map...</p>
        </div>
      ) : error ? (
        <div className="p-8 bg-rose-950/30 border border-rose-800/60 rounded-2xl text-center space-y-3">
          <p className="text-rose-300 font-semibold">{error}</p>
          <button
            onClick={() => fetchGraphData(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold"
          >
            Load Multi-Subject Benchmark Graph
          </button>
        </div>
      ) : viewMode === "3d" ? (
        <div className="space-y-3">
          <CrossSubjectGraph3D
            ref={graph3DRef}
            nodes={memoNodes}
            links={allDisplayLinks}
            subjects={memoSubjects}
            focusedSubjectId={focusedSubjectId}
            onSelectLink={(link) => setSelectedLink(link)}
            onAutoRotateChange={(rotating) => setIsAutoRotating(rotating)}
            fadeSameSubject={fadeSameSubject}
          />
          {/* Parity Footer Callout */}
          <div className="flex items-center justify-between text-xs text-slate-400 px-2">
            <span>
              Showing <strong className="text-amber-400 font-bold">{visibleCrossLinks.length}</strong> glowing cross-subject bridges (Strength ≥ {minStrength})
              {fadeSameSubject && ` and ${sameSubjectLinks.length} faded internal links`}
            </span>
            <button
              onClick={() => setViewMode("text")}
              className="text-indigo-400 hover:text-indigo-300 font-medium underline"
            >
              View matching text list ({visibleCrossLinks.length} items) →
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <CrossSubjectTextList
            links={visibleCrossLinks}
            onSelectLink={(link) => setSelectedLink(link)}
            minStrength={minStrength}
          />
        </div>
      )}

      {/* Detail Modal for Clicked Links */}
      <CrossLinkDetailModal
        link={selectedLink}
        onClose={() => setSelectedLink(null)}
      />
    </div>
  );
};
