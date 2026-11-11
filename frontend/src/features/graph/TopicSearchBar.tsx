import React, { useEffect, useRef, useState } from "react";
import { Search, X, Loader2, Tag, Layers } from "lucide-react";
import {
  RawGraphNode,
  SearchTopicSuggestion,
  matchLocalTopics,
  mergeSearchSuggestions,
} from "./focusSearchUtils";

interface TopicSearchBarProps {
  localNodes: RawGraphNode[];
  subjectId?: string;
  authHeaders?: Record<string, string>;
  onSelectTopic: (suggestion: SearchTopicSuggestion) => void;
  onClearFocus?: () => void;
  activeFocusKeyword?: string | null;
  placeholder?: string;
  variant?: "light" | "dark";
}

export const TopicSearchBar: React.FC<TopicSearchBarProps> = ({
  localNodes,
  subjectId,
  authHeaders,
  onSelectTopic,
  onClearFocus,
  activeFocusKeyword,
  placeholder = "Search topic or alias (e.g. Module 4 concept, 3-way handshake)...",
  variant = "light",
}) => {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<SearchTopicSuggestion[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  // Debounced live search merging instant local matches + PostgreSQL alias search
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSuggestions([]);
      setIsOpen(false);
      setLoading(false);
      return;
    }

    const instantLocal = matchLocalTopics(localNodes, trimmed, 10);
    setSuggestions(instantLocal);
    setIsOpen(true);
    setActiveIndex(-1);

    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q: trimmed, limit: "10" });
        if (subjectId) params.set("subject_id", subjectId);

        const res = await fetch(`/api/topics/search?${params.toString()}`, {
          headers: authHeaders || {},
        });
        if (res.ok) {
          const remote: SearchTopicSuggestion[] = await res.json();
          setSuggestions(mergeSearchSuggestions(remote, instantLocal, 10));
        }
      } catch {
        // Keep instant local matches if server is unreachable or offline
      } finally {
        setLoading(false);
      }
    }, 180);

    return () => clearTimeout(timer);
  }, [query, localNodes, subjectId, authHeaders]);

  const handleChoose = (item: SearchTopicSuggestion) => {
    setQuery(item.keyword);
    setIsOpen(false);
    setActiveIndex(-1);
    onSelectTopic(item);
  };

  const handleClear = () => {
    setQuery("");
    setSuggestions([]);
    setIsOpen(false);
    setActiveIndex(-1);
    onClearFocus?.();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen || suggestions.length === 0) {
      if (e.key === "Escape") setIsOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? suggestions.length - 1 : prev - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = activeIndex >= 0 ? suggestions[activeIndex] : suggestions[0];
      if (target) handleChoose(target);
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  const isDark = variant === "dark";

  return (
    <div ref={containerRef} className="relative w-full">
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-xl border transition ${
          isDark
            ? "bg-slate-950 border-slate-700/80 focus-within:border-indigo-500 text-slate-100"
            : "bg-slate-50 border-slate-300 focus-within:border-indigo-500 focus-within:bg-white text-slate-900"
        }`}
      >
        <Search className={`w-4 h-4 shrink-0 ${isDark ? "text-indigo-400" : "text-slate-400"}`} />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (query.trim().length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label="Search topic or alias"
          className="w-full bg-transparent text-xs sm:text-sm focus:outline-none placeholder:text-slate-400"
        />

        {loading && <Loader2 className="w-4 h-4 animate-spin text-indigo-500 shrink-0" />}

        {(query || activeFocusKeyword) && (
          <button
            type="button"
            onClick={handleClear}
            className={`p-1 rounded-md transition shrink-0 ${
              isDark
                ? "text-slate-400 hover:text-white hover:bg-slate-800"
                : "text-slate-400 hover:text-slate-700 hover:bg-slate-200/70"
            }`}
            title="Clear search and return to full graph"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Autocomplete Suggestions Dropdown */}
      {isOpen && query.trim().length > 0 && (
        <div
          className={`absolute left-0 right-0 mt-1.5 rounded-xl border shadow-2xl z-40 max-h-80 overflow-y-auto ${
            isDark
              ? "bg-slate-900 border-slate-700 text-slate-100"
              : "bg-white border-slate-200 text-slate-900"
          }`}
        >
          {suggestions.length === 0 ? (
            <div className="p-4 text-center text-xs text-slate-400">
              {loading
                ? "Searching topics and aliases..."
                : `No topic or alias matched "${query.trim()}".`}
            </div>
          ) : (
            <ul className="divide-y divide-slate-800/30">
              {suggestions.map((item, idx) => {
                const isActive = idx === activeIndex;
                return (
                  <li key={`${item.id}-${item.source || "db"}`}>
                    <button
                      type="button"
                      onClick={() => handleChoose(item)}
                      className={`w-full text-left px-3.5 py-2.5 transition flex flex-col gap-1 ${
                        isDark
                          ? isActive
                            ? "bg-indigo-950/90"
                            : "hover:bg-slate-800/80"
                          : isActive
                          ? "bg-indigo-50"
                          : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <span className="font-bold text-xs sm:text-sm">{item.keyword}</span>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              isDark
                                ? "bg-slate-800 text-slate-300 border border-slate-700"
                                : "bg-slate-100 text-slate-700 border border-slate-200"
                            }`}
                          >
                            {item.subject_name}
                          </span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              isDark
                                ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                                : "bg-indigo-50 text-indigo-700 border border-indigo-200"
                            }`}
                          >
                            Module {item.module_no}
                          </span>
                        </div>
                      </div>

                      {/* Highlight alias match when found via topic_aliases */}
                      {item.matched_alias && (
                        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-500">
                          <Tag className="w-3 h-3 shrink-0" />
                          <span>Matched alias: "{item.matched_alias}"</span>
                        </div>
                      )}

                      {!item.matched_alias && item.aliases && item.aliases.length > 0 && (
                        <div className="flex items-center gap-1 text-[10px] text-slate-400">
                          <Layers className="w-3 h-3 shrink-0" />
                          <span>Aliases: {item.aliases.slice(0, 3).join(", ")}</span>
                        </div>
                      )}

                      {item.explanation && (
                        <p className="text-[11px] text-slate-400 line-clamp-1">
                          {item.explanation}
                        </p>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

