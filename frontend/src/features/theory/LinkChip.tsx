import React, { useState } from "react";
import { ArrowUpRight, ArrowDownLeft, Zap, Info, Star } from "lucide-react";

export interface TheoryLinkChipData {
  edge_id: string;
  target_topic_id: string;
  target_keyword: string;
  target_module_no: number;
  target_subject_name?: string;
  type: string;
  reason: string;
  industry_example?: string;
  strength: number;
  is_cross_module: boolean;
  is_cross_subject: boolean;
  is_weak: boolean;
  direction: "outgoing" | "incoming";
}

interface LinkChipProps {
  chip: TheoryLinkChipData;
  onJump: (targetTopicId: string) => void;
}

const TYPE_CONFIG: Record<
  string,
  { label: string; badgeBg: string; text: string; border: string }
> = {
  prerequisite_of: {
    label: "Prerequisite",
    badgeBg: "bg-purple-50",
    text: "text-purple-700",
    border: "border-purple-200",
  },
  applies_in: {
    label: "Applies In",
    badgeBg: "bg-blue-50",
    text: "text-blue-700",
    border: "border-blue-200",
  },
  example_of: {
    label: "Example",
    badgeBg: "bg-emerald-50",
    text: "text-emerald-700",
    border: "border-emerald-200",
  },
  same_concept: {
    label: "Same Concept",
    badgeBg: "bg-cyan-50",
    text: "text-cyan-700",
    border: "border-cyan-200",
  },
  part_of: {
    label: "Part Of",
    badgeBg: "bg-amber-50",
    text: "text-amber-700",
    border: "border-amber-200",
  },
  contrasts_with: {
    label: "Contrasts",
    badgeBg: "bg-rose-50",
    text: "text-rose-700",
    border: "border-rose-200",
  },
};

export const LinkChip: React.FC<LinkChipProps> = ({ chip, onJump }) => {
  const [showTooltip, setShowTooltip] = useState(false);

  const typeConfig = TYPE_CONFIG[chip.type] || {
    label: chip.type.replace(/_/g, " "),
    badgeBg: "bg-slate-100",
    text: "text-slate-700",
    border: "border-slate-200",
  };

  return (
    <div className="relative inline-block">
      <button
        onClick={() => onJump(chip.target_topic_id)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={`group flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-all text-left shadow-2xs ${
          chip.is_weak
            ? "bg-slate-50 border-dashed border-slate-300 text-slate-500 hover:border-slate-400 hover:bg-slate-100"
            : `${typeConfig.badgeBg} ${typeConfig.border} ${typeConfig.text} hover:shadow-xs hover:scale-[1.02]`
        }`}
        title={`Click to jump to ${chip.target_keyword} (Module ${chip.target_module_no})`}
      >
        {/* Direction arrow */}
        {chip.direction === "outgoing" ? (
          <ArrowUpRight className="w-3 h-3 shrink-0 opacity-70 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
        ) : (
          <ArrowDownLeft className="w-3 h-3 shrink-0 opacity-70 group-hover:-translate-x-0.5 group-hover:translate-y-0.5 transition-transform" />
        )}

        {/* Cross-Module / Cross-Subject Badge */}
        {chip.is_cross_module && (
          <span className="inline-flex items-center gap-0.5 px-1 py-0.2 bg-white/80 rounded text-[10px] font-bold text-indigo-700 border border-indigo-200 shrink-0">
            <Zap className="w-2.5 h-2.5 text-amber-500" />
            M{chip.target_module_no}
          </span>
        )}

        {/* Relationship Type */}
        <span className="font-semibold">{typeConfig.label}:</span>

        {/* Target Keyword */}
        <span className="underline decoration-dotted underline-offset-2 font-bold max-w-[130px] truncate">
          {chip.target_keyword}
        </span>

        {/* Strength stars / dot */}
        <span className="text-[10px] opacity-75 flex items-center gap-0.5 font-normal ml-0.5">
          <Star className="w-2.5 h-2.5 fill-current opacity-80" />
          {chip.strength}
        </span>
      </button>

      {/* Hover Reason Card */}
      {showTooltip && (
        <div className="absolute z-30 bottom-full left-0 mb-2 w-64 p-2.5 bg-slate-900 text-white rounded-lg shadow-xl text-xs pointer-events-none animate-in fade-in duration-150">
          <div className="flex items-start gap-1.5 mb-1 font-semibold text-slate-200">
            <Info className="w-3.5 h-3.5 text-indigo-400 shrink-0 mt-0.5" />
            <span>Why this is linked:</span>
          </div>
          <p className="text-slate-300 leading-relaxed italic">
            "{chip.reason}"
          </p>
          {chip.industry_example && (
            <div className="mt-1.5 pt-1.5 border-t border-slate-800 text-[11px] text-emerald-400">
              <span className="font-bold text-slate-400">Industry: </span>
              {chip.industry_example}
            </div>
          )}
          <div className="mt-1 text-[10px] text-slate-400 flex justify-between">
            <span>Module {chip.target_module_no}</span>
            <span className="text-indigo-300 font-medium">Click chip to scroll &rarr;</span>
          </div>
        </div>
      )}
    </div>
  );
};

