import React, { useState, useEffect, useMemo } from "react";
import {
  BookOpen,
  Search,
  Filter,
  Eye,
  EyeOff,
  AlertCircle,
  RefreshCw,
  Folder,
  Layers,
  ArrowRight,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { TopicCard, TheoryTopicCardData } from "./TopicCard";
import { TheoryLinkChipData } from "./LinkChip";
import { SyllabusModal } from "../syllabus/SyllabusModal";
import { SubjectSyllabusResponse } from "../syllabus/syllabusUtils";

interface SubjectItem {
  id: string;
  name: string;
  source_preference?: string;
}

interface TheoryModuleGroupData {
  module_no: number;
  module_title: string;
  topic_count: number;
  topics: TheoryTopicCardData[];
}

interface SubjectTheoryResponse {
  subject_id: string;
  subject_name: string;
  source_preference?: string;
  total_topics: number;
  total_links: number;
  unreviewed_count: number;
  modules: TheoryModuleGroupData[];
}

const DEMO_USERS = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Alex Chen (Student A)", email: "alex@university.edu" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Jordan Taylor (Student B)", email: "jordan@university.edu" },
];

export const TheoryPage: React.FC = () => {
  const [activeUser, setActiveUser] = useState(DEMO_USERS[0]);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [theoryData, setTheoryData] = useState<SubjectTheoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters & Toggles
  const [searchTerm, setSearchTerm] = useState("");
  const [showWeakLinks, setShowWeakLinks] = useState(false); // Default false (Rule 13.8)
  const [highlightedTopicId, setHighlightedTopicId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [prefSaving, setPrefSaving] = useState(false);
  const [syllabusInfo, setSyllabusInfo] = useState<SubjectSyllabusResponse | null>(null);
  const [isSyllabusModalOpen, setIsSyllabusModalOpen] = useState(false);

  // Load subject list on mount or when student changes
  useEffect(() => {
    fetchSubjects(activeUser.id, activeUser.email);
  }, [activeUser.id]);

  const fetchSubjects = async (userId: string, userEmail: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/subjects", {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (!res.ok) throw new Error("Failed to load subject list.");
      const data: SubjectItem[] = await res.json();
      setSubjects(data);
      if (data.length > 0) {
        setSelectedSubjectId(data[0].id);
        fetchTheoryData(data[0].id, userId, userEmail);
      } else {
        setSelectedSubjectId("");
        setTheoryData(null);
        setLoading(false);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load subjects.");
      setLoading(false);
    }
  };

  const handleSwitchUser = (userId: string) => {
    const user = DEMO_USERS.find((u) => u.id === userId) || DEMO_USERS[0];
    setActiveUser(user);
    setSelectedSubjectId("");
    setTheoryData(null);
  };

  const handleSubjectChange = (subjectId: string) => {
    setSelectedSubjectId(subjectId);
    fetchTheoryData(subjectId, activeUser.id, activeUser.email);
  };

  const fetchTheoryData = async (subjectId: string, userId?: string, userEmail?: string) => {
    setLoading(true);
    setError(null);
    const uid = userId || activeUser.id;
    const uemail = userEmail || activeUser.email;
    try {
      const res = await fetch(`/api/subjects/${subjectId}/theory`, {
        headers: {
          "x-test-user-id": uid,
          "x-test-user-email": uemail,
        },
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => null);
        throw new Error(errJson?.detail || `Error loading theory: ${res.status}`);
      }
      const data: SubjectTheoryResponse = await res.json();
      setTheoryData(data);
      // Load syllabus coverage in parallel (non-blocking)
      fetch(`/api/subjects/${subjectId}/syllabus`, {
        headers: { "x-test-user-id": uid, "x-test-user-email": uemail },
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((s) => setSyllabusInfo(s))
        .catch(() => setSyllabusInfo(null));
    } catch (err: any) {
      setError(err.message || "Could not load theory revision data.");
    } finally {
      setLoading(false);
    }
  };

  // Filter topics based on search term
  const filteredModules = useMemo(() => {
    if (!theoryData) return [];
    if (!searchTerm.trim()) return theoryData.modules;

    const lower = searchTerm.toLowerCase();
    return theoryData.modules
      .map((mod) => {
        const matchedTopics = mod.topics.filter(
          (t) =>
            t.keyword.toLowerCase().includes(lower) ||
            t.explanation.toLowerCase().includes(lower) ||
            (t.real_world_use && t.real_world_use.toLowerCase().includes(lower)) ||
            t.links.some((l) => l.target_keyword.toLowerCase().includes(lower))
        );
        return {
          ...mod,
          topics: matchedTopics,
          topic_count: matchedTopics.length,
        };
      })
      .filter((mod) => mod.topics.length > 0);
  }, [theoryData, searchTerm]);

  // Handle clicking a link chip to jump to target topic
  const handleJumpToTopic = (targetTopicId: string) => {
    // If search filter is active and might hide the destination, clear it
    if (searchTerm.trim()) {
      setSearchTerm("");
    }

    setHighlightedTopicId(targetTopicId);

    setTimeout(() => {
      const el = document.getElementById(`topic-${targetTopicId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        showToast("Scrolled to connected topic!");
      } else {
        showToast("Connected concept is in another subject or section.");
      }
    }, 100);

    // Auto-remove highlight after 3.5 seconds
    setTimeout(() => {
      setHighlightedTopicId((curr) => (curr === targetTopicId ? null : curr));
    }, 3500);
  };

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleModuleScroll = (moduleNo: number) => {
    const el = document.getElementById(`module-section-${moduleNo}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handlePreferenceToggle = async (nextPref: "notes" | "textbook") => {
    if (!selectedSubjectId || prefSaving) return;
    setPrefSaving(true);
    try {
      const res = await fetch(`/api/subjects/${selectedSubjectId}/preference`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "x-test-user-id": activeUser.id,
          "x-test-user-email": activeUser.email,
        },
        body: JSON.stringify({ source_preference: nextPref }),
      });
      if (res.ok) {
        showToast(`Switched preferred source to ${nextPref === "notes" ? "Lecture Notes" : "Textbook"}`);
        await fetchTheoryData(selectedSubjectId, activeUser.id, activeUser.email);
      }
    } catch {
      showToast("Could not update source preference.");
    } finally {
      setPrefSaving(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 space-y-6">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-4 py-2.5 rounded-lg shadow-xl text-xs font-semibold flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Header Card: Subject Picker & Revision Overview */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
            <BookOpen className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              Theory Revision View
            </h1>
            <p className="text-xs text-slate-500">
              Bite-sized concept cards grouped by module with verified cross-module connection chips.
            </p>
          </div>
        </div>

        {/* Student Profile Switcher & Subject Selector */}
        <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto">
          {/* Active Student Switcher (Privacy Rule 11) */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 shadow-2xs">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Student:</span>
            <select
              value={activeUser.id}
              onChange={(e) => handleSwitchUser(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-800 focus:outline-none pr-1 cursor-pointer"
            >
              {DEMO_USERS.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>

          {/* Subject Selector */}
          <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 shadow-2xs">
            <Folder className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={selectedSubjectId}
              onChange={(e) => handleSubjectChange(e.target.value)}
              className="bg-transparent text-xs font-semibold text-slate-800 focus:outline-none pr-1 cursor-pointer"
            >
              {subjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => selectedSubjectId && fetchTheoryData(selectedSubjectId, activeUser.id, activeUser.email)}
            disabled={loading}
            className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 transition"
            title="Refresh Theory"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-indigo-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* Sticky Quick-Jump & Filter Toolbar */}
      {theoryData && theoryData.modules.length > 0 && (
        <div className="sticky top-18 z-20 bg-white/95 backdrop-blur-md rounded-xl border border-slate-200 p-3 shadow-xs space-y-2.5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search concepts, applications, or connected keywords..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
              />
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2.5 top-2 text-[10px] text-slate-400 hover:text-slate-600"
                >
                  Clear
                </button>
              )}
            </div>

            {/* Controls: Source Preference Toggle (F17), Syllabus Coverage (F16), Weak Links & Stats */}
            <div className="flex flex-wrap items-center gap-2.5 self-end sm:self-auto">
              {/* Notes vs Textbook Preference Toggle */}
              <div className="flex items-center gap-1 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 text-xs">
                <span className="text-[11px] font-semibold text-slate-500">Prefer:</span>
                <button
                  type="button"
                  disabled={prefSaving}
                  onClick={() => handlePreferenceToggle("notes")}
                  className={`px-2 py-0.5 rounded font-semibold transition cursor-pointer ${
                    (theoryData.source_preference || "notes") === "notes"
                      ? "bg-indigo-600 text-white"
                      : "text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  Notes
                </button>
                <button
                  type="button"
                  disabled={prefSaving}
                  onClick={() => handlePreferenceToggle("textbook")}
                  className={`px-2 py-0.5 rounded font-semibold transition cursor-pointer ${
                    theoryData.source_preference === "textbook"
                      ? "bg-purple-600 text-white"
                      : "text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  Textbook
                </button>
              </div>

              {/* Syllabus Coverage & Gaps button */}
              {selectedSubjectId && (
                <button
                  type="button"
                  onClick={() => setIsSyllabusModalOpen(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold border bg-indigo-50/70 text-indigo-800 border-indigo-200 hover:bg-indigo-100 transition cursor-pointer"
                >
                  <Layers className="w-3.5 h-3.5 text-indigo-600" />
                  {syllabusInfo?.has_syllabus
                    ? `Syllabus ${syllabusInfo.coverage_percent}% (${syllabusInfo.gap_count} gaps)`
                    : "Syllabus & Gaps"}
                </button>
              )}

              {/* Weak Links Toggle (Rule 13.8) */}
              <button
                onClick={() => setShowWeakLinks(!showWeakLinks)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${
                  showWeakLinks
                    ? "bg-amber-50 text-amber-800 border-amber-200 shadow-2xs"
                    : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                }`}
                title="Toggle weak links (strength 1-2). Hidden by default per RULEBOOK Rule 13.8."
              >
                {showWeakLinks ? (
                  <Eye className="w-3.5 h-3.5 text-amber-600" />
                ) : (
                  <EyeOff className="w-3.5 h-3.5 text-slate-400" />
                )}
                <span>Weak Links {showWeakLinks ? "Shown" : "Hidden"}</span>
              </button>

              {/* Stats badges */}
              <div className="hidden lg:flex items-center gap-2 text-xs font-medium text-slate-500 border-l border-slate-200 pl-3">
                <span className="font-bold text-slate-800">{theoryData.total_topics}</span> topics
                <span>&bull;</span>
                <span className="font-bold text-slate-800">{theoryData.total_links}</span> links
                {theoryData.unreviewed_count > 0 && (
                  <span className="text-amber-700 font-bold bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                    {theoryData.unreviewed_count} unreviewed
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Module Navigation Jump Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 pt-1 scrollbar-none border-t border-slate-100">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mr-1 shrink-0">
              Jump:
            </span>
            {theoryData.modules.map((mod) => (
              <button
                key={mod.module_no}
                onClick={() => handleModuleScroll(mod.module_no)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-700 transition shrink-0"
              >
                <span>Mod {mod.module_no}</span>
                <span className="text-[10px] text-slate-400 font-normal">
                  ({mod.topic_count})
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error Notice */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-bold">Error: </span>
            {error}
          </div>
        </div>
      )}

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-6 animate-pulse">
          <div className="h-6 bg-slate-200 rounded w-48 mb-4"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-44 bg-slate-100 rounded-xl border border-slate-200"></div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && theoryData && theoryData.modules.length === 0 && (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 text-center space-y-3">
          <BookOpen className="w-10 h-10 text-slate-300 mx-auto" />
          <h3 className="text-sm font-bold text-slate-800">
            No study cards yet for {theoryData.subject_name}
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Upload course notes or slides for this subject in the "Upload & Ingest" tab to automatically extract topic cards and link them into a knowledge network.
          </p>
        </div>
      )}

      {/* Main Revision Content Grouped By Module */}
      {!loading && theoryData && filteredModules.length > 0 && (
        <div className="space-y-8">
          {filteredModules.map((group) => (
            <section
              key={group.module_no}
              id={`module-section-${group.module_no}`}
              className="scroll-mt-36 space-y-4"
            >
              {/* Module Header Bar */}
              <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full bg-indigo-600"></div>
                  <h2 className="text-base font-bold text-slate-900 tracking-tight">
                    {group.module_title}
                  </h2>
                  <span className="text-xs text-slate-500 font-medium">
                    ({group.topic_count} {group.topic_count === 1 ? "concept" : "concepts"})
                  </span>
                </div>

                <button
                  onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
                  className="text-[11px] text-slate-400 hover:text-indigo-600 font-medium flex items-center gap-0.5 transition"
                >
                  <span>Top</span>
                  <ChevronRight className="w-3 h-3 rotate-[-90deg]" />
                </button>
              </div>

              {/* Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {group.topics.map((topic) => (
                  <TopicCard
                    key={topic.id}
                    card={topic}
                    showWeakLinks={showWeakLinks}
                    isHighlighted={highlightedTopicId === topic.id}
                    onJump={handleJumpToTopic}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* Search No Results */}
      {!loading && theoryData && theoryData.modules.length > 0 && filteredModules.length === 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-2">
          <Search className="w-8 h-8 text-slate-300 mx-auto" />
          <h4 className="text-sm font-semibold text-slate-700">
            No concepts match "{searchTerm}"
          </h4>
          <p className="text-xs text-slate-400">
            Try searching for another keyword or clear the search filter.
          </p>
          <button
            onClick={() => setSearchTerm("")}
            className="text-xs text-indigo-600 font-bold hover:underline pt-2 inline-block"
          >
            Clear search
          </button>
        </div>
      )}

      {/* Syllabus Coverage & Gap Modal */}
      {selectedSubjectId && (
        <SyllabusModal
          key={selectedSubjectId}
          isOpen={isSyllabusModalOpen}
          subjectId={selectedSubjectId}
          subjectName={theoryData?.subject_name || "Subject"}
          activeUserId={activeUser.id}
          activeUserEmail={activeUser.email}
          initialTab={syllabusInfo?.has_syllabus ? "coverage" : "upload"}
          onClose={() => setIsSyllabusModalOpen(false)}
          onUpdated={() => fetchTheoryData(selectedSubjectId, activeUser.id, activeUser.email)}
        />
      )}
    </div>
  );
};
