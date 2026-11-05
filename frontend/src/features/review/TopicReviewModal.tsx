import React, { useState, useEffect } from "react";
import {
  X,
  CheckCheck,
  Check,
  Edit3,
  Trash2,
  Clock,
  Sparkles,
  AlertCircle,
  FileText,
  Save,
  RotateCcw,
  Loader2,
  ArrowRight,
  ShieldCheck,
  Layers,
} from "lucide-react";

export interface TopicReviewItem {
  id: string;
  subject_id: string;
  keyword: string;
  explanation: string;
  real_world_use?: string | null;
  module_no?: number | null;
  reviewed: boolean;
  source_pages: number[];
  chunk_count: number;
}

export interface TopicListResponse {
  document_id: string;
  filename: string;
  subject_id: string;
  subject_name: string;
  topics: TopicReviewItem[];
  total_count: number;
  reviewed_count: number;
  unreviewed_count: number;
}

interface TopicReviewModalProps {
  documentId: string;
  documentTitle: string;
  moduleNo?: number;
  activeUserId: string;
  activeUserEmail: string;
  isOpen: boolean;
  onClose: () => void;
  onTopicsUpdated?: () => void;
}

export const TopicReviewModal: React.FC<TopicReviewModalProps> = ({
  documentId,
  documentTitle,
  moduleNo,
  activeUserId,
  activeUserEmail,
  isOpen,
  onClose,
  onTopicsUpdated,
}) => {
  const [loading, setLoading] = useState<boolean>(true);
  const [topics, setTopics] = useState<TopicReviewItem[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  // Editing state for an individual topic card
  const [editingTopicId, setEditingTopicId] = useState<string | null>(null);
  const [editKeyword, setEditKeyword] = useState<string>("");
  const [editExplanation, setEditExplanation] = useState<string>("");
  const [editRealWorldUse, setEditRealWorldUse] = useState<string>("");
  const [savingEdit, setSavingEdit] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Deletion prompt state
  const [deletingTopicId, setDeletingTopicId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  // Bulk action loading state
  const [isBulkActing, setIsBulkActing] = useState<boolean>(false);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);

  const authHeaders = {
    "x-test-user-id": activeUserId,
    "x-test-user-email": activeUserEmail,
  };

  // Helper to show temporary toast-like notifications
  const triggerNotice = (msg: string) => {
    setActionNotice(msg);
    setTimeout(() => {
      setActionNotice(null);
    }, 3500);
  };

  // Fetch topics for this document
  const fetchTopics = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`/api/documents/${documentId}/topics`, {
        headers: authHeaders,
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to fetch topics (HTTP ${res.status})`);
      }
      const data: TopicListResponse = await res.json();
      setTopics(data.topics);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load topics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && documentId) {
      fetchTopics();
    } else {
      setEditingTopicId(null);
      setDeletingTopicId(null);
    }
  }, [isOpen, documentId, activeUserId]);

  if (!isOpen) return null;

  // Count reviewed vs unreviewed topics
  const reviewedCount = topics.filter((t) => t.reviewed).length;
  const unreviewedCount = topics.length - reviewedCount;

  // Inline edit handlers
  const startEditing = (topic: TopicReviewItem) => {
    setEditingTopicId(topic.id);
    setEditKeyword(topic.keyword);
    setEditExplanation(topic.explanation);
    setEditRealWorldUse(topic.real_world_use || "");
    setEditError(null);
  };

  const cancelEditing = () => {
    setEditingTopicId(null);
    setEditKeyword("");
    setEditExplanation("");
    setEditRealWorldUse("");
    setEditError(null);
  };

  const handleSaveEdit = async (topicId: string) => {
    const cleanKw = editKeyword.trim();
    const cleanExp = editExplanation.trim();
    if (!cleanKw) {
      setEditError("Concept keyword cannot be empty.");
      return;
    }
    if (!cleanExp) {
      setEditError("Explanation cannot be empty.");
      return;
    }

    const lines = cleanExp.split(/\r?\n/).filter((l) => l.trim().length > 0);
    if (lines.length > 4) {
      setEditError(`Explanation must be at most 4 lines (currently ${lines.length}). Rule 13.3 strictly enforces 4 lines.`);
      return;
    }

    setSavingEdit(true);
    setEditError(null);

    try {
      const res = await fetch(`/api/topics/${topicId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({
          keyword: cleanKw,
          explanation: cleanExp,
          real_world_use: editRealWorldUse.trim() || null,
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Save failed (HTTP ${res.status})`);
      }

      const updatedTopic: TopicReviewItem = await res.json();
      setTopics((prev) => prev.map((t) => (t.id === topicId ? updatedTopic : t)));
      setEditingTopicId(null);
      triggerNotice(`Updated concept "${updatedTopic.keyword}"`);
      if (onTopicsUpdated) onTopicsUpdated();
    } catch (err: any) {
      setEditError(err.message || "Failed to save topic changes.");
    } finally {
      setSavingEdit(false);
    }
  };

  // Toggle individual topic reviewed state
  const handleToggleReviewed = async (topic: TopicReviewItem) => {
    const nextState = !topic.reviewed;
    try {
      const res = await fetch(`/api/topics/${topic.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders,
        },
        body: JSON.stringify({ reviewed: nextState }),
      });

      if (res.ok) {
        const updatedTopic: TopicReviewItem = await res.json();
        setTopics((prev) => prev.map((t) => (t.id === topic.id ? updatedTopic : t)));
        triggerNotice(nextState ? `Approved "${topic.keyword}"` : `Marked "${topic.keyword}" as unreviewed`);
        if (onTopicsUpdated) onTopicsUpdated();
      }
    } catch (err) {
      console.error("Failed to toggle review state:", err);
    }
  };

  // Delete topic handler
  const handleDeleteTopic = async (topicId: string) => {
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/topics/${topicId}`, {
        method: "DELETE",
        headers: authHeaders,
      });

      if (!res.ok) {
        throw new Error("Failed to delete topic from database.");
      }

      setTopics((prev) => prev.filter((t) => t.id !== topicId));
      setDeletingTopicId(null);
      triggerNotice("Topic removed from knowledge base.");
      if (onTopicsUpdated) onTopicsUpdated();
    } catch (err: any) {
      alert(err.message || "Failed to delete topic.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Bulk action: Approve All
  const handleApproveAll = async () => {
    setIsBulkActing(true);
    try {
      const res = await fetch(`/api/documents/${documentId}/topics/approve-all`, {
        method: "POST",
        headers: authHeaders,
      });

      if (!res.ok) {
        throw new Error("Approve all request failed.");
      }

      setTopics((prev) => prev.map((t) => ({ ...t, reviewed: true })));
      triggerNotice("All topics approved and marked as reviewed!");
      if (onTopicsUpdated) onTopicsUpdated();
    } catch (err: any) {
      alert(err.message || "Failed to approve topics.");
    } finally {
      setIsBulkActing(false);
    }
  };

  // Bulk action: Skip review
  const handleSkip = async () => {
    setIsBulkActing(true);
    try {
      await fetch(`/api/documents/${documentId}/topics/skip`, {
        method: "POST",
        headers: authHeaders,
      });
      triggerNotice("Review skipped. Unreviewed topics will link conservatively.");
      if (onTopicsUpdated) onTopicsUpdated();
      setTimeout(() => {
        onClose();
      }, 400);
    } catch (err: any) {
      console.error("Skip action error:", err);
      onClose();
    } finally {
      setIsBulkActing(false);
    }
  };

  // On-demand topic extraction
  const handleExtractTopics = async () => {
    setIsExtracting(true);
    try {
      const res = await fetch(`/api/documents/${documentId}/extract-topics`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) {
        throw new Error("Failed to extract topics.");
      }
      const data = await res.json();
      triggerNotice(`Extracted ${data.topics_created} topics!`);
      await fetchTopics();
      if (onTopicsUpdated) onTopicsUpdated();
    } catch (err: any) {
      alert(err.message || "Failed to extract topics.");
    } finally {
      setIsExtracting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/60 backdrop-blur-xs transition-opacity animate-in fade-in">
      <div className="bg-white w-full max-w-4xl max-h-[92vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-slate-200">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-200 flex items-center justify-between bg-white sticky top-0 z-10">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
              <FileText className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-900 tracking-tight">Review Extracted Topics</h2>
                {moduleNo !== undefined && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                    Module {moduleNo}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">
                Document: <span className="font-medium text-slate-700">{documentTitle}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
              title="Close without changes"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Action Toolbar / Summary Bar */}
        <div className="bg-slate-50 border-b border-slate-200 px-6 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-700">{topics.length} Concepts Found</span>
            <span className="text-slate-300">•</span>
            <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 font-medium">
              <Check className="w-3 h-3" /> {reviewedCount} Reviewed
            </span>
            {unreviewedCount > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200 font-medium">
                <Clock className="w-3 h-3" /> {unreviewedCount} Unreviewed
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleApproveAll}
              disabled={loading || isBulkActing || topics.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-medium transition-all shadow-xs disabled:opacity-50"
            >
              {isBulkActing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCheck className="w-3.5 h-3.5" />}
              Approve All
            </button>

            <button
              type="button"
              onClick={handleSkip}
              disabled={loading || isBulkActing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded-lg font-medium transition-all shadow-xs disabled:opacity-50"
              title="Skip manual review. Extracted topics will be saved with an 'Unreviewed' tag and linked conservatively."
            >
              Skip & Continue
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Transient Toast Notification */}
        {actionNotice && (
          <div className="bg-indigo-600 text-white px-6 py-2 text-xs font-medium flex items-center justify-between animate-in slide-in-from-top-1">
            <div className="flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5" />
              <span>{actionNotice}</span>
            </div>
            <button onClick={() => setActionNotice(null)} className="opacity-80 hover:opacity-100">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="py-16 text-center text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin mx-auto text-indigo-500 mb-2" />
              <p className="text-sm font-medium">Loading extracted topics from database...</p>
            </div>
          ) : errorMessage ? (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Unable to load topics</p>
                <p className="text-xs text-rose-700 mt-1">{errorMessage}</p>
                <button
                  onClick={fetchTopics}
                  className="mt-2 text-xs font-semibold underline hover:text-rose-900"
                >
                  Try Again
                </button>
              </div>
            </div>
          ) : topics.length === 0 ? (
            <div className="py-16 text-center text-slate-400 border-2 border-dashed border-slate-200 rounded-2xl p-6">
              <Layers className="w-10 h-10 mx-auto text-slate-300 mb-2" />
              <p className="text-sm font-medium text-slate-700">No academic topics extracted yet</p>
              <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1 mb-4">
                This document's topics haven't been extracted yet. You can run extraction now.
              </p>
              <button
                type="button"
                onClick={handleExtractTopics}
                disabled={isExtracting}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors cursor-pointer disabled:opacity-50"
              >
                {isExtracting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Extracting Topics with AI...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    Extract Topics Now
                  </>
                )}
              </button>
            </div>
          ) : (
            topics.map((topic) => {
              const isEditing = editingTopicId === topic.id;
              const isDeletingPrompt = deletingTopicId === topic.id;

              return (
                <div
                  key={topic.id}
                  className={`rounded-xl border transition-all ${
                    topic.reviewed
                      ? "border-slate-200 bg-white hover:border-slate-300 shadow-xs"
                      : "border-amber-200 bg-amber-50/30 hover:border-amber-300 shadow-xs"
                  }`}
                >
                  {isEditing ? (
                    /* Inline Editing Mode */
                    <div className="p-5 space-y-3 bg-indigo-50/20 rounded-xl">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider flex items-center gap-1.5">
                          <Edit3 className="w-3.5 h-3.5" /> Editing Concept
                        </span>
                        <div className="text-xs text-slate-400">
                          {editExplanation.split(/\r?\n/).filter((l) => l.trim().length > 0).length} / 4 lines
                        </div>
                      </div>

                      {editError && (
                        <div className="p-2.5 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
                          <span>{editError}</span>
                        </div>
                      )}

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Concept Keyword / Title
                        </label>
                        <input
                          type="text"
                          value={editKeyword}
                          onChange={(e) => setEditKeyword(e.target.value)}
                          className="w-full text-sm font-semibold px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                          placeholder="e.g. Virtual Memory"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Explanation (Max 4 lines, clear & plain)
                        </label>
                        <textarea
                          rows={4}
                          value={editExplanation}
                          onChange={(e) => setEditExplanation(e.target.value)}
                          className="w-full text-xs text-slate-800 leading-relaxed px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500 font-sans"
                          placeholder="Provide at most 4 concise lines explaining this concept..."
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">
                          Real-World / Industry Application (Optional)
                        </label>
                        <input
                          type="text"
                          value={editRealWorldUse}
                          onChange={(e) => setEditRealWorldUse(e.target.value)}
                          className="w-full text-xs text-slate-800 px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
                          placeholder="e.g. Used in cloud hypervisors to isolate tenant RAM spaces."
                        />
                      </div>

                      <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200">
                        <button
                          type="button"
                          onClick={cancelEditing}
                          disabled={savingEdit}
                          className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleSaveEdit(topic.id)}
                          disabled={savingEdit}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors shadow-xs disabled:opacity-50"
                        >
                          {savingEdit ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          Save Changes
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Normal Card Display */
                    <div className="p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2.5 flex-wrap">
                            <h3 className="text-base font-bold text-slate-900 tracking-tight">{topic.keyword}</h3>
                            {topic.reviewed ? (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                                <ShieldCheck className="w-3 h-3" /> Reviewed
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                                <Clock className="w-3 h-3" /> Unreviewed
                              </span>
                            )}
                            {topic.source_pages && topic.source_pages.length > 0 && (
                              <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
                                Page{topic.source_pages.length > 1 ? "s" : ""}: {topic.source_pages.join(", ")}
                              </span>
                            )}
                          </div>

                          {/* 1-4 Line Explanation */}
                          <div className="mt-2 text-xs text-slate-700 leading-relaxed whitespace-pre-line font-normal">
                            {topic.explanation}
                          </div>

                          {/* Real-world use note */}
                          {topic.real_world_use && (
                            <div className="mt-2.5 flex items-start gap-1.5 text-[11px] text-indigo-900 bg-indigo-50/70 border border-indigo-100/80 px-2.5 py-1.5 rounded-lg">
                              <Sparkles className="w-3.5 h-3.5 text-indigo-600 shrink-0 mt-0.5" />
                              <div>
                                <span className="font-semibold text-indigo-950">Real-World Application: </span>
                                {topic.real_world_use}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Card Controls */}
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={() => handleToggleReviewed(topic)}
                            className={`p-1.5 rounded-lg text-xs font-medium border transition-colors ${
                              topic.reviewed
                                ? "text-emerald-700 bg-emerald-50 border-emerald-200 hover:bg-emerald-100"
                                : "text-slate-600 bg-white border-slate-200 hover:bg-slate-50"
                            }`}
                            title={topic.reviewed ? "Mark as unreviewed" : "Mark as approved"}
                          >
                            <Check className="w-4 h-4" />
                          </button>

                          <button
                            type="button"
                            onClick={() => startEditing(topic)}
                            className="p-1.5 rounded-lg text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 transition-colors"
                            title="Edit keyword or explanation"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>

                          <button
                            type="button"
                            onClick={() => setDeletingTopicId(topic.id)}
                            className="p-1.5 rounded-lg text-xs font-medium text-rose-600 bg-white border border-rose-200 hover:bg-rose-50 transition-colors"
                            title="Delete topic"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      {/* Delete Confirmation Alert */}
                      {isDeletingPrompt && (
                        <div className="mt-3 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between text-xs animate-in fade-in">
                          <div className="flex items-center gap-2 text-rose-800 font-medium">
                            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                            <span>Remove "{topic.keyword}" from this document and the knowledge graph?</span>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              type="button"
                              onClick={() => setDeletingTopicId(null)}
                              disabled={isDeleting}
                              className="px-2 py-1 text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded font-medium"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteTopic(topic.id)}
                              disabled={isDeleting}
                              className="px-2 py-1 text-white bg-rose-600 hover:bg-rose-700 rounded font-semibold inline-flex items-center gap-1"
                            >
                              {isDeleting ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                              Confirm Delete
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            <span className="font-semibold text-slate-700">Tip:</span> Review takes ~30 seconds. Skipped topics stay
            marked <span className="font-semibold text-amber-700">Unreviewed</span> and are linked conservatively.
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold transition-colors shadow-xs"
          >
            Done Reviewing
          </button>
        </div>
      </div>
    </div>
  );
};

