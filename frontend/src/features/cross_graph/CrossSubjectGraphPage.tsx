import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  RotateCcw,
  Play,
  Pause,
  List,
  Box,
  Layers,
  Sparkles,
  Activity,
  Sliders,
  Eye,
  EyeOff,
  RefreshCw,
  X,
  Compass,
  Gauge,
  AlertTriangle,
  Crosshair,
  BookOpen,
} from "lucide-react";
import { CrossSubjectGraph3D, CrossGraph3DHandle, getSubjectColor } from "./CrossSubjectGraph3D";
import { CrossSubjectGraph2D, CrossGraph2DHandle } from "./CrossSubjectGraph2D";
import { CrossSubjectTextList } from "./CrossSubjectTextList";
import { CrossLinkDetailModal, CrossLinkData } from "./CrossLinkDetailModal";
import { TopicSearchBar } from "../graph/TopicSearchBar";
import { NodeDetailPanel, GraphNodeData, ConnectedConceptChip } from "../graph/NodeDetailPanel";
import { useFpsMonitor } from "../graph/useFpsMonitor";
import {
  DEFAULT_GRAPH_CONFIG,
  GraphRuntimeConfig,
  fetchGraphRuntimeConfig,
} from "../../config/graphConfig";
import {
  SearchTopicSuggestion,
  extractKHopSubgraph,
  getEndpointId,
} from "../graph/focusSearchUtils";

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
    hidden_weak_count?: number;
  };
}

interface FallbackNoticeState {
  measuredFps: number;
  threshold: number;
}

const DEFAULT_AUTH_HEADERS = {
  "x-test-user-id": "11111111-1111-4111-8111-111111111111",
  "x-test-user-email": "alex@university.edu",
};

export const CrossSubjectGraphPage: React.FC = () => {
  const [runtimeConfig, setRuntimeConfig] = useState<GraphRuntimeConfig>(DEFAULT_GRAPH_CONFIG);
  const [data, setData] = useState<CrossGraphResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // View & performance state
  const [viewMode, setViewMode] = useState<"3d" | "2d" | "text">("3d");
  const [isBenchmarkMode, setIsBenchmarkMode] = useState<boolean>(false);
  const [minStrength, setMinStrength] = useState<number>(3); // Default strength >= 3 per Golden Rule & R19
  const [fadeSameSubject, setFadeSameSubject] = useState<boolean>(true);
  const [isAutoRotating, setIsAutoRotating] = useState<boolean>(false);
  const [nodeCap, setNodeCap] = useState<number>(DEFAULT_GRAPH_CONFIG.maxVisibleNodes);
  const [fallbackNotice, setFallbackNotice] = useState<FallbackNoticeState | null>(null);
  const [retry3DUntil, setRetry3DUntil] = useState<number>(0);

  // Focus search & Theory Card state (lives above 3D/2D renderers so fallback never loses place)
  const [focusedSubjectId, setFocusedSubjectId] = useState<string | null>(null);
  const [focusedTopicMeta, setFocusedTopicMeta] = useState<{
    id: string;
    keyword: string;
    matchedAlias?: string | null;
    source: "database" | "local";
  } | null>(null);
  const [hopCount, setHopCount] = useState<number>(DEFAULT_GRAPH_CONFIG.defaultSearchHops);
  const [focusedDbGraph, setFocusedDbGraph] = useState<CrossGraphResponse | null>(null);
  const [focusLoading, setFocusLoading] = useState<boolean>(false);

  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedLink, setSelectedLink] = useState<CrossLinkData | null>(null);

  const graph3DRef = useRef<CrossGraph3DHandle>(null);
  const graph2DRef = useRef<CrossGraph2DHandle>(null);

  // Load central backend graph config (FPS limit & hop defaults) on mount
  useEffect(() => {
    fetchGraphRuntimeConfig().then((cfg) => {
      setRuntimeConfig(cfg);
      setHopCount(cfg.defaultSearchHops);
      setNodeCap(cfg.maxVisibleNodes);
    });
  }, []);

  // Real-time FPS monitor with automatic 3D -> 2D fallback (Feature F15, Risk R14)
  const handleAutoFallback = useCallback(
    (measuredFps: number) => {
      setIsAutoRotating(false);
      setViewMode((prev) => (prev === "3d" ? "2d" : prev));
      setFallbackNotice({
        measuredFps,
        threshold: runtimeConfig.fpsFallbackThreshold,
      });
    },
    [runtimeConfig.fpsFallbackThreshold]
  );

  const { fps, triggerSimulatedLowFps } = useFpsMonitor({
    enabled: viewMode === "3d" && !loading && !error,
    threshold: runtimeConfig.fpsFallbackThreshold,
    streakRequired: runtimeConfig.fpsLowStreakCount,
    sampleWindowMs: runtimeConfig.fpsSampleWindowMs,
    cooldownUntil: retry3DUntil,
    onFallbackTriggered: handleAutoFallback,
  });

  // Fetch cross-subject graph
  const fetchGraphData = async (forceBenchmark = false) => {
    setLoading(true);
    setError(null);
    setFocusedSubjectId(null);
    try {
      const url = forceBenchmark
        ? "/api/graphs/cross-subject/benchmark"
        : "/api/graphs/cross-subject?fresh=true";
      const res = await fetch(url, { headers: DEFAULT_AUTH_HEADERS });
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

  // Load focused 2-3 hop neighborhood from database for real topics
  const loadFocusedDbGraph = useCallback(
    async (topicId: string, hops: number, strengthFloor: number, cap: number) => {
      setFocusLoading(true);
      try {
        const includeWeak = strengthFloor < runtimeConfig.weakLinkThreshold;
        const params = new URLSearchParams({
          hops: String(hops),
          include_weak: String(includeWeak),
          max_nodes: String(cap),
        });
        const res = await fetch(`/api/graphs/focus/${topicId}?${params.toString()}`, {
          headers: DEFAULT_AUTH_HEADERS,
        });
        if (!res.ok) {
          throw new Error("Could not load focused neighborhood for this topic.");
        }
        const focusedJson = await res.json();
        setFocusedDbGraph(focusedJson);
        if (focusedJson.focus_topic) {
          setSelectedNode(focusedJson.focus_topic as GraphNodeData);
        }
      } catch (err: any) {
        setError(err.message || "Failed to load focused topic graph.");
      } finally {
        setFocusLoading(false);
      }
    },
    [runtimeConfig.weakLinkThreshold]
  );

  // Handle selecting a topic from search suggestions (supports keywords + aliases)
  const handleSelectSearchTopic = useCallback(
    async (suggestion: SearchTopicSuggestion) => {
      setFocusedSubjectId(null);
      setSelectedLink(null);
      setFocusedTopicMeta({
        id: suggestion.id,
        keyword: suggestion.keyword,
        matchedAlias: suggestion.matched_alias,
        source: suggestion.source === "local" ? "local" : "database",
      });

      if (suggestion.source === "local") {
        setFocusedDbGraph(null);
        const foundNode = data?.nodes?.find((n) => n.id === suggestion.id);
        setSelectedNode(
          (foundNode as GraphNodeData) || {
            id: suggestion.id,
            name: suggestion.keyword,
            keyword: suggestion.keyword,
            aliases: suggestion.aliases,
            explanation: suggestion.explanation,
            real_world_use: suggestion.real_world_use,
            module_no: suggestion.module_no,
            reviewed: suggestion.reviewed,
            subject_id: suggestion.subject_id,
            subject_name: suggestion.subject_name,
            hop_distance: 0,
            is_focus: true,
          }
        );
      } else {
        await loadFocusedDbGraph(suggestion.id, hopCount, minStrength, nodeCap);
      }

      if (viewMode === "2d") {
        setTimeout(() => graph2DRef.current?.focusNode(suggestion.id), 200);
      }
    },
    [data?.nodes, hopCount, minStrength, nodeCap, loadFocusedDbGraph, viewMode]
  );

  // Re-fetch or re-slice when hop count changes while focused
  const handleChangeHops = (nextHops: number) => {
    setHopCount(nextHops);
    if (focusedTopicMeta && focusedTopicMeta.source === "database") {
      loadFocusedDbGraph(focusedTopicMeta.id, nextHops, minStrength, nodeCap);
    }
  };

  // Clear topic focus and return to full graph
  const handleClearTopicFocus = () => {
    setFocusedTopicMeta(null);
    setFocusedDbGraph(null);
    setSelectedNode(null);
    if (viewMode === "3d") {
      graph3DRef.current?.resetCamera();
    } else if (viewMode === "2d") {
      graph2DRef.current?.resetView();
    }
  };

  // Jump focus to a connected concept clicked inside the Theory Card
  const handleFocusConnectedTopic = (topicId: string) => {
    const activeNodes = focusedDbGraph?.nodes || data?.nodes || [];
    const targetNode = activeNodes.find((n) => n.id === topicId);
    const sourceMode = focusedTopicMeta?.source || (isBenchmarkMode ? "local" : "database");
    handleSelectSearchTopic({
      id: topicId,
      subject_id: targetNode?.subject_id || "",
      subject_name: targetNode?.subject_name || "Subject",
      keyword: targetNode?.keyword || targetNode?.name || "Topic",
      aliases: targetNode?.aliases || [],
      explanation: targetNode?.explanation || "",
      real_world_use: targetNode?.real_world_use || "",
      module_no: targetNode?.module_no || 1,
      reviewed: Boolean(targetNode?.reviewed),
      cluster_label: targetNode?.cluster_label,
      source: sourceMode,
    });
  };

  // Compute displayed nodes & links (either focused 2-3 hop subgraph or capped full graph)
  const {
    memoNodes,
    memoSubjects,
    visibleCrossLinks,
    sameSubjectLinks,
    allDisplayLinks,
    totalAvailableNodes,
  } = useMemo(() => {
    // Case 1: Database-backed focused topic view
    if (focusedTopicMeta?.source === "database" && focusedDbGraph) {
      const filteredLinks = focusedDbGraph.links.filter(
        (l) => (l.strength || 1) >= minStrength
      );
      const cross = filteredLinks.filter((l) => l.scope === "cross_subject");
      const same = filteredLinks.filter((l) => l.scope !== "cross_subject");
      return {
        memoNodes: focusedDbGraph.nodes,
        memoSubjects: focusedDbGraph.subjects || [],
        visibleCrossLinks: cross,
        sameSubjectLinks: same,
        allDisplayLinks: filteredLinks,
        totalAvailableNodes: focusedDbGraph.nodes.length,
      };
    }

    // Case 2: Local / benchmark focused topic view
    if (focusedTopicMeta?.source === "local" && data) {
      const localSub = extractKHopSubgraph(
        data.nodes,
        data.links,
        focusedTopicMeta.id,
        hopCount,
        {
          includeWeak: minStrength < runtimeConfig.weakLinkThreshold,
          weakThreshold: runtimeConfig.weakLinkThreshold,
          maxNodes: nodeCap,
          minHops: runtimeConfig.minSearchHops,
          maxHops: runtimeConfig.maxSearchHops,
        }
      );
      const filteredLinks = localSub.links.filter((l) => (l.strength || 1) >= minStrength);
      const cross = filteredLinks.filter((l) => l.scope === "cross_subject");
      const same = filteredLinks.filter((l) => l.scope !== "cross_subject");
      const subjectSet = new Map<string, SubjectSummary>();
      for (const n of localSub.nodes) {
        if (n.subject_id && !subjectSet.has(n.subject_id)) {
          subjectSet.set(n.subject_id, { id: n.subject_id, name: n.subject_name || "Subject" });
        }
      }
      return {
        memoNodes: localSub.nodes,
        memoSubjects: Array.from(subjectSet.values()),
        visibleCrossLinks: cross,
        sameSubjectLinks: same,
        allDisplayLinks: filteredLinks,
        totalAvailableNodes: data.nodes.length,
      };
    }

    // Case 3: Full graph (capped by nodeCap per Risk R14 & Feature F15)
    if (!data) {
      return {
        memoNodes: [],
        memoSubjects: [],
        visibleCrossLinks: [],
        sameSubjectLinks: [],
        allDisplayLinks: [],
        totalAvailableNodes: 0,
      };
    }

    let nodes = data.nodes;
    let links = data.links;
    const totalCount = nodes.length;

    if (nodes.length > nodeCap) {
      const degreeMap: Record<string, number> = {};
      links.forEach((l) => {
        const s = getEndpointId(l.source);
        const t = getEndpointId(l.target);
        degreeMap[s] = (degreeMap[s] || 0) + 1;
        degreeMap[t] = (degreeMap[t] || 0) + 1;
      });
      nodes = [...nodes]
        .sort((a, b) => (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0))
        .slice(0, nodeCap);
      const activeIds = new Set(nodes.map((n) => n.id));
      links = links.filter(
        (l) => activeIds.has(getEndpointId(l.source)) && activeIds.has(getEndpointId(l.target))
      );
    }

    const cross = links.filter(
      (l) => l.scope === "cross_subject" && (l.strength || 3) >= minStrength
    );
    const same = links.filter((l) => l.scope === "same_subject");
    const displayLinks = fadeSameSubject ? [...cross, ...same] : cross;

    return {
      memoNodes: nodes,
      memoSubjects: data.subjects || [],
      visibleCrossLinks: cross,
      sameSubjectLinks: same,
      allDisplayLinks: displayLinks,
      totalAvailableNodes: totalCount,
    };
  }, [
    data,
    focusedTopicMeta,
    focusedDbGraph,
    hopCount,
    minStrength,
    fadeSameSubject,
    nodeCap,
    runtimeConfig,
  ]);

  // Connected concept chips for the open Theory Card
  const selectedNodeConnectedChips: ConnectedConceptChip[] = useMemo(() => {
    if (!selectedNode) return [];
    const nodeLookup = new Map<string, any>();
    for (const n of memoNodes) nodeLookup.set(n.id, n);

    const chips: ConnectedConceptChip[] = [];
    for (const l of allDisplayLinks) {
      const srcId = getEndpointId(l.source);
      const tgtId = getEndpointId(l.target);
      if (srcId === selectedNode.id) {
        const other = nodeLookup.get(tgtId);
        chips.push({
          edgeId: l.id,
          targetTopicId: tgtId,
          targetKeyword: l.target_keyword || other?.keyword || tgtId,
          type: l.type || "related",
          strength: l.strength || 3,
        });
      } else if (tgtId === selectedNode.id) {
        const other = nodeLookup.get(srcId);
        chips.push({
          edgeId: l.id,
          targetTopicId: srcId,
          targetKeyword: l.source_keyword || other?.keyword || srcId,
          type: l.type || "related",
          strength: l.strength || 3,
        });
      }
    }
    return chips;
  }, [selectedNode, memoNodes, allDisplayLinks]);

  // Handle manual mode switch
  const handleSetViewMode = (mode: "3d" | "2d" | "text") => {
    if (mode === "3d") {
      setRetry3DUntil(Date.now() + runtimeConfig.retry3DCooldownMs);
      setFallbackNotice(null);
    } else {
      setIsAutoRotating(false);
      graph3DRef.current?.toggleAutoRotate(false);
    }
    setViewMode(mode);
  };

  // Handle subject jump
  const handleFlyToSubject = (subjectId: string) => {
    setFocusedSubjectId(subjectId);
    const subj = data?.subjects?.find((s) => s.id === subjectId);

    if (viewMode === "text") {
      setViewMode("3d");
      setTimeout(() => {
        graph3DRef.current?.flyToSubject(subjectId, subj?.center);
      }, 100);
    } else if (viewMode === "3d") {
      graph3DRef.current?.flyToSubject(subjectId, subj?.center);
    } else {
      graph2DRef.current?.resetView();
    }
  };

  // Clear subject focus
  const handleClearSubjectFocus = () => {
    setFocusedSubjectId(null);
    if (viewMode === "3d") {
      graph3DRef.current?.resetCamera();
    } else if (viewMode === "2d") {
      graph2DRef.current?.resetView();
    }
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
    if (viewMode === "3d") {
      graph3DRef.current?.resetCamera();
    } else if (viewMode === "2d") {
      graph2DRef.current?.resetView();
    }
  };

  const activeSubject = data?.subjects?.find((s) => s.id === focusedSubjectId);
  const isFocusedMode = Boolean(focusedTopicMeta);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-5">
      {/* Top Header & Overview */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-5 sm:p-6 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl text-white">
        <div className="space-y-1">
          <div className="flex items-center flex-wrap gap-2">
            <span className="px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 font-semibold text-xs border border-indigo-500/30 flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              Tasks T15 & T16 • Features F12, F13, F15
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
          <h1 className="text-xl sm:text-2xl font-black tracking-tight text-white">
            Cross-Subject Knowledge Explorer
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 max-w-2xl">
            Search any topic or alias for a focused 2–3 hop map & Theory Card, or explore all subjects in 3D with automatic 2D protection on slower devices.
          </p>
        </div>

        {/* View Switcher Tabs (3D / 2D Focus Mode / Text List) */}
        <div className="flex items-center flex-wrap gap-1.5 bg-slate-950 p-1.5 rounded-xl border border-slate-800 self-start lg:self-auto">
          <button
            onClick={() => handleSetViewMode("3d")}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
              viewMode === "3d"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <Box className="w-4 h-4" />
            3D Galaxy
          </button>
          <button
            onClick={() => handleSetViewMode("2d")}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
              viewMode === "2d"
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/30"
                : "text-slate-400 hover:text-white"
            }`}
            title="Switch to lightweight 2D Canvas mode (great for weak laptops and phones)"
          >
            <Layers className="w-4 h-4" />
            2D Mode
          </button>
          <button
            onClick={() => handleSetViewMode("text")}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
              viewMode === "text"
                ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                : "text-slate-400 hover:text-white"
            }`}
          >
            <List className="w-4 h-4" />
            Text List
          </button>
        </div>
      </div>

      {/* Automatic 2D Performance Fallback Notice */}
      {fallbackNotice && (
        <div
          role="status"
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 bg-amber-950/70 border border-amber-500/50 rounded-xl text-amber-100 shadow-lg"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-0.5 text-xs sm:text-sm">
              <div className="font-bold text-amber-200">
                Switched to 2D Focus Mode for smooth speed
              </div>
              <p className="text-amber-100/90 text-xs">
                Frame rate dropped to <strong>{fallbackNotice.measuredFps} FPS</strong> (below your{" "}
                <strong>{fallbackNotice.threshold} FPS</strong> config limit), so 2D mode took over automatically.
                {focusedTopicMeta
                  ? ` "${focusedTopicMeta.keyword}" and your Theory Card stayed right where you left them.`
                  : " Your current view and filters were preserved."}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => handleSetViewMode("3d")}
              className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition"
            >
              Try 3D Again
            </button>
            <button
              onClick={() => setFallbackNotice(null)}
              className="p-1.5 rounded-lg text-amber-300 hover:text-white hover:bg-amber-900/50 transition"
              title="Dismiss notice"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Topic Search + Interactive Controls Bar */}
      <div className="p-4 bg-slate-900/90 border border-slate-800 rounded-xl space-y-3.5 text-xs">
        {/* Topic Search with Alias Autocomplete (Feature F13) */}
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          <div className="flex-1">
            <TopicSearchBar
              localNodes={data?.nodes || []}
              authHeaders={DEFAULT_AUTH_HEADERS}
              onSelectTopic={handleSelectSearchTopic}
              onClearFocus={handleClearTopicFocus}
              activeFocusKeyword={focusedTopicMeta?.keyword}
              variant="dark"
            />
          </div>

          {/* Node Cap Control (Risk R14, Feature F15) */}
          <div className="flex items-center justify-between sm:justify-start gap-2 bg-slate-950 px-3 py-2 rounded-xl border border-slate-800 text-slate-300 shrink-0">
            <span className="text-slate-400 font-semibold">Node Cap:</span>
            <select
              value={nodeCap}
              onChange={(e) => setNodeCap(Number(e.target.value))}
              className="bg-transparent text-xs font-bold text-white focus:outline-none cursor-pointer"
              title="Maximum visible nodes rendered at once (config default protects weak devices)"
            >
              <option value={50} className="bg-slate-900">50</option>
              <option value={100} className="bg-slate-900">100</option>
              <option value={150} className="bg-slate-900">150 (Default)</option>
              <option value={300} className="bg-slate-900">300 (G08 Test)</option>
              <option value={500} className="bg-slate-900">500</option>
            </select>
          </div>
        </div>

        {/* Active Topic Focus Banner (2-3 Hops + Theory Card toggle) */}
        {focusedTopicMeta && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 bg-indigo-950/60 border border-indigo-500/50 rounded-xl text-indigo-100">
            <div className="flex items-center flex-wrap gap-2">
              <Crosshair className="w-4 h-4 text-amber-400 shrink-0" />
              <span className="font-bold text-white">
                Focused ({hopCount}-Hop Local Map): {focusedTopicMeta.keyword}
              </span>
              {focusedTopicMeta.matchedAlias && (
                <span className="px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-400/40 text-amber-300 text-[11px] font-semibold">
                  via alias "{focusedTopicMeta.matchedAlias}"
                </span>
              )}
              <span className="text-indigo-300 text-[11px]">
                ({memoNodes.length} topics, {allDisplayLinks.length} links)
              </span>
            </div>

            <div className="flex items-center flex-wrap gap-2">
              <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-700">
                {[2, 3].map((h) => (
                  <button
                    key={h}
                    onClick={() => handleChangeHops(h)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition ${
                      hopCount === h
                        ? "bg-indigo-600 text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {h} Hops
                  </button>
                ))}
              </div>

              <button
                onClick={() => {
                  const node = memoNodes.find((n) => n.id === focusedTopicMeta.id);
                  if (node) setSelectedNode(node as GraphNodeData);
                }}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-indigo-400/40 text-xs font-semibold text-indigo-200 transition"
              >
                <BookOpen className="w-3.5 h-3.5 text-amber-400" />
                Theory Card
              </button>

              <button
                onClick={handleClearTopicFocus}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700 text-xs font-semibold text-slate-300 hover:text-white transition"
              >
                <X className="w-3.5 h-3.5" />
                Exit Focus
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Subject Jump Constellations */}
          {!isFocusedMode && (
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
          )}

          {/* Strength Filter and FPS Monitor */}
          <div className="flex items-center flex-wrap gap-2.5 ml-auto">
            {/* Minimum Strength Interactive Slider & Buttons */}
            <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300">
              <Sliders className="w-3.5 h-3.5 text-amber-400" />
              <span className="font-semibold text-slate-300">Strength:</span>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={minStrength}
                onChange={(e) => setMinStrength(Number(e.target.value))}
                className="w-16 sm:w-20 h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-amber-500"
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
            {viewMode !== "text" && !isFocusedMode && (
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
                  <span>Reset</span>
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
                  <span>{isAutoRotating ? "Pause" : "Auto-Orbit"}</span>
                </button>
              </div>
            )}

            {/* 2D Camera Controls */}
            {viewMode === "2d" && (
              <button
                onClick={handleResetCamera}
                className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-950 hover:bg-slate-800 text-slate-300 hover:text-white rounded-lg border border-slate-800 transition"
                title="Fit 2D graph to screen"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Fit 2D</span>
              </button>
            )}

            {/* Live Machine FPS Counter + Low-FPS Test Trigger (Quality Gate G08) */}
            <div className="flex items-center gap-1.5">
              <div
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border font-mono font-bold text-[11px] ${
                  fps >= 45
                    ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
                    : fps >= runtimeConfig.fpsFallbackThreshold
                    ? "bg-amber-950/60 text-amber-300 border-amber-800/60"
                    : "bg-rose-950/60 text-rose-300 border-rose-800/60"
                }`}
                title={`Live FPS monitor (auto-switches 3D -> 2D if sustained below ${runtimeConfig.fpsFallbackThreshold} FPS)`}
              >
                <Activity className="w-3.5 h-3.5" />
                <span>{fps} FPS</span>
                <span className="text-[10px] font-sans font-normal text-slate-400 hidden sm:inline">
                  (Min {runtimeConfig.fpsFallbackThreshold})
                </span>
              </div>

              {viewMode === "3d" && (
                <button
                  onClick={() => triggerSimulatedLowFps(Math.max(8, runtimeConfig.fpsFallbackThreshold - 10))}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-950 hover:bg-amber-950/70 border border-slate-800 hover:border-amber-600/60 text-amber-300 text-[11px] font-semibold transition"
                  title="Test low-FPS fallback behavior on a fast computer"
                >
                  <Gauge className="w-3.5 h-3.5" />
                  <span>Simulate Low FPS (Test)</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Active Subject Focus Banner */}
        {!isFocusedMode && focusedSubjectId && activeSubject && (
          <div className="flex items-center justify-between p-2.5 bg-indigo-950/40 border border-indigo-500/40 rounded-lg text-indigo-200">
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{
                  backgroundColor: getSubjectColor(focusedSubjectId),
                  boxShadow: `0 0 8px ${getSubjectColor(focusedSubjectId)}`,
                }}
              />
              <span className="font-semibold text-white">Focused Galaxy: {activeSubject.name}</span>
              <span className="text-slate-400 text-[11px] hidden sm:inline">
                (Camera zoomed into this subject's neighborhood; other galaxies dimmed)
              </span>
            </div>
            <button
              onClick={handleClearSubjectFocus}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-indigo-400/40 text-xs font-semibold text-indigo-300 hover:text-white transition"
            >
              <X className="w-3 h-3" />
              Show All
            </button>
          </div>
        )}
      </div>

      {/* Main Display Area */}
      {loading || focusLoading ? (
        <div className="h-[540px] flex flex-col items-center justify-center bg-slate-950 rounded-2xl border border-slate-800 text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin text-indigo-500 mb-3" />
          <p className="text-sm font-medium">
            {focusLoading ? "Loading focused 2–3 hop neighborhood..." : "Assembling multi-subject knowledge map..."}
          </p>
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
            fadeSameSubject={isFocusedMode ? false : fadeSameSubject}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 px-2">
            <span>
              Showing <strong className="text-white">{memoNodes.length}</strong>
              {totalAvailableNodes > memoNodes.length && ` of ${totalAvailableNodes}`} topics &amp;{" "}
              <strong className="text-amber-400 font-bold">{visibleCrossLinks.length}</strong> cross-subject bridges (Strength ≥ {minStrength})
              {(isFocusedMode || !fadeSameSubject) && sameSubjectLinks.length > 0 && ` + ${sameSubjectLinks.length} same-subject links`}
            </span>
            <button
              onClick={() => handleSetViewMode("text")}
              className="text-indigo-400 hover:text-indigo-300 font-medium underline"
            >
              View matching text list ({visibleCrossLinks.length} items) →
            </button>
          </div>
        </div>
      ) : viewMode === "2d" ? (
        <div className="space-y-3">
          <CrossSubjectGraph2D
            ref={graph2DRef}
            nodes={memoNodes}
            links={allDisplayLinks}
            focusedSubjectId={focusedSubjectId}
            focusedTopicId={focusedTopicMeta?.id || null}
            selectedNodeId={selectedNode?.id || null}
            onSelectNode={(node) => setSelectedNode(node)}
            onSelectLink={(link) => setSelectedLink(link)}
            fadeSameSubject={isFocusedMode ? false : fadeSameSubject}
          />
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 px-2">
            <span>
              2D Focus Mode: <strong className="text-emerald-400">{memoNodes.length}</strong> topics &amp;{" "}
              <strong className="text-amber-400 font-bold">{allDisplayLinks.length}</strong> visible links (Strength ≥ {minStrength})
            </span>
            <button
              onClick={() => handleSetViewMode("text")}
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

      {/* Theory Card Side Panel (stays open across 3D <-> 2D mode switches) */}
      <NodeDetailPanel
        node={selectedNode}
        onClose={() => setSelectedNode(null)}
        connectedEdgeCount={selectedNodeConnectedChips.length}
        connectedLinks={selectedNodeConnectedChips}
        onFocusTopic={handleFocusConnectedTopic}
      />

      {/* Detail Modal for Clicked Links */}
      <CrossLinkDetailModal
        link={selectedLink}
        onClose={() => setSelectedLink(null)}
      />
    </div>
  );
};
