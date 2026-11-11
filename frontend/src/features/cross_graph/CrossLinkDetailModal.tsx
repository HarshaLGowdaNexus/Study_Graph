import React from "react";
import { X, ExternalLink, ShieldCheck, Sparkles, BookOpen, Layers } from "lucide-react";

export interface CrossLinkEvidence {
  chunk_id?: string | null;
  snippet: string;
}

export interface CrossLinkData {
  id: string;
  source: string | any;
  target: string | any;
  source_keyword?: string;
  target_keyword?: string;
  source_subject_id?: string;
  target_subject_id?: string;
  source_subject_name?: string;
  target_subject_name?: string;
  type: string;
  reason: string;
  industry_example: string;
  strength: number;
  scope: string;
  status?: string;
  locked?: boolean;
  evidence?: CrossLinkEvidence[];
  snippet_a?: string | null;
  snippet_b?: string | null;
}

interface CrossLinkDetailModalProps {
  link: CrossLinkData | null;
  onClose: () => void;
}

export const CrossLinkDetailModal: React.FC<CrossLinkDetailModalProps> = ({ link, onClose }) => {
  if (!link) return null;

  // Helper to extract display names when source/target might be node objects or strings
  const sourceKeyword =
    link.source_keyword ||
    (typeof link.source === "object" ? link.source?.keyword || link.source?.name : String(link.source));
  const targetKeyword =
    link.target_keyword ||
    (typeof link.target === "object" ? link.target?.keyword || link.target?.name : String(link.target));

  const sourceSubj =
    link.source_subject_name ||
    (typeof link.source === "object" ? link.source?.subject_name : "Subject A");
  const targetSubj =
    link.target_subject_name ||
    (typeof link.target === "object" ? link.target?.subject_name : "Subject B");

  // Format link type for clean display
  const formatType = (t: string) => {
    switch (t) {
      case "prerequisite_of":
        return "Prerequisite Of";
      case "same_concept":
        return "Same Concept Across Disciplines";
      case "applies_in":
        return "Applies In Practical Domain";
      case "contrasts_with":
        return "Contrasts With";
      case "part_of":
        return "Part Of Larger Architecture";
      case "example_of":
        return "Concrete Example Of";
      default:
        return t.replace(/_/g, " ");
    }
  };

  const snippetA =
    link.snippet_a ||
    (link.evidence && link.evidence.length > 0 ? link.evidence[0].snippet : null);
  const snippetB =
    link.snippet_b ||
    (link.evidence && link.evidence.length > 1 ? link.evidence[1].snippet : null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto text-slate-100 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-800 bg-slate-950/60 sticky top-0 backdrop-blur-sm z-10">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-400/30 flex items-center justify-center text-indigo-400">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
                Cross-Subject Bridge
              </span>
              <h3 className="text-base font-bold text-white leading-tight">
                {sourceKeyword} <span className="text-slate-400 font-normal">↔</span> {targetKeyword}
              </h3>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800 transition"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-5">
          {/* Subjects Bridge Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3.5 bg-slate-800/60 border border-slate-700/60 rounded-xl items-center">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#38bdf8]" />
              <div className="text-xs">
                <div className="text-slate-400">Origin Subject</div>
                <div className="font-semibold text-cyan-200">{sourceSubj}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 sm:justify-end">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-400 shadow-[0_0_8px_#c084fc]" />
              <div className="text-xs sm:text-right">
                <div className="text-slate-400">Connected Subject</div>
                <div className="font-semibold text-purple-200">{targetSubj}</div>
              </div>
            </div>
          </div>

          {/* Relationship Metadata Badges */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            <span className="px-3 py-1 bg-indigo-500/20 text-indigo-300 font-medium rounded-full border border-indigo-500/40">
              {formatType(link.type)}
            </span>
            <span className="px-3 py-1 bg-amber-500/20 text-amber-300 font-medium rounded-full border border-amber-500/40 flex items-center gap-1">
              <span>Strength:</span>
              <span className="font-bold">{"★".repeat(link.strength || 3)}</span>
              <span className="text-amber-500/60">{"★".repeat(Math.max(0, 5 - (link.strength || 3)))}</span>
            </span>
            {link.locked && (
              <span className="px-2.5 py-1 bg-emerald-500/20 text-emerald-300 rounded-full border border-emerald-500/40 flex items-center gap-1 font-medium">
                <ShieldCheck className="w-3.5 h-3.5" />
                Verified & Locked
              </span>
            )}
          </div>

          {/* Reasoning */}
          <div className="bg-slate-950/40 border border-slate-800 p-4 rounded-xl">
            <div className="text-xs font-semibold text-indigo-300 mb-1 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5" />
              Cross-Disciplinary Connection Reason
            </div>
            <p className="text-sm text-slate-200 leading-relaxed">
              {link.reason || "No explicit reason recorded."}
            </p>
          </div>

          {/* Industry Example */}
          {link.industry_example && (
            <div className="bg-slate-950/40 border border-slate-800 p-4 rounded-xl">
              <div className="text-xs font-semibold text-amber-300 mb-1 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5" />
                Real-World & Industry Application
              </div>
              <p className="text-sm text-slate-200 leading-relaxed">
                {link.industry_example}
              </p>
            </div>
          )}

          {/* Evidence Quotes From BOTH Subjects */}
          <div className="space-y-3">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
              <span>Verbatim Evidence From Both Subjects (Golden Rule 1 & Risk R19)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Snippet A */}
              <div className="p-3.5 bg-slate-950/60 border border-cyan-900/40 rounded-xl flex flex-col justify-between">
                <div className="text-[11px] font-semibold text-cyan-400 mb-1.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                  From {sourceSubj}:
                </div>
                <blockquote className="text-xs text-slate-300 italic border-l-2 border-cyan-500/60 pl-2.5 py-0.5 leading-relaxed">
                  "{snippetA || "Evidence snippet verified during ingestion."}"
                </blockquote>
              </div>

              {/* Snippet B */}
              <div className="p-3.5 bg-slate-950/60 border border-purple-900/40 rounded-xl flex flex-col justify-between">
                <div className="text-[11px] font-semibold text-purple-400 mb-1.5 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
                  From {targetSubj}:
                </div>
                <blockquote className="text-xs text-slate-300 italic border-l-2 border-purple-500/60 pl-2.5 py-0.5 leading-relaxed">
                  "{snippetB || "Evidence snippet verified during ingestion."}"
                </blockquote>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
          <span>Scope: Cross-Subject Bridge • Feature F12</span>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white font-medium rounded-lg transition"
          >
            Close Details
          </button>
        </div>
      </div>
    </div>
  );
};

