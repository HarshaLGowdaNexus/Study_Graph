import React, { useState } from "react";
import {
  X,
  Link as LinkIcon,
  Quote,
  ShieldCheck,
  Edit3,
  Trash2,
  Check,
  AlertTriangle,
  Sparkles,
  ArrowRight,
  Info,
} from "lucide-react";

export interface GraphLinkEvidence {
  chunk_id?: string | null;
  snippet: string;
}

export interface GraphLinkData {
  id: string;
  source: any; // string ID or object with id, keyword
  target: any; // string ID or object with id, keyword
  type: string;
  reason: string;
  industry_example?: string;
  strength: number; // 1-5
  scope?: string;
  status?: string;
  locked?: boolean;
  graph_version?: number;
  evidence?: GraphLinkEvidence[];
}

interface LinkDetailPanelProps {
  link: GraphLinkData | null;
  onClose: () => void;
  onLinkUpdated: (updatedLink: GraphLinkData) => void;
  onLinkDeleted: (deletedLinkId: string) => void;
  userAuthHeaders?: Record<string, string>;
}

const TYPE_CONFIG: Record<string, { label: string; bg: string; text: string; border: string }> = {
  prerequisite_of: { label: "Prerequisite Of", bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200" },
  same_concept: { label: "Same Concept", bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
  part_of: { label: "Part Of", bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200" },
  contrasts_with: { label: "Contrasts With", bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  applies_in: { label: "Applies In", bg: "bg-cyan-50", text: "text-cyan-700", border: "border-cyan-200" },
  example_of: { label: "Example Of", bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200" },
};

export const LinkDetailPanel: React.FC<LinkDetailPanelProps> = ({
  link,
  onClose,
  onLinkUpdated,
  onLinkDeleted,
  userAuthHeaders = {},
}) => {
  if (!link) return null;

  const [isEditing, setIsEditing] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Edit form state
  const [editType, setEditType] = useState(link.type || "prerequisite_of");
  const [editReason, setEditReason] = useState(link.reason || "");
  const [editExample, setEditExample] = useState(link.industry_example || "");
  const [editStrength, setEditStrength] = useState<number>(link.strength || 3);

  // Get source and target display names
  const sourceName = typeof link.source === "object" ? link.source.keyword || link.source.name || link.source.id : link.source;
  const targetName = typeof link.target === "object" ? link.target.keyword || link.target.name || link.target.id : link.target;
  const typeStyle = TYPE_CONFIG[link.type] || {
    label: link.type,
    bg: "bg-slate-50",
    text: "text-slate-700",
    border: "border-slate-200",
  };

  const handleSaveEdit = async () => {
    if (!editReason.trim()) {
      setError("Link reason cannot be blank.");
      return;
    }
    setSubmitting(true);
    setError(null);

    // If it's a synthetic benchmark link, simulate local persistence
    if (link.id.startsWith("syn-edge-")) {
      const updated: GraphLinkData = {
        ...link,
        type: editType,
        reason: editReason,
        industry_example: editExample,
        strength: editStrength,
        locked: true,
        status: "edited",
      };
      onLinkUpdated(updated);
      setIsEditing(false);
      setSubmitting(false);
      return;
    }

    try {
      const res = await fetch(`/api/edges/${link.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...userAuthHeaders,
        },
        body: JSON.stringify({
          type: editType,
          reason: editReason,
          industry_example: editExample,
          strength: editStrength,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to update link.");
      }

      const updatedRow = await res.json();
      const updated: GraphLinkData = {
        ...link,
        type: updatedRow.type,
        reason: updatedRow.reason,
        industry_example: updatedRow.industry_example,
        strength: updatedRow.strength,
        locked: true,
        status: "edited",
      };
      onLinkUpdated(updated);
      setIsEditing(false);
    } catch (err: any) {
      setError(err.message || "Failed to edit link.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    setSubmitting(true);
    setError(null);

    // If it's a synthetic benchmark link, simulate local deletion
    if (link.id.startsWith("syn-edge-")) {
      onLinkDeleted(link.id);
      setIsDeleting(false);
      setSubmitting(false);
      onClose();
      return;
    }

    try {
      const res = await fetch(`/api/edges/${link.id}`, {
        method: "DELETE",
        headers: {
          ...userAuthHeaders,
        },
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Failed to delete link.");
      }

      onLinkDeleted(link.id);
      setIsDeleting(false);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to delete link.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-[420px] bg-white border-l border-slate-200 shadow-2xl z-30 flex flex-col transform transition-transform duration-300 ease-out">
      {/* Header */}
      <div className="p-5 border-b border-slate-100 flex items-start justify-between bg-slate-50">
        <div className="space-y-1.5 pr-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-2 py-0.5 text-xs font-bold rounded border ${typeStyle.bg} ${typeStyle.text} ${typeStyle.border}`}
            >
              {typeStyle.label}
            </span>
            <span className="px-2 py-0.5 text-xs font-semibold rounded bg-slate-200 text-slate-700">
              Strength {link.strength}/5
            </span>
            {link.locked && (
              <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-bold rounded bg-emerald-100 text-emerald-800">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                Locked (Sacred)
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-sm font-bold text-slate-900 mt-2">
            <span className="truncate max-w-[150px]">{sourceName}</span>
            <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
            <span className="truncate max-w-[150px]">{targetName}</span>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition"
          title="Close panel"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 text-sm">
        {error && (
          <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {isEditing ? (
          /* Inline Edit Form (Task T10) */
          <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200 text-xs font-bold text-slate-700">
              <span className="flex items-center gap-1.5">
                <Edit3 className="w-3.5 h-3.5 text-indigo-600" />
                Edit Link Attributes
              </span>
              <span className="text-slate-400 font-normal">T10 Rule 2 Lock Guard</span>
            </div>

            {/* Type selector */}
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Relationship Type
              </label>
              <select
                value={editType}
                onChange={(e) => setEditType(e.target.value)}
                className="w-full text-xs p-2 bg-white border border-slate-300 rounded-md shadow-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              >
                {Object.keys(TYPE_CONFIG).map((k) => (
                  <option key={k} value={k}>
                    {TYPE_CONFIG[k].label}
                  </option>
                ))}
              </select>
            </div>

            {/* Strength slider */}
            <div>
              <div className="flex justify-between text-xs font-semibold text-slate-600 mb-1">
                <span>Strength (1 to 5)</span>
                <span className="font-bold text-indigo-600">{editStrength}/5</span>
              </div>
              <input
                type="range"
                min="1"
                max="5"
                step="1"
                value={editStrength}
                onChange={(e) => setEditStrength(parseInt(e.target.value))}
                className="w-full accent-indigo-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
                <span>1 (Weakest)</span>
                <span>3 (Moderate)</span>
                <span>5 (Strongest)</span>
              </div>
            </div>

            {/* Reason */}
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Reason (Why they connect)
              </label>
              <textarea
                rows={3}
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                className="w-full text-xs p-2 bg-white border border-slate-300 rounded-md shadow-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            {/* Industry Example */}
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Industry / Real-World Example
              </label>
              <textarea
                rows={2}
                value={editExample}
                onChange={(e) => setEditExample(e.target.value)}
                className="w-full text-xs p-2 bg-white border border-slate-300 rounded-md shadow-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSaveEdit}
                disabled={submitting}
                className="flex-1 py-2 px-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg text-xs font-bold flex items-center justify-center gap-1.5 shadow-sm transition"
              >
                <Check className="w-3.5 h-3.5" />
                {submitting ? "Saving..." : "Save & Lock"}
              </button>
              <button
                onClick={() => setIsEditing(false)}
                disabled={submitting}
                className="py-2 px-3 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 rounded-lg text-xs font-medium transition"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          /* View Mode */
          <div className="space-y-4">
            {/* Visual Strength Meter */}
            <div className="bg-slate-50 rounded-xl p-3.5 border border-slate-200 space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-600">
                <span>Link Strength & Line Thickness:</span>
                <span className="font-bold text-slate-900">{link.strength} / 5</span>
              </div>
              <div className="flex gap-1.5 h-2">
                {[1, 2, 3, 4, 5].map((lvl) => (
                  <div
                    key={lvl}
                    className={`flex-1 rounded-full transition-colors ${
                      lvl <= link.strength ? "bg-indigo-600" : "bg-slate-200"
                    }`}
                  />
                ))}
              </div>
              <p className="text-[11px] text-slate-500 italic">
                {link.strength >= 4
                  ? "Strong fundamental relationship; shown prominent in graph."
                  : link.strength >= 3
                  ? "Moderate conceptual overlap; visible by default."
                  : "Weak contextual link; hidden when weak links are filtered."}
              </p>
            </div>

            {/* Why This Link Exists */}
            <div className="bg-white rounded-xl p-4 border border-slate-200 shadow-2xs space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-900 uppercase tracking-wider">
                <Info className="w-3.5 h-3.5 text-indigo-600" />
                <span>Connection Reason</span>
              </div>
              <p className="text-slate-800 leading-relaxed text-sm">
                {link.reason || "No explicit reason specified."}
              </p>
            </div>

            {/* Industry Application */}
            {link.industry_example && (
              <div className="bg-emerald-50/50 rounded-xl p-4 border border-emerald-100/80 space-y-2">
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-900 uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Industry / Practical Example</span>
                </div>
                <p className="text-slate-800 leading-relaxed text-sm">
                  {link.industry_example}
                </p>
              </div>
            )}

            {/* Verbatim Source Evidence (RULEBOOK 13.1) */}
            <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 space-y-2.5">
              <div className="flex items-center justify-between text-xs font-bold text-slate-700">
                <span className="flex items-center gap-1.5">
                  <Quote className="w-3.5 h-3.5 text-indigo-500" />
                  Verbatim Source Snippets
                </span>
                <span className="text-[10px] text-slate-400">Rule 13.1 Grounding</span>
              </div>

              {link.evidence && link.evidence.length > 0 ? (
                <div className="space-y-2">
                  {link.evidence.map((ev, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg bg-white border border-slate-200/80 text-xs text-slate-700 leading-relaxed italic"
                    >
                      "{ev.snippet}"
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">No source evidence snippets attached.</p>
              )}
            </div>

            {/* Action Bar (Edit / Delete) */}
            <div className="pt-2 flex gap-2">
              <button
                onClick={() => setIsEditing(true)}
                className="flex-1 py-2 px-3 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 text-indigo-700 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition"
              >
                <Edit3 className="w-3.5 h-3.5" />
                Edit Link (T10)
              </button>

              <button
                onClick={() => setIsDeleting(true)}
                className="py-2 px-3 bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition"
                title="Soft delete link"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal Overlay */}
        {isDeleting && (
          <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-rose-900">
              <AlertTriangle className="w-4 h-4 text-rose-600" />
              <span>Confirm Link Deletion</span>
            </div>
            <p className="text-xs text-rose-800 leading-relaxed">
              This will remove the connection and mark it as locked-deleted. It will never be automatically recreated on future uploads (Rule 13.2).
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleDelete}
                disabled={submitting}
                className="flex-1 py-1.5 px-3 bg-rose-600 hover:bg-rose-700 text-white rounded-md text-xs font-bold transition disabled:opacity-50"
              >
                {submitting ? "Deleting..." : "Yes, Delete Link"}
              </button>
              <button
                onClick={() => setIsDeleting(false)}
                disabled={submitting}
                className="py-1.5 px-3 bg-white border border-rose-200 text-rose-700 rounded-md text-xs font-semibold transition"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
        <span>Link ID: {link.id.slice(0, 12)}...</span>
        <button
          onClick={onClose}
          className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 rounded-md font-medium text-slate-700 transition"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};

