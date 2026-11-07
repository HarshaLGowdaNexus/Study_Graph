import React, { useEffect, useRef } from "react";
import { Briefcase, AlertCircle, Bookmark, Layers, Link as LinkIcon } from "lucide-react";
import { LinkChip, TheoryLinkChipData } from "./LinkChip";

export interface TheoryTopicCardData {
  id: string;
  subject_id: string;
  keyword: string;
  explanation: string;
  real_world_use?: string;
  module_no: number;
  reviewed: boolean;
  cluster_label?: string;
  links: TheoryLinkChipData[];
}

interface TopicCardProps {
  card: TheoryTopicCardData;
  showWeakLinks: boolean;
  isHighlighted: boolean;
  onJump: (targetTopicId: string) => void;
}

export const TopicCard: React.FC<TopicCardProps> = ({
  card,
  showWeakLinks,
  isHighlighted,
  onJump,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);

  // Filter links based on weak link toggle
  const visibleLinks = card.links.filter(
    (l) => showWeakLinks || !l.is_weak
  );

  // Split explanation lines cleanly
  const explanationLines = (card.explanation || "")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .slice(0, 4); // Enforce max 4 lines (Rule 13.3)

  // Scroll into view when highlighted
  useEffect(() => {
    if (isHighlighted && cardRef.current) {
      cardRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [isHighlighted]);

  return (
    <div
      ref={cardRef}
      id={`topic-${card.id}`}
      className={`rounded-xl border bg-white p-5 shadow-xs transition-all duration-300 relative ${
        isHighlighted
          ? "ring-4 ring-amber-400 border-amber-500 shadow-lg scale-[1.01] bg-amber-50/20"
          : "border-slate-200 hover:border-slate-300 hover:shadow-sm"
      }`}
    >
      {/* Top Header: Keyword, Cluster & Review status */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-bold text-slate-900 text-base tracking-tight">
              {card.keyword}
            </h3>

            {/* Unreviewed Badge (Rule 13.9) */}
            {!card.reviewed ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                <AlertCircle className="w-3 h-3 text-amber-500" />
                Unreviewed
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                Reviewed
              </span>
            )}
          </div>

          {/* Cluster / Community Category */}
          {card.cluster_label && (
            <div className="flex items-center gap-1 text-[11px] text-slate-500 font-medium">
              <Layers className="w-3 h-3 text-slate-400" />
              <span>{card.cluster_label}</span>
            </div>
          )}
        </div>

        {/* Module Badge */}
        <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-600 text-xs font-semibold shrink-0 border border-slate-200">
          Mod {card.module_no}
        </span>
      </div>

      {/* Short 1-4 Line Explanation (Concept understanding, not rote) */}
      <div className="text-slate-700 text-sm leading-relaxed mb-3.5 bg-slate-50/70 p-3 rounded-lg border border-slate-100/80">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-1">
          <Bookmark className="w-3.5 h-3.5 text-indigo-500" />
          <span>Core Concept</span>
        </div>
        <ul className="space-y-1 list-disc list-inside text-slate-700">
          {explanationLines.map((line, idx) => (
            <li key={idx} className="text-xs sm:text-sm">
              {line.replace(/^[•\-\*]\s*/, "")}
            </li>
          ))}
        </ul>
      </div>

      {/* Real-World Use Line (Answers 'Why am I learning this?') */}
      {card.real_world_use && (
        <div className="flex items-start gap-2 text-xs text-slate-600 mb-4 bg-emerald-50/40 p-2.5 rounded-lg border border-emerald-100/60">
          <Briefcase className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-emerald-800">Industry Application: </span>
            <span className="text-slate-700">{card.real_world_use}</span>
          </div>
        </div>
      )}

      {/* Linked To Chips Section */}
      <div className="pt-3 border-t border-slate-100">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1 text-xs font-semibold text-slate-600">
            <LinkIcon className="w-3 h-3 text-indigo-500" />
            <span>Connected Concepts</span>
            <span className="text-[10px] text-slate-400 font-normal">
              ({visibleLinks.length})
            </span>
          </div>

          {/* Cross-Module count indicator */}
          {visibleLinks.some((l) => l.is_cross_module) && (
            <span className="text-[10px] font-semibold text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-100">
              Cross-Module Links
            </span>
          )}
        </div>

        {visibleLinks.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {visibleLinks.map((link) => (
              <LinkChip
                key={`${link.edge_id}-${link.direction}-${link.target_topic_id}`}
                chip={link}
                onJump={onJump}
              />
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400 italic">
            {card.links.length > 0
              ? "All links for this topic are weak (toggle 'Show weak links' above)."
              : "No verified links discovered yet for this concept."}
          </p>
        )}
      </div>
    </div>
  );
};

