import React, { useState, useEffect } from "react";
import {
  Lock,
  Unlock,
  Edit2,
  Trash2,
  Plus,
  RefreshCw,
  Search,
  Check,
  X,
  AlertCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
} from "lucide-react";

interface EvidenceItem {
  id?: string;
  edge_id: string;
  chunk_id?: string | null;
  snippet: string;
}

interface EdgeItem {
  id: string;
  topic_a: string;
  topic_b: string;
  topic_a_keyword: string;
  topic_b_keyword: string;
  topic_a_subject_name?: string;
  topic_b_subject_name?: string;
  type: string;
  reason: string;
  industry_example: string;
  strength: number;
  scope: "same_subject" | "cross_subject";
  status: "auto" | "edited" | "deleted";
  locked: boolean;
  is_visible: boolean;
  graph_version: number;
  evidence: EvidenceItem[];
}

interface TopicOption {
  id: string;
  keyword: string;
  subject_name?: string;
}

const LINK_TYPES = [
  { value: "prerequisite_of", label: "Prerequisite Of", desc: "A must be understood before B" },
  { value: "same_concept", label: "Same Concept", desc: "Different names or perspectives for the same idea" },
  { value: "example_of", label: "Example Of", desc: "A is a concrete implementation of B" },
  { value: "applies_in", label: "Applies In", desc: "A is a tool or method used directly in B" },
  { value: "contrasts_with", label: "Contrasts With", desc: "A and B are opposing alternatives or trade-offs" },
  { value: "part_of", label: "Part Of", desc: "A is a sub-component or module of B" },
];

export const LinkManager: React.FC = () => {
  const [edges, setEdges] = useState<EdgeItem[]>([]);
  const [topics, setTopics] = useState<TopicOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState("");
  const [scopeFilter, setScopeFilter] = useState<string>("all");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [lockedOnly, setLockedOnly] = useState(false);

  // Expanded evidence
  const [expandedEvidence, setExpandedEvidence] = useState<Record<string, boolean>>({});

  // Editing state
  const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<{
    type: string;
    reason: string;
    industry_example: string;
    strength: number;
  }>({
    type: "prerequisite_of",
    reason: "",
    industry_example: "",
    strength: 3,
  });

  // Delete modal state
  const [deletingEdge, setDeletingEdge] = useState<EdgeItem | null>(null);

  // Manual Add Modal State
  const [showAddModal, setShowAddModal] = useState(false);
  const [manualForm, setManualForm] = useState({
    topic_a: "",
    topic_b: "",
    type: "prerequisite_of",
    reason: "",
    industry_example: "Practical application",
    strength: 3,
    snippet_a: "",
    snippet_b: "",
  });

  // Fetch edges
  const fetchEdges = async () => {
    setLoading(true);
    try {
      let url = `/api/edges?include_deleted=${includeDeleted}&locked_only=${lockedOnly}`;
      if (scopeFilter !== "all") {
        url += `&scope=${scopeFilter}`;
      }
      const res = await fetch(url);
      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || `Server returned ${res.status}`);
      }
      const data: EdgeItem[] = await res.json();
      setEdges(data);
      setError(null); // Clear error on successful fetch
    } catch (err: any) {
      setError(`Failed to load links: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Fetch topics for manual add dropdown
  const fetchTopics = async () => {
    try {
      const res = await fetch("/api/topics");
      if (res.ok) {
        const data = await res.json();
        setTopics(data);
      }
    } catch {
      // Topic dropdown fallback
    }
  };

  useEffect(() => {
    fetchEdges();
    fetchTopics();
  }, [includeDeleted, lockedOnly, scopeFilter]);

  const showNotification = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 4000);
  };

  // Start editing an edge
  const handleStartEdit = (edge: EdgeItem) => {
    setEditingEdgeId(edge.id);
    setEditForm({
      type: edge.type,
      reason: edge.reason,
      industry_example: edge.industry_example,
      strength: edge.strength,
    });
  };

  // Save edit
  const handleSaveEdit = async (edgeId: string) => {
    setError(null);
    try {
      const res = await fetch(`/api/edges/${edgeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || `Error ${res.status}`);
      }
      const updated: EdgeItem = await res.json();
      setEdges((prev) => prev.map((e) => (e.id === edgeId ? updated : e)));
      setEditingEdgeId(null);
      showNotification("Link successfully updated and locked. Automation will not overwrite this.");
    } catch (err: any) {
      setError(`Failed to update link: ${err.message}`);
    }
  };

  // Soft delete confirmation
  const handleConfirmDelete = async () => {
    if (!deletingEdge) return;
    setError(null);
    try {
      const res = await fetch(`/api/edges/${deletingEdge.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || `Error ${res.status}`);
      }
      // Update locally
      if (includeDeleted) {
        setEdges((prev) =>
          prev.map((e) =>
            e.id === deletingEdge.id
              ? { ...e, status: "deleted", locked: true, is_visible: false }
              : e
          )
        );
      } else {
        setEdges((prev) => prev.filter((e) => e.id !== deletingEdge.id));
      }
      setDeletingEdge(null);
      showNotification("Link soft-deleted and locked. The pipeline will never recreate this link.");
    } catch (err: any) {
      setError(`Failed to delete link: ${err.message}`);
    }
  };

  // Create manual link
  const handleCreateManual = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!manualForm.topic_a || !manualForm.topic_b) {
      setError("Please select two distinct topics to connect.");
      return;
    }
    if (manualForm.topic_a === manualForm.topic_b) {
      setError("A topic cannot be connected to itself.");
      return;
    }
    if (!manualForm.reason.trim()) {
      setError("Please provide a reason why these topics connect.");
      return;
    }

    try {
      const res = await fetch("/api/edges/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(manualForm),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || `Error ${res.status}`);
      }
      const created: EdgeItem = await res.json();
      setEdges((prev) => [created, ...prev.filter((e) => e.id !== created.id)]);
      setShowAddModal(false);
      setManualForm({
        topic_a: "",
        topic_b: "",
        type: "prerequisite_of",
        reason: "",
        industry_example: "Practical application",
        strength: 3,
        snippet_a: "",
        snippet_b: "",
      });
      showNotification("Manual link created and locked. It is protected from automation overwrites.");
    } catch (err: any) {
      setError(`Failed to create manual link: ${err.message}`);
    }
  };

  const toggleEvidence = (id: string) => {
    setExpandedEvidence((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Filter edges by search term
  const filteredEdges = edges.filter((e) => {
    if (!searchTerm.trim()) return true;
    const term = searchTerm.toLowerCase();
    return (
      e.topic_a_keyword.toLowerCase().includes(term) ||
      e.topic_b_keyword.toLowerCase().includes(term) ||
      e.reason.toLowerCase().includes(term) ||
      e.type.toLowerCase().includes(term)
    );
  });

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {/* Header and Controls */}
      <div className="bg-white rounded-xl shadow-xs border border-slate-200 p-6 mb-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                Link & Knowledge Graph Management
              </h1>
              <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded border border-indigo-200">
                Task T10 (F08)
              </span>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Inspect, edit, soft-delete, or manually create topic connections. User decisions are{" "}
              <strong className="text-slate-700">locked</strong> so background AI runs never overwrite your choices.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => fetchEdges()}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 hover:text-slate-900 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition"
              title="Refresh link list"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
            >
              <Plus className="w-4 h-4" />
              Add Manual Link
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-5">
          {/* Search */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search topics or reasons..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white"
            />
          </div>

          {/* Scope Filter */}
          <div>
            <select
              value={scopeFilter}
              onChange={(e) => setScopeFilter(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white"
            >
              <option value="all">All Scopes (Same & Cross-Subject)</option>
              <option value="same_subject">Same-Subject Only</option>
              <option value="cross_subject">Cross-Subject Only</option>
            </select>
          </div>

          {/* Locked Checkbox */}
          <div className="flex items-center gap-2 px-1">
            <input
              type="checkbox"
              id="lockedOnly"
              checked={lockedOnly}
              onChange={(e) => setLockedOnly(e.target.checked)}
              className="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500"
            />
            <label htmlFor="lockedOnly" className="text-sm text-slate-700 select-none flex items-center gap-1.5 cursor-pointer">
              <Lock className="w-3.5 h-3.5 text-amber-600" />
              Locked by Student Only
            </label>
          </div>

          {/* Include Deleted Checkbox */}
          <div className="flex items-center gap-2 px-1">
            <input
              type="checkbox"
              id="includeDeleted"
              checked={includeDeleted}
              onChange={(e) => setIncludeDeleted(e.target.checked)}
              className="w-4 h-4 text-rose-600 rounded border-slate-300 focus:ring-rose-500"
            />
            <label htmlFor="includeDeleted" className="text-sm text-slate-700 select-none flex items-center gap-1.5 cursor-pointer">
              <Trash2 className="w-3.5 h-3.5 text-rose-600" />
              Show Soft-Deleted (Audit)
            </label>
          </div>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm rounded-lg flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-emerald-600" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-600 hover:text-emerald-900">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 text-sm rounded-lg flex items-center justify-between shadow-xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-600 hover:text-rose-900">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Link List */}
      <div className="space-y-4">
        {loading && edges.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center text-slate-500 border border-slate-200">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
            Loading links and verification evidence...
          </div>
        ) : filteredEdges.length === 0 ? (
          <div className="bg-white rounded-xl p-12 text-center text-slate-500 border border-slate-200">
            <Lock className="w-8 h-8 mx-auto mb-2 text-slate-300" />
            <p className="font-medium text-slate-700">No links match the selected filters.</p>
            <p className="text-xs text-slate-400 mt-1">
              Try adjusting your search, scope, or click &quot;Add Manual Link&quot; above.
            </p>
          </div>
        ) : (
          filteredEdges.map((edge) => (
            <div
              key={edge.id}
              className={`bg-white rounded-xl border transition shadow-xs ${
                edge.status === "deleted"
                  ? "border-rose-200 bg-rose-50/30 opacity-75"
                  : edge.locked
                  ? "border-amber-200"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="p-5">
                {/* Top Bar: Topic Keywords & Badges */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 text-base">{edge.topic_a_keyword}</span>
                      {edge.topic_a_subject_name && (
                        <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
                          {edge.topic_a_subject_name}
                        </span>
                      )}
                    </div>

                    <span className="text-slate-400 font-black text-sm">⟷</span>

                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 text-base">{edge.topic_b_keyword}</span>
                      {edge.topic_b_subject_name && (
                        <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
                          {edge.topic_b_subject_name}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Status & Lock Pills */}
                  <div className="flex items-center gap-2">
                    {/* Scope Badge */}
                    <span
                      className={`text-xs px-2 py-0.5 font-medium rounded-full ${
                        edge.scope === "same_subject"
                          ? "bg-blue-50 text-blue-700 border border-blue-200"
                          : "bg-purple-50 text-purple-700 border border-purple-200"
                      }`}
                    >
                      {edge.scope === "same_subject" ? "Same Subject" : "Cross-Subject"}
                    </span>

                    {/* Status Badge */}
                    <span
                      className={`text-xs px-2 py-0.5 font-semibold rounded-full uppercase tracking-wider ${
                        edge.status === "deleted"
                          ? "bg-rose-100 text-rose-700"
                          : edge.status === "edited"
                          ? "bg-amber-100 text-amber-800"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {edge.status}
                    </span>

                    {/* Lock Indicator */}
                    <span
                      className={`text-xs px-2 py-0.5 font-semibold rounded-full flex items-center gap-1 ${
                        edge.locked
                          ? "bg-amber-500 text-white shadow-xs"
                          : "bg-slate-100 text-slate-500"
                      }`}
                      title={
                        edge.locked
                          ? "Protected: User edited or deleted this link. Automation will not overwrite."
                          : "Auto-generated by AI pipeline."
                      }
                    >
                      {edge.locked ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
                      {edge.locked ? "Locked" : "Unlocked"}
                    </span>
                  </div>
                </div>

                {/* Edit Form or Display */}
                {editingEdgeId === edge.id ? (
                  <div className="pt-4 space-y-3 bg-amber-50/50 p-4 rounded-lg mt-3 border border-amber-200">
                    <div className="flex items-center gap-2 text-xs font-semibold text-amber-800 uppercase tracking-wide">
                      <Edit2 className="w-3.5 h-3.5" />
                      Editing Link (Saving will mark this link Locked)
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Relationship Type
                        </label>
                        <select
                          value={editForm.type}
                          onChange={(e) => setEditForm({ ...editForm, type: e.target.value })}
                          className="w-full text-sm bg-white border border-slate-300 rounded px-2.5 py-1.5 focus:ring-2 focus:ring-amber-500"
                        >
                          {LINK_TYPES.map((lt) => (
                            <option key={lt.value} value={lt.value}>
                              {lt.label}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Strength (1 = weak/incidental, 5 = essential prerequisite)
                        </label>
                        <select
                          value={editForm.strength}
                          onChange={(e) =>
                            setEditForm({ ...editForm, strength: parseInt(e.target.value, 10) })
                          }
                          className="w-full text-sm bg-white border border-slate-300 rounded px-2.5 py-1.5 focus:ring-2 focus:ring-amber-500"
                        >
                          {[1, 2, 3, 4, 5].map((s) => (
                            <option key={s} value={s}>
                              Strength {s} {s >= 3 ? "(Visible in cross-subject)" : "(Weak)"}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Reason (Why these topics connect)
                      </label>
                      <textarea
                        rows={2}
                        value={editForm.reason}
                        onChange={(e) => setEditForm({ ...editForm, reason: e.target.value })}
                        className="w-full text-sm bg-white border border-slate-300 rounded p-2 focus:ring-2 focus:ring-amber-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Real-World / Industry Example
                      </label>
                      <input
                        type="text"
                        value={editForm.industry_example}
                        onChange={(e) =>
                          setEditForm({ ...editForm, industry_example: e.target.value })
                        }
                        className="w-full text-sm bg-white border border-slate-300 rounded px-2.5 py-1.5 focus:ring-2 focus:ring-amber-500"
                      />
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-2">
                      <button
                        onClick={() => setEditingEdgeId(null)}
                        className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-900 bg-white border border-slate-300 rounded font-medium"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleSaveEdit(edge.id)}
                        className="flex items-center gap-1.5 px-4 py-1.5 text-xs text-white bg-amber-600 hover:bg-amber-700 rounded font-semibold shadow-xs"
                      >
                        <Lock className="w-3.5 h-3.5" />
                        Save & Lock Link
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="pt-3">
                    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 mb-2">
                      <span className="font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
                        {edge.type}
                      </span>
                      <span>•</span>
                      <span className="font-medium">
                        Strength: <strong className="text-slate-700">{edge.strength}/5</strong>
                      </span>
                      <span>•</span>
                      <span>
                        Visibility:{" "}
                        <strong className={edge.is_visible ? "text-emerald-600" : "text-slate-400"}>
                          {edge.is_visible ? "Visible in graph" : "Hidden"}
                        </strong>
                      </span>
                    </div>

                    <p className="text-sm text-slate-800 leading-relaxed font-normal">
                      {edge.reason}
                    </p>

                    <div className="mt-2 text-xs text-slate-600 bg-slate-50 border border-slate-100 p-2.5 rounded-lg flex items-start gap-2">
                      <span className="font-semibold text-slate-500 shrink-0">Real-World Use:</span>
                      <span className="italic">{edge.industry_example}</span>
                    </div>

                    {/* Evidence Accordion */}
                    {edge.evidence && edge.evidence.length > 0 && (
                      <div className="mt-3">
                        <button
                          onClick={() => toggleEvidence(edge.id)}
                          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 font-medium"
                        >
                          {expandedEvidence[edge.id] ? (
                            <ChevronUp className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronDown className="w-3.5 h-3.5" />
                          )}
                          {edge.evidence.length} Evidence Snippet{edge.evidence.length > 1 ? "s" : ""}
                        </button>

                        {expandedEvidence[edge.id] && (
                          <div className="mt-2 space-y-1.5 pl-3 border-l-2 border-indigo-200">
                            {edge.evidence.map((ev, idx) => (
                              <div key={idx} className="text-xs text-slate-600">
                                <span className="font-semibold text-indigo-600 mr-1.5">
                                  {ev.snippet.startsWith("[manual]") ? "[Manual Note]" : `Snippet ${idx + 1}:`}
                                </span>
                                <span className="italic">&ldquo;{ev.snippet}&rdquo;</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Action Bar */}
                    <div className="flex items-center justify-between border-t border-slate-100 mt-4 pt-3">
                      <div className="text-xs text-slate-400">
                        {edge.locked ? (
                          <span className="text-amber-700 flex items-center gap-1">
                            <Lock className="w-3 h-3" /> User lock active: Automation will not overwrite this link
                          </span>
                        ) : (
                          <span>Generated by pipeline judge</span>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {edge.status !== "deleted" && (
                          <>
                            <button
                              onClick={() => handleStartEdit(edge)}
                              className="flex items-center gap-1 text-xs px-2.5 py-1 text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded font-medium transition"
                            >
                              <Edit2 className="w-3 h-3" />
                              Edit
                            </button>
                            <button
                              onClick={() => setDeletingEdge(edge)}
                              className="flex items-center gap-1 text-xs px-2.5 py-1 text-rose-600 hover:text-rose-800 bg-rose-50 hover:bg-rose-100 rounded font-medium transition"
                            >
                              <Trash2 className="w-3 h-3" />
                              Soft Delete
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Soft Delete Modal */}
      {deletingEdge && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200 animate-in fade-in duration-150">
            <div className="flex items-center gap-3 text-rose-600 mb-3">
              <ShieldAlert className="w-6 h-6" />
              <h2 className="text-base font-bold text-slate-900">Soft-Delete Link</h2>
            </div>

            <p className="text-sm text-slate-600 mb-2">
              Are you sure you want to remove the link between:
            </p>
            <div className="p-3 bg-slate-50 rounded-lg text-sm font-semibold text-slate-800 mb-3">
              {deletingEdge.topic_a_keyword} ⟷ {deletingEdge.topic_b_keyword}
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 mb-5">
              <strong>How Soft-Delete Works:</strong> We mark this link as{" "}
              <code className="bg-amber-100 px-1 rounded">status = &apos;deleted&apos;</code> and{" "}
              <code className="bg-amber-100 px-1 rounded">locked = TRUE</code>. It will disappear from the graph and
              the pipeline will <strong>never recreate it</strong> on future note uploads.
            </div>

            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setDeletingEdge(null)}
                className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 bg-slate-100 rounded-lg font-medium"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                className="px-4 py-2 text-sm text-white bg-rose-600 hover:bg-rose-700 rounded-lg font-semibold shadow-xs"
              >
                Confirm Soft Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Add Link Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-xl max-w-xl w-full p-6 shadow-xl border border-slate-200 my-8">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-indigo-600" />
                <h2 className="text-base font-bold text-slate-900">Add Manual Link</h2>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateManual} className="space-y-4">
              {/* Topic Selectors */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    First Topic (Topic A) *
                  </label>
                  <select
                    value={manualForm.topic_a}
                    onChange={(e) => setManualForm({ ...manualForm, topic_a: e.target.value })}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                    required
                  >
                    <option value="">-- Select Topic A --</option>
                    {topics.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.keyword} {t.subject_name ? `(${t.subject_name})` : ""}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Second Topic (Topic B) *
                  </label>
                  <select
                    value={manualForm.topic_b}
                    onChange={(e) => setManualForm({ ...manualForm, topic_b: e.target.value })}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                    required
                  >
                    <option value="">-- Select Topic B --</option>
                    {topics.map((t) => (
                      <option key={t.id} value={t.id} disabled={t.id === manualForm.topic_a}>
                        {t.keyword} {t.subject_name ? `(${t.subject_name})` : ""}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Type and Strength */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Relationship Type *
                  </label>
                  <select
                    value={manualForm.type}
                    onChange={(e) => setManualForm({ ...manualForm, type: e.target.value })}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                  >
                    {LINK_TYPES.map((lt) => (
                      <option key={lt.value} value={lt.value}>
                        {lt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Strength (1-5) *
                  </label>
                  <select
                    value={manualForm.strength}
                    onChange={(e) =>
                      setManualForm({ ...manualForm, strength: parseInt(e.target.value, 10) })
                    }
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                  >
                    {[1, 2, 3, 4, 5].map((s) => (
                      <option key={s} value={s}>
                        Strength {s} {s >= 3 ? "(High confidence / Visible)" : "(Weak)"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Reason */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Reason * (Why these topics connect)
                </label>
                <textarea
                  rows={2}
                  value={manualForm.reason}
                  onChange={(e) => setManualForm({ ...manualForm, reason: e.target.value })}
                  placeholder="e.g. TCP Handshake is required to establish reliable transport before HTTP headers can be sent."
                  className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                  required
                />
              </div>

              {/* Industry Example */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Industry / Real-World Example
                </label>
                <input
                  type="text"
                  value={manualForm.industry_example}
                  onChange={(e) => setManualForm({ ...manualForm, industry_example: e.target.value })}
                  placeholder="e.g. Cloudflare edge servers optimize connection handshakes to reduce latency."
                  className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Optional Snippets */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-2">
                <span className="text-xs font-semibold text-slate-700 block">
                  Optional Evidence Snippets (will be labeled &apos;manual&apos;)
                </span>
                <input
                  type="text"
                  placeholder="Supporting quote or note for Topic A (optional)"
                  value={manualForm.snippet_a}
                  onChange={(e) => setManualForm({ ...manualForm, snippet_a: e.target.value })}
                  className="w-full text-xs bg-white border border-slate-200 rounded p-1.5 focus:ring-2 focus:ring-indigo-500"
                />
                <input
                  type="text"
                  placeholder="Supporting quote or note for Topic B (optional)"
                  value={manualForm.snippet_b}
                  onChange={(e) => setManualForm({ ...manualForm, snippet_b: e.target.value })}
                  className="w-full text-xs bg-white border border-slate-200 rounded p-1.5 focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex items-center gap-2 px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm transition"
                >
                  <Lock className="w-4 h-4" />
                  Save Manual Link & Lock
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

