import React, { useState, useMemo } from "react";
import { Search, ExternalLink, ShieldCheck, Sparkles, BookOpen, Layers, ArrowRight } from "lucide-react";
import { CrossLinkData } from "./CrossLinkDetailModal";

interface CrossSubjectTextListProps {
  links: CrossLinkData[];
  onSelectLink: (link: CrossLinkData) => void;
  minStrength: number;
}

export const CrossSubjectTextList: React.FC<CrossSubjectTextListProps> = ({
  links,
  onSelectLink,
  minStrength,
}) => {
  const [searchTerm, setSearchTerm] = useState("");

  // Filter links by search query
  const filteredLinks = useMemo(() => {
    if (!searchTerm.trim()) return links;
    const q = searchTerm.toLowerCase();
    return links.filter((l) => {
      const src = (l.source_keyword || (typeof l.source === "object" ? l.source?.name : String(l.source))).toLowerCase();
      const tgt = (l.target_keyword || (typeof l.target === "object" ? l.target?.name : String(l.target))).toLowerCase();
      const srcSubj = (l.source_subject_name || "").toLowerCase();
      const tgtSubj = (l.target_subject_name || "").toLowerCase();
      const reason = (l.reason || "").toLowerCase();
      const example = (l.industry_example || "").toLowerCase();
      return (
        src.includes(q) ||
        tgt.includes(q) ||
        srcSubj.includes(q) ||
        tgtSubj.includes(q) ||
        reason.includes(q) ||
        example.includes(q)
      );
    });
  }, [links, searchTerm]);

  // Group links by subject pair
  const groupedByPair = useMemo(() => {
    const groups: Record<string, CrossLinkData[]> = {};
    for (const link of filteredLinks) {
      const s1 = link.source_subject_name || "Subject A";
      const s2 = link.target_subject_name || "Subject B";
      // Canonical alphabetical key for stable grouping
      const pairKey = [s1, s2].sort().join(" ⟷ ");
      if (!groups[pairKey]) {
        groups[pairKey] = [];
      }
      groups[pairKey].push(link);
    }
    return groups;
  }, [filteredLinks]);

  const formatType = (t: string) => {
    switch (t) {
      case "prerequisite_of":
        return "Prerequisite Of";
      case "same_concept":
        return "Same Concept";
      case "applies_in":
        return "Applies In";
      case "contrasts_with":
        return "Contrasts With";
      case "part_of":
        return "Part Of";
      case "example_of":
        return "Example Of";
      default:
        return t.replace(/_/g, " ");
    }
  };

  return (
    <div className="space-y-6">
      {/* Search Header */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-4 bg-slate-900 border border-slate-800 rounded-xl">
        <div className="relative w-full sm:w-96">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search cross-subject concepts, reasons, subjects..."
            className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-700/80 rounded-lg text-sm text-slate-100 placeholder-slate-500 focus:outline-hidden focus:border-indigo-500"
          />
        </div>
        <div className="text-xs text-slate-400 font-medium">
          Showing <span className="font-bold text-indigo-400">{filteredLinks.length}</span> verified cross-subject links (Strength ≥ {minStrength})
        </div>
      </div>

      {/* Empty State */}
      {filteredLinks.length === 0 && (
        <div className="p-12 text-center bg-slate-900/50 border border-slate-800 rounded-2xl">
          <Layers className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <h4 className="text-base font-semibold text-slate-300">No cross-subject links found</h4>
          <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
            {searchTerm
              ? `No connections matched your query "${searchTerm}". Try another keyword.`
              : `No cross-subject bridges met the strength threshold of ${minStrength}. Lower the strength filter to view more connections.`}
          </p>
        </div>
      )}

      {/* Grouped Link Cards */}
      {Object.entries(groupedByPair).map(([pairName, pairLinks]) => (
        <div key={pairName} className="space-y-3">
          <div className="flex items-center gap-2 px-1">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
            <h3 className="text-sm font-bold text-slate-200 tracking-wide">
              {pairName}
            </h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700">
              {pairLinks.length} {pairLinks.length === 1 ? "bridge" : "bridges"}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3.5">
            {pairLinks.map((link) => {
              const srcKeyword =
                link.source_keyword ||
                (typeof link.source === "object" ? link.source?.name : String(link.source));
              const tgtKeyword =
                link.target_keyword ||
                (typeof link.target === "object" ? link.target?.name : String(link.target));

              const srcSubj =
                link.source_subject_name ||
                (typeof link.source === "object" ? link.source?.subject_name : "Subject A");
              const tgtSubj =
                link.target_subject_name ||
                (typeof link.target === "object" ? link.target?.subject_name : "Subject B");

              const snippetA =
                link.snippet_a ||
                (link.evidence && link.evidence.length > 0 ? link.evidence[0].snippet : null);
              const snippetB =
                link.snippet_b ||
                (link.evidence && link.evidence.length > 1 ? link.evidence[1].snippet : null);

              return (
                <div
                  key={link.id}
                  onClick={() => onSelectLink(link)}
                  className="group p-5 bg-slate-900/80 hover:bg-slate-850 border border-slate-800 hover:border-indigo-500/50 rounded-xl transition duration-150 cursor-pointer shadow-md hover:shadow-indigo-500/5 flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    {/* Header: Concept Bridge */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                      <div className="flex items-center flex-wrap gap-2 text-sm">
                        <span className="px-2.5 py-1 rounded-md bg-cyan-950/80 text-cyan-300 font-semibold border border-cyan-800/60">
                          {srcKeyword}
                        </span>
                        <span className="text-xs text-slate-500 font-normal">({srcSubj})</span>

                        <span className="text-indigo-400 font-bold px-1 flex items-center">
                          <ArrowRight className="w-3.5 h-3.5" />
                        </span>

                        <span className="px-2.5 py-1 rounded-md bg-purple-950/80 text-purple-300 font-semibold border border-purple-800/60">
                          {tgtKeyword}
                        </span>
                        <span className="text-xs text-slate-500 font-normal">({tgtSubj})</span>
                      </div>

                      {/* Badges */}
                      <div className="flex items-center gap-2 self-start sm:self-center">
                        <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-medium">
                          {formatType(link.type)}
                        </span>
                        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 font-medium">
                          {"★".repeat(link.strength)}
                        </span>
                        {link.locked && (
                          <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1">
                            <ShieldCheck className="w-3 h-3" />
                            Locked
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Connection Reason */}
                    <p className="text-sm text-slate-300 leading-relaxed">
                      {link.reason}
                    </p>

                    {/* Industry Example */}
                    {link.industry_example && (
                      <div className="flex items-start gap-2 p-3 rounded-lg bg-slate-950/50 border border-slate-800/60 text-xs text-slate-300">
                        <Sparkles className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-amber-300">Industry Application: </span>
                          <span>{link.industry_example}</span>
                        </div>
                      </div>
                    )}

                    {/* Verbatim Dual Snippets */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
                      {snippetA && (
                        <div className="p-2.5 bg-cyan-950/30 border border-cyan-900/40 rounded-lg text-xs text-slate-400">
                          <div className="text-[11px] font-medium text-cyan-400 mb-1">
                            Quote from {srcSubj}:
                          </div>
                          <span className="italic text-slate-300">"{snippetA}"</span>
                        </div>
                      )}
                      {snippetB && (
                        <div className="p-2.5 bg-purple-950/30 border border-purple-900/40 rounded-lg text-xs text-slate-400">
                          <div className="text-[11px] font-medium text-purple-400 mb-1">
                            Quote from {tgtSubj}:
                          </div>
                          <span className="italic text-slate-300">"{snippetB}"</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card Action Hint */}
                  <div className="mt-3 pt-2 flex items-center justify-end text-xs text-slate-500 group-hover:text-indigo-400 transition font-medium">
                    <span className="flex items-center gap-1">
                      Click to inspect in detail <ExternalLink className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

