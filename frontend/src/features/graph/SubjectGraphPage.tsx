import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  Network,
  Layers,
  Eye,
  EyeOff,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Zap,
  AlertCircle,
  Folder,
  Sliders,
  CheckCircle2,
  Crosshair,
  X,
  BookOpen,
} from "lucide-react";
import { GraphCanvas, GraphCanvasHandle } from "./GraphCanvas";
import { NodeDetailPanel, GraphNodeData, ConnectedConceptChip } from "./NodeDetailPanel";
import { LinkDetailPanel, GraphLinkData } from "./LinkDetailPanel";
import { TopicSearchBar } from "./TopicSearchBar";
import {
  DEFAULT_GRAPH_CONFIG,
  GraphRuntimeConfig,
  fetchGraphRuntimeConfig,
} from "../../config/graphConfig";
import {
  SearchTopicSuggestion,
  extractKHopSubgraph,
  getEndpointId,
} from "./focusSearchUtils";

interface SubjectItem {
  id: string;
  name: string;
}

interface ClusterItem {
  id: string;
  label: string;
  sub_clusters?: { id: string; label: string }[];
}

interface GraphResponse {
  subject_id: string;
  subject_name: string;
  source_preference?: "notes" | "textbook";
  nodes: GraphNodeData[];
  links: GraphLinkData[];
  clusters: ClusterItem[];
  stats: {
    node_count: number;
    real_node_count?: number;
    link_count: number;
    cluster_count: number;
    is_synthetic?: boolean;
    total_available_nodes?: number;
  };
}

const DEMO_USERS = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Alex Chen (Student A)", email: "alex@university.edu" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Jordan Taylor (Student B)", email: "jordan@university.edu" },
];

export const SubjectGraphPage: React.FC = () => {
  const [activeUser, setActiveUser] = useState(DEMO_USERS[0]);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // View & Filter Controls
  const [runtimeConfig, setRuntimeConfig] = useState<GraphRuntimeConfig>(DEFAULT_GRAPH_CONFIG);
  const [isStressTestMode, setIsStressTestMode] = useState(false);
  const [selectedClusterId, setSelectedClusterId] = useState<string>("all");
  const [showWeakLinks, setShowWeakLinks] = useState(false); // Default: weak links hidden (Rule 13.8)
  const [nodeCap, setNodeCap] = useState<number>(DEFAULT_GRAPH_CONFIG.maxVisibleNodes);

  // Topic search & 2-3 hop focus state (Task T16, Feature F13)
  const [focusedTopicMeta, setFocusedTopicMeta] = useState<{
    id: string;
    keyword: string;
    matchedAlias?: string | null;
    source: "database" | "local";
  } | null>(null);
  const [hopCount, setHopCount] = useState<number>(DEFAULT_GRAPH_CONFIG.defaultSearchHops);
  const [focusedDbGraph, setFocusedDbGraph] = useState<{
    nodes: GraphNodeData[];
    links: GraphLinkData[];
    focus_topic?: GraphNodeData | null;
  } | null>(null);

  // Selection state for side drawers
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedLink, setSelectedLink] = useState<GraphLinkData | null>(null);

  const canvasRef = useRef<GraphCanvasHandle>(null);

  const authHeaders = useMemo(() => {
    return {
      "x-test-user-id": activeUser.id,
      "x-test-user-email": activeUser.email,
    };
  }, [activeUser]);

  // Hydrate central config on mount
  useEffect(() => {
    fetchGraphRuntimeConfig().then((cfg) => {
      setRuntimeConfig(cfg);
      setHopCount(cfg.defaultSearchHops);
      setNodeCap(cfg.maxVisibleNodes);
    });
  }, []);

  // Load subject list on mount
  useEffect(() => {
    if (!isStressTestMode) {
      loadSubjects();
    }
  }, [activeUser.id, isStressTestMode]);

  const loadSubjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/subjects", { headers: authHeaders });
      if (!res.ok) throw new Error("Could not load subject folders.");
      const list: SubjectItem[] = await res.json();
      setSubjects(list);
      if (list.length > 0) {
        setSelectedSubjectId(list[0].id);
        fetchSubjectGraph(list[0].id);
      } else {
        setLoading(false);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load subjects.");
      setLoading(false);
    }
  };

  const fetchSubjectGraph = async (subjectId: string, fresh = false) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedLink(null);
    setSelectedClusterId("all");
    setFocusedTopicMeta(null);
    setFocusedDbGraph(null);

    try {
      const url = fresh ? `/api/graphs/${subjectId}?fresh=true` : `/api/graphs/${subjectId}`;
      const res = await fetch(url, { headers: authHeaders });
      if (!res.ok) throw new Error("Could not fetch cached graph for subject.");
      const data: GraphResponse = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load subject graph.");
    } finally {
      setLoading(false);
    }
  };

  const fetchSyntheticStressTest = async (count: number = 500) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedLink(null);
    setSelectedClusterId("all");
    setFocusedTopicMeta(null);
    setFocusedDbGraph(null);

    try {
      const res = await fetch(`/api/graphs/synthetic/stress-test?node_count=${count}`);
      if (!res.ok) throw new Error("Failed to generate synthetic stress-test graph.");
      const data: GraphResponse = await res.json();
      setGraphData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load synthetic benchmark.");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStressTest = (enable: boolean) => {
    setIsStressTestMode(enable);
    if (enable) {
      fetchSyntheticStressTest(500);
    } else {
      if (selectedSubjectId) {
        fetchSubjectGraph(selectedSubjectId);
      } else {
        loadSubjects();
      }
    }
  };

  // Fetch focused 2-3 hop subgraph from backend for database topics
  const loadFocusedDbGraph = useCallback(
    async (topicId: string, hops: number, includeWeak: boolean, cap: number) => {
      try {
        const params = new URLSearchParams({
          hops: String(hops),
          include_weak: String(includeWeak),
          max_nodes: String(cap),
        });
        const res = await fetch(`/api/graphs/focus/${topicId}?${params.toString()}`, {
          headers: authHeaders,
        });
        if (!res.ok) throw new Error("Failed to load focused neighborhood.");
        const focusedJson = await res.json();
        setFocusedDbGraph(focusedJson);
        if (focusedJson.focus_topic) {
          setSelectedNode(focusedJson.focus_topic);
        }
        setTimeout(() => canvasRef.current?.resetView(), 220);
      } catch (err: any) {
        setError(err.message || "Could not load focused topic graph.");
      }
    },
    [authHeaders]
  );

  const handleSelectSearchTopic = useCallback(
    async (suggestion: SearchTopicSuggestion) => {
      setSelectedLink(null);
      setSelectedClusterId("all");
      setFocusedTopicMeta({
        id: suggestion.id,
        keyword: suggestion.keyword,
        matchedAlias: suggestion.matched_alias,
        source: suggestion.source === "local" ? "local" : "database",
      });

      if (suggestion.source === "local") {
        setFocusedDbGraph(null);
        const foundNode = graphData?.nodes?.find((n) => n.id === suggestion.id);
        setSelectedNode(
          foundNode
            ? { ...foundNode, hop_distance: 0, is_focus: true }
            : {
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
        setTimeout(() => canvasRef.current?.resetView(), 220);
      } else {
        await loadFocusedDbGraph(suggestion.id, hopCount, showWeakLinks, nodeCap);
      }
    },
    [graphData?.nodes, hopCount, showWeakLinks, nodeCap, loadFocusedDbGraph]
  );

  const handleChangeHops = (nextHops: number) => {
    setHopCount(nextHops);
    if (focusedTopicMeta?.source === "database") {
      loadFocusedDbGraph(focusedTopicMeta.id, nextHops, showWeakLinks, nodeCap);
    } else {
      setTimeout(() => canvasRef.current?.resetView(), 180);
    }
  };

  const handleClearTopicFocus = () => {
    setFocusedTopicMeta(null);
    setFocusedDbGraph(null);
    setSelectedNode(null);
    setTimeout(() => canvasRef.current?.resetView(), 120);
  };

  // Filter nodes according to focused search, visible node cap, and cluster zoom
  const displayedGraph = useMemo(() => {
    if (focusedTopicMeta?.source === "database" && focusedDbGraph) {
      let links = [...focusedDbGraph.links];
      const totalLinksBeforeWeakFilter = links.length;
      if (!showWeakLinks) {
        links = links.filter((l) => (l.strength || 1) >= runtimeConfig.weakLinkThreshold);
      }
      return {
        nodes: focusedDbGraph.nodes,
        links,
        hiddenWeakCount: totalLinksBeforeWeakFilter - links.length,
        totalLinksBeforeWeakFilter,
      };
    }

    if (focusedTopicMeta?.source === "local" && graphData) {
      const sub = extractKHopSubgraph(
        graphData.nodes,
        graphData.links,
        focusedTopicMeta.id,
        hopCount,
        {
          includeWeak: showWeakLinks,
          weakThreshold: runtimeConfig.weakLinkThreshold,
          maxNodes: nodeCap,
          minHops: runtimeConfig.minSearchHops,
          maxHops: runtimeConfig.maxSearchHops,
        }
      );
      return {
        nodes: sub.nodes,
        links: sub.links,
        hiddenWeakCount: sub.hiddenWeakCount,
        totalLinksBeforeWeakFilter: sub.links.length + sub.hiddenWeakCount,
      };
    }

    if (!graphData) return { nodes: [], links: [], hiddenWeakCount: 0, totalLinksBeforeWeakFilter: 0 };

    let nodes = [...graphData.nodes];
    let links = [...graphData.links];

    // If cluster filter selected, isolate to cluster sub-graph
    if (selectedClusterId !== "all") {
      nodes = nodes.filter(
        (n) => n.cluster_id === selectedClusterId || n.parent_cluster_label === selectedClusterId
      );
      const validNodeIds = new Set(nodes.map((n) => n.id));
      links = links.filter((l) => {
        const srcId = typeof l.source === "object" ? l.source.id : l.source;
        const tgtId = typeof l.target === "object" ? l.target.id : l.target;
        return validNodeIds.has(srcId) && validNodeIds.has(tgtId);
      });
    }

    // Apply visible node capping (Risk R14: prevents FPS lag)
    if (nodes.length > nodeCap) {
      const degreeMap: Record<string, number> = {};
      links.forEach((l) => {
        const srcId = typeof l.source === "object" ? l.source.id : l.source;
        const tgtId = typeof l.target === "object" ? l.target.id : l.target;
        degreeMap[srcId] = (degreeMap[srcId] || 0) + 1;
        degreeMap[tgtId] = (degreeMap[tgtId] || 0) + 1;
      });

      nodes.sort((a, b) => (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0));
      nodes = nodes.slice(0, nodeCap);
      const activeIds = new Set(nodes.map((n) => n.id));
      links = links.filter((l) => {
        const srcId = typeof l.source === "object" ? l.source.id : l.source;
        const tgtId = typeof l.target === "object" ? l.target.id : l.target;
        return activeIds.has(srcId) && activeIds.has(tgtId);
      });
    }

    // Apply weak link filtering (Rule 13.8: strength < 3 hidden by default)
    const totalLinksBeforeWeakFilter = links.length;
    if (!showWeakLinks) {
      links = links.filter((l) => (l.strength || 1) >= runtimeConfig.weakLinkThreshold);
    }
    const hiddenWeakCount = totalLinksBeforeWeakFilter - links.length;

    return { nodes, links, hiddenWeakCount, totalLinksBeforeWeakFilter };
  }, [
    graphData,
    focusedTopicMeta,
    focusedDbGraph,
    hopCount,
    selectedClusterId,
    nodeCap,
    showWeakLinks,
    runtimeConfig,
  ]);

  // Handle cluster dropdown selection with smooth camera animation
  const handleClusterSelect = (clusterVal: string) => {
    setFocusedTopicMeta(null);
    setFocusedDbGraph(null);
    setSelectedClusterId(clusterVal);
    if (clusterVal === "all") {
      canvasRef.current?.resetView();
    } else {
      setTimeout(() => {
        canvasRef.current?.zoomToCluster(clusterVal);
      }, 50);
    }
  };

  // Callback when a link is edited in LinkDetailPanel (Task T10)
  const handleLinkUpdated = (updatedLink: GraphLinkData) => {
    if (!graphData) return;
    setGraphData({
      ...graphData,
      links: graphData.links.map((l) => (l.id === updatedLink.id ? updatedLink : l)),
    });
    setSelectedLink(updatedLink);
  };

  // Callback when a link is deleted in LinkDetailPanel (Task T10)
  const handleLinkDeleted = (deletedLinkId: string) => {
    if (!graphData) return;
    setGraphData({
      ...graphData,
      links: graphData.links.filter((l) => l.id !== deletedLinkId),
    });
    setSelectedLink(null);
  };

  // Connected edges & quick-jump chips for selected node
  const selectedNodeConnectedChips: ConnectedConceptChip[] = useMemo(() => {
    if (!selectedNode) return [];
    const nodeMap = new Map<string, GraphNodeData>();
    for (const n of displayedGraph.nodes) nodeMap.set(n.id, n);

    const chips: ConnectedConceptChip[] = [];
    for (const l of displayedGraph.links) {
      const srcId = getEndpointId(l.source as any);
      const tgtId = getEndpointId(l.target as any);
      if (srcId === selectedNode.id) {
        const other = nodeMap.get(tgtId);
        chips.push({
          edgeId: l.id,
          targetTopicId: tgtId,
          targetKeyword: other?.keyword || tgtId,
          type: l.type || "related",
          strength: l.strength || 3,
        });
      } else if (tgtId === selectedNode.id) {
        const other = nodeMap.get(srcId);
        chips.push({
          edgeId: l.id,
          targetTopicId: srcId,
          targetKeyword: other?.keyword || srcId,
          type: l.type || "related",
          strength: l.strength || 3,
        });
      }
    }
    return chips;
  }, [selectedNode, displayedGraph]);

  const handleFocusConnectedTopic = (topicId: string) => {
    const node = displayedGraph.nodes.find((n) => n.id === topicId);
    const sourceMode = focusedTopicMeta?.source || (isStressTestMode ? "local" : "database");
    handleSelectSearchTopic({
      id: topicId,
      subject_id: node?.subject_id || selectedSubjectId,
      subject_name: node?.subject_name || graphData?.subject_name || "Subject",
      keyword: node?.keyword || node?.name || "Topic",
      aliases: node?.aliases || [],
      explanation: node?.explanation || "",
      real_world_use: node?.real_world_use || "",
      module_no: node?.module_no || 1,
      reviewed: Boolean(node?.reviewed),
      cluster_label: node?.cluster_label,
      source: sourceMode,
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 space-y-4">
      {/* Top Header & Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Left: Title & Mode Toggle */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-2xs">
            <Network className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900">Interactive Subject Graph</h1>
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-indigo-50 border border-indigo-200 text-indigo-700">
                F11 • Task T14
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {isStressTestMode
                ? "500-Topic Stress Test Benchmark (Louvain Communities & Smooth Canvas Zoom)"
                : "Force-directed topic clusters from your verified study notes"}
            </p>
          </div>

          {/* Stress test vs real data toggle */}
          <div className="ml-0 sm:ml-4 flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200 text-xs">
            <button
              onClick={() => handleToggleStressTest(false)}
              className={`px-2.5 py-1 rounded-md font-semibold transition ${!isStressTestMode
                  ? "bg-white text-indigo-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
                }`}
            >
              Real Notes
            </button>
            <button
              onClick={() => handleToggleStressTest(true)}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-md font-semibold transition ${isStressTestMode
                  ? "bg-indigo-600 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
                }`}
            >
              <Zap className="w-3 h-3" />
              500-Topic Stress Test
            </button>
          </div>
        </div>

        {/* Right: Controls & Options */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Subject picker (if in real notes mode) */}
          {!isStressTestMode && subjects.length > 0 && (
            <div className="flex items-center gap-1.5 text-xs">
              <Folder className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={selectedSubjectId}
                onChange={(e) => {
                  setSelectedSubjectId(e.target.value);
                  fetchSubjectGraph(e.target.value);
                }}
                className="text-xs py-1.5 px-2 bg-slate-50 border border-slate-300 rounded-lg shadow-2xs font-medium text-slate-700 focus:ring-2 focus:ring-indigo-500"
              >
                {subjects.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Cluster filter dropdown */}
          {graphData && graphData.clusters && (
            <div className="flex items-center gap-1.5 text-xs">
              <Layers className="w-3.5 h-3.5 text-indigo-500" />
              <select
                value={selectedClusterId}
                onChange={(e) => handleClusterSelect(e.target.value)}
                className="text-xs py-1.5 px-2.5 bg-indigo-50/60 border border-indigo-200 rounded-lg shadow-2xs font-semibold text-indigo-900 focus:ring-2 focus:ring-indigo-500"
              >
                <option value="all">Full Subject (All Clusters)</option>
                {graphData.clusters.map((c) => (
                  <option key={c.id} value={c.label}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Weak-link toggle (Rule 13.8) */}
          <button
            onClick={() => setShowWeakLinks(!showWeakLinks)}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition ${showWeakLinks
                ? "bg-amber-50 text-amber-800 border-amber-300 shadow-2xs"
                : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
              }`}
            title="Toggle links with strength < 3 (Hidden by default to prevent hairballs)"
          >
            {showWeakLinks ? <Eye className="w-3.5 h-3.5 text-amber-600" /> : <EyeOff className="w-3.5 h-3.5 text-slate-400" />}
            <span>
              {showWeakLinks
                ? `Weak Links Shown (All ${displayedGraph.totalLinksBeforeWeakFilter})`
                : `Weak Links Hidden (${displayedGraph.hiddenWeakCount} filtered)`}
            </span>
          </button>

          {/* Node cap dropdown (Risk R14) */}
          <div className="flex items-center gap-1 bg-slate-50 px-2 py-1 rounded-lg border border-slate-200 text-xs">
            <Sliders className="w-3 h-3 text-slate-400" />
            <span className="text-slate-500 font-medium">Cap:</span>
            <select
              value={nodeCap}
              onChange={(e) => setNodeCap(Number(e.target.value))}
              className="bg-transparent text-xs font-bold text-slate-800 focus:outline-none"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={150}>150 (Default)</option>
              <option value={300}>300</option>
              <option value={500}>500 (Max)</option>
            </select>
          </div>

          {/* Camera Reset & Zoom buttons */}
          <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg border border-slate-200">
            <button
              onClick={() => canvasRef.current?.resetView()}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-white transition"
              title="Reset camera / Full view"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => canvasRef.current?.zoomIn()}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-white transition"
              title="Zoom in"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => canvasRef.current?.zoomOut()}
              className="p-1 rounded text-slate-600 hover:text-slate-900 hover:bg-white transition"
              title="Zoom out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Topic Search & Focused Neighborhood Bar (Task T16, Feature F13) */}
      <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs space-y-3">
        <TopicSearchBar
          localNodes={graphData?.nodes || []}
          subjectId={!isStressTestMode && selectedSubjectId ? selectedSubjectId : undefined}
          authHeaders={authHeaders}
          onSelectTopic={handleSelectSearchTopic}
          onClearFocus={handleClearTopicFocus}
          activeFocusKeyword={focusedTopicMeta?.keyword}
          placeholder="Search any topic or merged alias in this subject (e.g. Module 4 topic)..."
          variant="light"
        />

        {focusedTopicMeta && (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 p-3 bg-indigo-50 border border-indigo-200 rounded-xl text-xs">
            <div className="flex items-center flex-wrap gap-2">
              <Crosshair className="w-4 h-4 text-indigo-600 shrink-0" />
              <span className="font-bold text-indigo-950">
                Focused ({hopCount}-Hop Subgraph): {focusedTopicMeta.keyword}
              </span>
              {focusedTopicMeta.matchedAlias && (
                <span className="px-2 py-0.5 rounded-full bg-amber-100 border border-amber-300 text-amber-800 font-semibold">
                  via alias "{focusedTopicMeta.matchedAlias}"
                </span>
              )}
              <span className="text-indigo-700">
                ({displayedGraph.nodes.length} topics, {displayedGraph.links.length} links)
              </span>
            </div>

            <div className="flex items-center flex-wrap gap-2">
              <div className="flex items-center bg-white p-0.5 rounded-lg border border-indigo-200">
                {[2, 3].map((h) => (
                  <button
                    key={h}
                    onClick={() => handleChangeHops(h)}
                    className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition ${hopCount === h
                        ? "bg-indigo-600 text-white"
                        : "text-slate-600 hover:text-indigo-700"
                      }`}
                  >
                    {h} Hops
                  </button>
                ))}
              </div>

              <button
                onClick={() => {
                  const target = displayedGraph.nodes.find((n) => n.id === focusedTopicMeta.id);
                  if (target) setSelectedNode(target);
                }}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white hover:bg-indigo-100 border border-indigo-200 font-semibold text-indigo-700 transition"
              >
                <BookOpen className="w-3.5 h-3.5" />
                Theory Card
              </button>

              <button
                onClick={handleClearTopicFocus}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white hover:bg-slate-100 border border-slate-200 font-semibold text-slate-700 transition"
              >
                <X className="w-3.5 h-3.5" />
                Exit Focus
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Stats Bar */}
      {graphData && (
        <div className="flex items-center justify-between text-xs px-2 text-slate-500">
          <div className="flex items-center gap-4">
            <span>
              Showing <strong className="text-slate-800">{displayedGraph.nodes.length}</strong> nodes
              {graphData.nodes.length > displayedGraph.nodes.length && (
                <span className="text-slate-400 ml-1">
                  (capped from {graphData.stats.total_available_nodes || graphData.nodes.length})
                </span>
              )}
            </span>
            <span>
              Active links: <strong className="text-slate-800">{displayedGraph.links.length}</strong>
              {displayedGraph.hiddenWeakCount > 0 && (
                <span className="text-amber-600 ml-1 font-medium">
                  ({displayedGraph.hiddenWeakCount} weak hidden)
                </span>
              )}
            </span>
            <span>
              Clusters: <strong className="text-slate-800">{graphData.clusters?.length || 0}</strong>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              Smooth 60 FPS Canvas Rendering
            </span>
          </div>
        </div>
      )}

      {/* Main Canvas Container */}
      <div className="w-full h-[650px] rounded-2xl overflow-hidden border border-slate-300 shadow-inner relative bg-slate-950">
        {loading ? (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-slate-900/90 text-white space-y-3">
            <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm font-semibold tracking-wide text-slate-300">
              {isStressTestMode ? "Compiling 500-Topic Benchmark Graph..." : "Loading Subject Knowledge Graph..."}
            </p>
          </div>
        ) : error ? (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 text-center bg-slate-900 text-white space-y-3">
            <AlertCircle className="w-10 h-10 text-rose-500" />
            <h3 className="font-bold text-base">Graph Rendering Error</h3>
            <p className="text-xs text-slate-400 max-w-md">{error}</p>
            <button
              onClick={() => (isStressTestMode ? fetchSyntheticStressTest(500) : loadSubjects())}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-xs font-bold transition"
            >
              Try Again
            </button>
          </div>
        ) : (
          <GraphCanvas
            ref={canvasRef}
            nodes={displayedGraph.nodes}
            links={displayedGraph.links}
            selectedNodeId={selectedNode?.id}
            selectedLinkId={selectedLink?.id}
            onNodeSelect={(node) => {
              setSelectedLink(null);
              setSelectedNode(node);
            }}
            onLinkSelect={(link) => {
              setSelectedNode(null);
              setSelectedLink(link);
            }}
            onBackgroundClick={() => {
              setSelectedNode(null);
              setSelectedLink(null);
            }}
            showWeakLinks={showWeakLinks}
          />
        )}

        {/* Side Drawers */}
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          connectedEdgeCount={selectedNodeConnectedChips.length}
          connectedLinks={selectedNodeConnectedChips}
          onFocusCluster={(cid) => handleClusterSelect(cid)}
          onFocusTopic={handleFocusConnectedTopic}
        />

        <LinkDetailPanel
          link={selectedLink}
          onClose={() => setSelectedLink(null)}
          onLinkUpdated={handleLinkUpdated}
          onLinkDeleted={handleLinkDeleted}
          userAuthHeaders={authHeaders}
        />
      </div>
    </div>
  );
};

