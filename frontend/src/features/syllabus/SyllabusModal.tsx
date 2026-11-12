import React, { useEffect, useState } from "react";
import {
  X,
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  Edit3,
  Trash2,
  Plus,
  Sparkles,
  Loader2,
  Layers,
  Lock,
  RefreshCw,
} from "lucide-react";
import { SubjectSyllabusResponse, SyllabusTopicItem } from "./syllabusUtils";

interface SyllabusModalProps {
  isOpen: boolean;
  subjectId: string;
  subjectName: string;
  activeUserId: string;
  activeUserEmail: string;
  initialTab?: "upload" | "review" | "coverage";
  onClose: () => void;
  onUpdated?: () => void;
}

export const SyllabusModal: React.FC<SyllabusModalProps> = ({
  isOpen,
  subjectId,
  subjectName,
  activeUserId,
  activeUserEmail,
  initialTab = "coverage",
  onClose,
  onUpdated,
}) => {
  const [activeTab, setActiveTab] = useState<"upload" | "review" | "coverage">(initialTab);
  const [syllabusData, setSyllabusData] = useState<SubjectSyllabusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Upload / Paste state
  const [inputMode, setInputMode] = useState<"paste" | "file">("paste");
  const [syllabusText, setSyllabusText] = useState("");
  const [syllabusFile, setSyllabusFile] = useState<File | null>(null);
  const [universityName, setUniversityName] = useState("Default University");
  const [schemeName, setSchemeName] = useState("2022 Scheme");
  const [subjectCode, setSubjectCode] = useState("");
  const [semester, setSemester] = useState("");
  const [branch, setBranch] = useState("");

  // Review state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editModuleNo, setEditModuleNo] = useState<number>(1);
  const [newTitle, setNewTitle] = useState("");
  const [newModuleNo, setNewModuleNo] = useState<number>(1);

  // Manual match correction state
  const [subjectTopics, setSubjectTopics] = useState<{ id: string; keyword: string }[]>([]);
  const [matchingNow, setMatchingNow] = useState(false);
  const [allSubjects, setAllSubjects] = useState<{ id: string; name: string }[]>([]);
  const [moveTargetId, setMoveTargetId] = useState<string>("");

  const authHeaders = {
    "x-test-user-id": activeUserId,
    "x-test-user-email": activeUserEmail,
  };

  useEffect(() => {
    if (!isOpen || !subjectId) return;
    setError(null);
    setNotice(null);
    setActiveTab(initialTab);
    fetchSyllabus(true);
    fetchSubjectTopics();
    fetchAllSubjects();
  }, [isOpen, subjectId, activeUserId]);

  const fetchSyllabus = async (autoPickTab = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus`, { headers: authHeaders });
      if (!res.ok) throw new Error("Failed to load syllabus details.");
      const data: SubjectSyllabusResponse = await res.json();
      setSyllabusData(data);
      if (data.metadata) {
        if (data.metadata.university_name) setUniversityName(data.metadata.university_name);
        if (data.metadata.scheme_name) setSchemeName(data.metadata.scheme_name);
        if (data.metadata.subject_code) setSubjectCode(data.metadata.subject_code);
        if (data.metadata.semester) setSemester(String(data.metadata.semester));
        if (data.metadata.branch) setBranch(data.metadata.branch);
      }
      if (autoPickTab) {
        if (!data.has_syllabus) {
          setActiveTab("upload");
        } else if (data.unreviewed_count > 0 && initialTab === "review") {
          setActiveTab("review");
        } else {
          setActiveTab(initialTab);
        }
      }
    } catch (err: any) {
      setError(err.message || "Could not load syllabus.");
    } finally {
      setLoading(false);
    }
  };

  const fetchSubjectTopics = async () => {
    try {
      const res = await fetch(`/api/topics?subject_id=${subjectId}`, { headers: authHeaders });
      if (res.ok) {
        const list = await res.json();
        setSubjectTopics(list || []);
      }
    } catch {
      // Non-fatal
    }
  };

  const fetchAllSubjects = async () => {
    try {
      const res = await fetch("/api/subjects", { headers: authHeaders });
      if (res.ok) {
        const list: { id: string; name: string }[] = await res.json();
        const others = list.filter((s) => s.id !== subjectId);
        setAllSubjects(others);
        setMoveTargetId(others[0]?.id || "");
      }
    } catch {
      // Non-fatal
    }
  };

  if (!isOpen) return null;

  const handleParseSyllabus = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      let res: Response;
      if (inputMode === "paste") {
        if (syllabusText.trim().length < 10) {
          throw new Error("Please paste syllabus text (at least a few lines).");
        }
        res = await fetch(`/api/subjects/${subjectId}/syllabus/parse-text`, {
          method: "POST",
          headers: { ...authHeaders, "Content-Type": "application/json" },
          body: JSON.stringify({
            syllabus_text: syllabusText.trim(),
            university_name: universityName.trim() || "Default University",
            scheme_name: schemeName.trim() || "2022 Scheme",
            subject_code: subjectCode.trim() || null,
            semester: semester ? Number(semester) : null,
            branch: branch.trim() || null,
          }),
        });
      } else {
        if (!syllabusFile) {
          throw new Error("Please choose a syllabus PDF, PPTX, or image file.");
        }
        const formData = new FormData();
        formData.append("file", syllabusFile);
        formData.append("university_name", universityName.trim() || "Default University");
        formData.append("scheme_name", schemeName.trim() || "2022 Scheme");
        if (subjectCode.trim()) formData.append("subject_code", subjectCode.trim());
        if (semester) formData.append("semester", semester);
        if (branch.trim()) formData.append("branch", branch.trim());

        res = await fetch(`/api/subjects/${subjectId}/syllabus/upload`, {
          method: "POST",
          headers: authHeaders,
          body: formData,
        });
      }

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to parse syllabus.");
      }

      setSyllabusData(data);
      setNotice(
        `Parsed ${data.total_syllabus_topics} syllabus ghost nodes. Review them below or skip straight to the graph!`
      );
      setActiveTab("review");
      onUpdated?.();
    } catch (err: any) {
      setError(err.message || "Syllabus parsing failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveEdit = async (item: SyllabusTopicItem) => {
    if (!editTitle.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/topics/${item.id}`, {
        method: "PATCH",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ title: editTitle.trim(), module_no: editModuleNo }),
      });
      if (!res.ok) throw new Error("Could not update syllabus topic.");
      setEditingId(null);
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteTopic = async (id: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/topics/${id}`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to remove syllabus topic.");
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddTopic = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/topics`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim(), module_no: newModuleNo }),
      });
      if (!res.ok) throw new Error("Failed to add syllabus topic.");
      setNewTitle("");
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleApproveAll = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/approve-all`, {
        method: "POST",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Failed to approve syllabus topics.");
      const data: SubjectSyllabusResponse = await res.json();
      setSyllabusData(data);
      setNotice("All syllabus ghost nodes approved!");
      setActiveTab("coverage");
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkipReview = async () => {
    await fetch(`/api/subjects/${subjectId}/syllabus/skip`, {
      method: "POST",
      headers: authHeaders,
    }).catch(() => {});
    setActiveTab("coverage");
  };

  const handleRunAutoMatch = async () => {
    setMatchingNow(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/match`, {
        method: "POST",
        headers: authHeaders,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Auto-match failed.");
      setNotice(
        `Matched ${data.matches_created} new topic(s) to syllabus ghost nodes (${data.coverage_percent}% covered).`
      );
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setMatchingNow(false);
    }
  };

  const handleManualAssignTopic = async (syllabusTopicId: string, topicId: string) => {
    if (!topicId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/matches/${topicId}`, {
        method: "PATCH",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ syllabus_topic_id: syllabusTopicId }),
      });
      if (!res.ok) throw new Error("Could not assign topic to syllabus item.");
      const data: SubjectSyllabusResponse = await res.json();
      setSyllabusData(data);
      setNotice("Saved & locked manual syllabus match (protected from future auto-overwrites).");
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnlinkTopic = async (topicId: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/matches/${topicId}`, {
        method: "PATCH",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ syllabus_topic_id: null }),
      });
      if (!res.ok) throw new Error("Could not unlink topic.");
      const data: SubjectSyllabusResponse = await res.json();
      setSyllabusData(data);
      setNotice("Unlinked topic and locked preference.");
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleMoveSyllabus = async () => {
    if (!moveTargetId) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus/reassign`, {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ target_subject_id: moveTargetId }),
      });
      if (!res.ok) throw new Error("Could not move syllabus to target subject.");
      const targetName = allSubjects.find((s) => s.id === moveTargetId)?.name || "target subject";
      setNotice(`Moved syllabus to "${targetName}"!`);
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteSyllabus = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/syllabus`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error("Could not delete syllabus.");
      setNotice("Removed syllabus from this subject.");
      await fetchSyllabus(false);
      onUpdated?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Layers className="w-5 h-5 text-indigo-600" />
              Syllabus Ghost Nodes & Coverage — {subjectName}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload an official syllabus to create faded ghost nodes that light up as your notes arrive.
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/70 transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="px-6 pt-3 pb-2 border-b border-slate-100 flex items-center gap-2 bg-white">
          <button
            type="button"
            onClick={() => setActiveTab("coverage")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === "coverage"
                ? "bg-indigo-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Coverage & Gaps ({syllabusData?.gap_count ?? 0})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("review")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === "review"
                ? "bg-indigo-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Review Parsed Syllabus ({syllabusData?.total_syllabus_topics ?? 0})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("upload")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
              activeTab === "upload"
                ? "bg-indigo-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Upload / Paste Syllabus
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {notice && (
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{notice}</span>
            </div>
          )}

          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-500 text-xs gap-2">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
              <span>Loading syllabus status...</span>
            </div>
          ) : activeTab === "upload" ? (
            <form onSubmit={handleParseSyllabus} className="space-y-4">
              <div className="p-3 rounded-xl bg-indigo-50 border border-indigo-200 text-xs text-indigo-900 flex items-center justify-between gap-2">
                <span>
                  Target Subject Folder: <strong className="font-bold">{subjectName}</strong>
                </span>
                <span className="text-[11px] text-indigo-700">
                  Close &amp; switch subject dropdown first if you meant another subject
                </span>
              </div>
              {/* University / Scheme fields (preserves schema hierarchy per R12) */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">University</label>
                  <input
                    type="text"
                    value={universityName}
                    onChange={(e) => setUniversityName(e.target.value)}
                    className="w-full text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                    placeholder="Default University"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Scheme / Year</label>
                  <input
                    type="text"
                    value={schemeName}
                    onChange={(e) => setSchemeName(e.target.value)}
                    className="w-full text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                    placeholder="2022 Scheme"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-600 mb-1">Subject Code (Optional)</label>
                  <input
                    type="text"
                    value={subjectCode}
                    onChange={(e) => setSubjectCode(e.target.value)}
                    className="w-full text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white"
                    placeholder="e.g. BCS401"
                  />
                </div>
              </div>

              {/* Input mode toggle */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setInputMode("paste")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border cursor-pointer ${
                    inputMode === "paste"
                      ? "bg-indigo-50 border-indigo-300 text-indigo-700"
                      : "bg-white border-slate-200 text-slate-600"
                  }`}
                >
                  Paste Syllabus Text
                </button>
                <button
                  type="button"
                  onClick={() => setInputMode("file")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border cursor-pointer ${
                    inputMode === "file"
                      ? "bg-indigo-50 border-indigo-300 text-indigo-700"
                      : "bg-white border-slate-200 text-slate-600"
                  }`}
                >
                  Upload Syllabus PDF / Image
                </button>
              </div>

              {inputMode === "paste" ? (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Paste Module-by-Module Syllabus
                  </label>
                  <textarea
                    rows={7}
                    value={syllabusText}
                    onChange={(e) => setSyllabusText(e.target.value)}
                    placeholder={`Module 1: Process Management, Process States, PCB, CPU Scheduling\nModule 2: Deadlocks, Deadlock Prevention, Banker's Algorithm, Virtual Memory\nModule 3: File Systems, Disk Scheduling`}
                    className="w-full text-xs border border-slate-300 rounded-xl p-3 font-mono focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              ) : (
                <div className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center bg-slate-50">
                  <Upload className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                  <input
                    type="file"
                    accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg"
                    onChange={(e) => setSyllabusFile(e.target.files?.[0] || null)}
                    className="text-xs text-slate-600"
                  />
                  {syllabusFile && (
                    <p className="text-xs font-semibold text-indigo-700 mt-2 flex items-center justify-center gap-1">
                      <FileText className="w-3.5 h-3.5" />
                      {syllabusFile.name}
                    </p>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-2">
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
                >
                  {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  Parse Syllabus into Ghost Nodes
                </button>
              </div>
            </form>
          ) : activeTab === "review" ? (
            !syllabusData?.has_syllabus ? (
              <div className="text-center py-10 space-y-3">
                <p className="text-xs text-slate-500">No syllabus uploaded for this subject yet.</p>
                <button
                  type="button"
                  onClick={() => setActiveTab("upload")}
                  className="px-3.5 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg cursor-pointer"
                >
                  Upload or Paste Syllabus
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 p-3 rounded-xl border border-slate-200">
                  <div className="text-xs text-slate-700">
                    <strong>{syllabusData.total_syllabus_topics}</strong> syllabus topics •{" "}
                    <span className="text-amber-700 font-semibold">{syllabusData.unreviewed_count} unreviewed</span>
                    {syllabusData.metadata && (
                      <span className="ml-2 text-slate-500">
                        ({syllabusData.metadata.university_name} • {syllabusData.metadata.scheme_name})
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleSkipReview}
                      className="px-3 py-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-300 rounded-lg hover:bg-slate-100 cursor-pointer"
                    >
                      Skip for now
                    </button>
                    <button
                      type="button"
                      onClick={handleApproveAll}
                      disabled={submitting}
                      className="px-3 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg flex items-center gap-1 cursor-pointer"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Approve All
                    </button>
                  </div>
                </div>

                {/* Add missing topic */}
                <form onSubmit={handleAddTopic} className="flex items-center gap-2">
                  <select
                    value={newModuleNo}
                    onChange={(e) => setNewModuleNo(Number(e.target.value))}
                    className="text-xs border border-slate-300 rounded-lg px-2 py-1.5 bg-white"
                  >
                    {[1, 2, 3, 4, 5, 6].map((m) => (
                      <option key={m} value={m}>
                        Module {m}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="Add missing syllabus topic..."
                    className="flex-1 text-xs border border-slate-300 rounded-lg px-3 py-1.5"
                  />
                  <button
                    type="submit"
                    disabled={submitting || !newTitle.trim()}
                    className="px-3 py-1.5 bg-indigo-600 text-white text-xs font-semibold rounded-lg flex items-center gap-1 disabled:opacity-50 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add
                  </button>
                </form>

                {/* List of syllabus topics for review */}
                <div className="space-y-2">
                  {syllabusData.syllabus_topics.map((item) => (
                    <div
                      key={item.id}
                      className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-slate-200 bg-white text-xs"
                    >
                      {editingId === item.id ? (
                        <div className="flex-1 flex items-center gap-2">
                          <select
                            value={editModuleNo}
                            onChange={(e) => setEditModuleNo(Number(e.target.value))}
                            className="border border-slate-300 rounded px-2 py-1 text-xs"
                          >
                            {[1, 2, 3, 4, 5, 6].map((m) => (
                              <option key={m} value={m}>
                                Mod {m}
                              </option>
                            ))}
                          </select>
                          <input
                            type="text"
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            className="flex-1 border border-slate-300 rounded px-2 py-1 text-xs"
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveEdit(item)}
                            className="px-2.5 py-1 bg-indigo-600 text-white rounded font-semibold cursor-pointer"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingId(null)}
                            className="px-2 py-1 text-slate-500 cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-semibold">
                              Mod {item.module_no}
                            </span>
                            <span className="font-semibold text-slate-900">{item.title}</span>
                            {item.reviewed ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                                Approved
                              </span>
                            ) : (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                                Unreviewed
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                setEditingId(item.id);
                                setEditTitle(item.title);
                                setEditModuleNo(item.module_no);
                              }}
                              className="p-1 text-slate-500 hover:text-indigo-600 cursor-pointer"
                              title="Edit syllabus topic"
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleDeleteTopic(item.id)}
                              className="p-1 text-slate-500 hover:text-rose-600 cursor-pointer"
                              title="Delete syllabus topic"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          ) : !syllabusData?.has_syllabus ? (
            <div className="text-center py-10 space-y-3">
              <p className="text-xs text-slate-500">
                No syllabus uploaded for <strong>{subjectName}</strong> yet.
              </p>
              <button
                type="button"
                onClick={() => setActiveTab("upload")}
                className="px-3.5 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg cursor-pointer"
              >
                Upload / Paste Syllabus to See Ghost Nodes
              </button>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Overall coverage summary */}
              <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-200 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-bold text-indigo-950">
                      {syllabusData.coverage_percent}% Syllabus Covered ({syllabusData.covered_count}/
                      {syllabusData.total_syllabus_topics} topics)
                    </div>
                    <div className="text-xs text-indigo-700">
                      {syllabusData.gap_count} uncovered ghost node{syllabusData.gap_count === 1 ? "" : "s"} remaining
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleRunAutoMatch}
                    disabled={matchingNow}
                    className="px-3 py-1.5 bg-white hover:bg-indigo-100 border border-indigo-300 rounded-lg text-xs font-semibold text-indigo-700 flex items-center gap-1.5 cursor-pointer"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${matchingNow ? "animate-spin" : ""}`} />
                    Re-run Auto-Match
                  </button>
                </div>
                <div className="w-full h-2.5 bg-white rounded-full overflow-hidden border border-indigo-200">
                  <div
                    className="h-full bg-indigo-600 transition-all duration-300"
                    style={{ width: `${Math.min(100, syllabusData.coverage_percent)}%` }}
                  />
                </div>

                {/* Move or Delete Syllabus controls (in case uploaded to wrong subject) */}
                <div className="pt-2 border-t border-indigo-200/70 flex flex-wrap items-center justify-between gap-2 text-xs">
                  {allSubjects.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[11px] text-indigo-900 font-medium">Wrong subject? Move to:</span>
                      <select
                        value={moveTargetId}
                        onChange={(e) => setMoveTargetId(e.target.value)}
                        className="text-[11px] border border-indigo-200 rounded-md px-2 py-1 bg-white text-slate-800"
                      >
                        {allSubjects.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={submitting || !moveTargetId}
                        onClick={handleMoveSyllabus}
                        className="px-2.5 py-1 rounded-md bg-white hover:bg-indigo-100 border border-indigo-300 text-[11px] font-semibold text-indigo-700 cursor-pointer"
                      >
                        Move Syllabus
                      </button>
                    </div>
                  )}
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={handleDeleteSyllabus}
                    className="px-2.5 py-1 rounded-md bg-white hover:bg-rose-50 border border-rose-200 text-[11px] font-semibold text-rose-700 cursor-pointer"
                  >
                    Remove Syllabus
                  </button>
                </div>
              </div>

              {/* Per-module breakdown */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {syllabusData.modules.map((mod) => (
                  <div
                    key={mod.module_no}
                    className="p-3.5 rounded-xl border border-slate-200 bg-white space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs font-bold text-slate-800">
                      <span>Module {mod.module_no}</span>
                      <span
                        className={
                          mod.coverage_percent === 100 ? "text-emerald-700" : "text-indigo-700"
                        }
                      >
                        {mod.covered_count}/{mod.total_topics} ({mod.coverage_percent}%)
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${
                          mod.coverage_percent === 100 ? "bg-emerald-500" : "bg-indigo-500"
                        }`}
                        style={{ width: `${Math.min(100, mod.coverage_percent)}%` }}
                      />
                    </div>
                    {mod.gap_count > 0 ? (
                      <div className="text-[11px] text-slate-600">
                        <span className="font-semibold text-amber-700">Gaps ({mod.gap_count}): </span>
                        {mod.gap_topics.map((g) => g.title).join(", ")}
                      </div>
                    ) : (
                      <div className="text-[11px] text-emerald-700 font-medium">
                        All syllabus topics covered!
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Full Gap List & Match Correction */}
              <div className="space-y-2">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Syllabus Topics, Matched Note Nodes & Gap List
                </h3>
                {syllabusData.syllabus_topics.map((syl) => (
                  <div
                    key={syl.id}
                    className={`p-3 rounded-xl border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 ${
                      syl.is_covered
                        ? "bg-emerald-50/40 border-emerald-200"
                        : "bg-slate-50 border-dashed border-slate-300"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-1.5 py-0.5 rounded bg-white border border-slate-200 font-semibold text-slate-700">
                          Mod {syl.module_no}
                        </span>
                        <span className="font-bold text-slate-900">{syl.title}</span>
                        {syl.is_covered ? (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold text-[10px]">
                            Lit Up (Covered)
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 font-semibold text-[10px]">
                            Ghost Gap (Not in notes)
                          </span>
                        )}
                      </div>

                      {syl.matched_topics.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap pl-1">
                          <span className="text-[11px] text-slate-500">Matched to:</span>
                          {syl.matched_topics.map((mt) => (
                            <span
                              key={mt.topic_id}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white border border-emerald-200 text-emerald-800 font-medium"
                            >
                              {mt.syllabus_match_locked && <Lock className="w-2.5 h-2.5 text-amber-600" />}
                              {mt.keyword}
                              <button
                                type="button"
                                onClick={() => handleUnlinkTopic(mt.topic_id)}
                                className="text-slate-400 hover:text-rose-600 ml-0.5 cursor-pointer"
                                title="Unlink & lock"
                              >
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {subjectTopics.length > 0 && (
                      <select
                        defaultValue=""
                        onChange={(e) => {
                          if (e.target.value) {
                            handleManualAssignTopic(syl.id, e.target.value);
                            e.target.value = "";
                          }
                        }}
                        className="text-[11px] border border-slate-300 rounded-lg px-2 py-1 bg-white text-slate-700 max-w-[200px]"
                      >
                        <option value="">+ Map note topic manually...</option>
                        {subjectTopics.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.keyword}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

