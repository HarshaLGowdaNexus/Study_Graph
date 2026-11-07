import React, { useState } from "react";
import { FileText, ExternalLink, X, BookOpen, Sparkles } from "lucide-react";

export interface CitationItemData {
  document_id: string;
  filename: string;
  page: number;
  snippet: string;
  similarity: number;
}

interface CitationBadgeProps {
  citation: CitationItemData;
}

export const CitationBadge: React.FC<CitationBadgeProps> = ({ citation }) => {
  const [isOpen, setIsOpen] = useState(false);

  // Shorten filename if it's very long
  const displayFilename =
    citation.filename.length > 24
      ? citation.filename.substring(0, 22) + "..."
      : citation.filename;

  const similarityPercent = Math.round(citation.similarity * 100);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full 
                   bg-indigo-50 border border-indigo-200 text-indigo-700 
                   hover:bg-indigo-100 hover:border-indigo-300 transition-all cursor-pointer shadow-2xs group"
        title="Click to view supporting note excerpt"
      >
        <FileText className="w-3 h-3 text-indigo-500 group-hover:text-indigo-700 transition" />
        <span className="font-medium truncate max-w-[150px]">{displayFilename}</span>
        <span className="bg-indigo-200/70 text-indigo-800 text-[10px] px-1.5 py-0.2 rounded-full font-bold">
          p. {citation.page}
        </span>
      </button>

      {/* Popover / Modal for Verbatim Snippet */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
          <div
            className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="bg-slate-50 px-5 py-3.5 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-100 text-indigo-700 rounded-lg">
                  <BookOpen className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                    Verified Note Citation
                    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                      {similarityPercent}% match
                    </span>
                  </h4>
                  <p className="text-xs text-slate-500 truncate max-w-sm">
                    {citation.filename} &bull; Page {citation.page}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Content - Verbatim Snippet */}
            <div className="p-5 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                Supporting Note Snippet
              </div>
              <blockquote className="text-sm text-slate-700 italic bg-amber-50/60 border-l-4 border-amber-400 p-3.5 rounded-r-lg leading-relaxed">
                "{citation.snippet}"
              </blockquote>
              <p className="text-xs text-slate-500">
                This exact excerpt was retrieved from your uploaded study document to ground the answer and prevent hallucination.
              </p>
            </div>

            {/* Modal Footer */}
            <div className="bg-slate-50 px-5 py-3 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setIsOpen(false)}
                className="px-3.5 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

