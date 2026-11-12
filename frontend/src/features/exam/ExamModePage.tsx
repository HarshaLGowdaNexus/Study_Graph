import React, { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Award,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Folder,
  GraduationCap,
  Loader2,
  Network,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  Upload,
  User,
  X,
} from "lucide-react";
import { CitationBadge, CitationItemData } from "../chat/CitationBadge";
import {
  ExamMarks,
  IMPORTANT_CONCEPTS_LABEL,
  REPEATED_QUESTIONS_LABEL,
  formatPaperFrequencyLabel,
  getMarksDescription,
} from "./examModeUtils";

interface SubjectItem {
  id: string;
  name: string;
}

interface ImportantConcept {
  topic_id: string;
  keyword: string;
  explanation: string;
  real_world_use?: string | null;
  module_no?: number | null;
  reviewed: boolean;
  importance_score: number;
  degree: number;
  weighted_degree: number;
  modules_covered: number;
  source_count: number;
  cross_subject_links: number;
  label: string;
}

interface ExamPaper {
  id: string;
  document_id: string;
  filename: string;
  year?: number | null;
  status: string;
  question_count: number;
  uploaded_at?: string | null;
}

interface QuestionOccurrence {
  question_id: string;
  paper_id: string;
  filename: string;
  year?: number | null;
  text: string;
  marks?: number | null;
}

interface RepeatedQuestionCluster {
  cluster_key: string;
  canonical_question: string;
  repeat_count: number;
  total_papers: number;
  typical_marks?: number | null;
  matched_topic_id?: string | null;
  matched_topic_keyword?: string | null;
  label: string;
  occurrences: QuestionOccurrence[];
}

interface ExamOverview {
  subject_id: string;
  subject_name: string;
  important_concepts_label: string;
  important_concepts: ImportantConcept[];
  repeated_questions_label: string;
  has_uploaded_papers: boolean;
  total_papers: number;
  total_questions: number;
  honest_notice?: string | null;
  papers: ExamPaper[];
  repeated_questions: RepeatedQuestionCluster[];
}

interface MarksAnswerResult {
  question: string;
  marks: ExamMarks;
  text: string;
  answered_from: "notes" | "general";
  confidence: number;
  citations: CitationItemData[];
}

const DEMO_USERS = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Alex Chen (Student A)", email: "alex@university.edu" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Jordan Taylor (Student B)", email: "jordan@university.edu" },
];

export const ExamModePage: React.FC = () => {
  const [activeUser, setActiveUser] = useState(DEMO_USERS[0]);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [overview, setOverview] = useState<ExamOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Paper upload state
  const [paperFile, setPaperFile] = useState<File | null>(null);
  const [paperYear, setPaperYear] = useState<string>("");
  const [uploadingPaper, setUploadingPaper] = useState(false);
  const [paperNotice, setPaperNotice] = useState<string | null>(null);
  const [deletingPaperId, setDeletingPaperId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Expanded repeated question cluster keys
  const [expandedClusters, setExpandedClusters] = useState<Record<string, boolean>>({});

  // Marks-based answer panel state (Feature F20)
  const [customQuestion, setCustomQuestion] = useState("");
  const [selectedMarks, setSelectedMarks] = useState<ExamMarks>(5);
  const [answering, setAnswering] = useState(false);
  const [answerResult, setAnswerResult] = useState<MarksAnswerResult | null>(null);

  const authHeaders = (user = activeUser) => ({
    "x-test-user-id": user.id,
    "x-test-user-email": user.email,
  });

  // Load subjects for active student
  useEffect(() => {
    const loadSubjects = async () => {
      setError(null);
      try {
        const res = await fetch("/api/subjects", { headers: authHeaders() });
        if (!res.ok) throw new Error("Failed to load subjects");
        const data: SubjectItem[] = await res.json();
        setSubjects(data);
        if (data.length > 0) {
          const savedId = localStorage.getItem("studygraph_exam_subject_id");
          const match = data.find((s) => s.id === savedId);
          setSelectedSubjectId(match ? match.id : data[0].id);
        } else {
          setSelectedSubjectId("");
          setOverview(null);
        }
      } catch (err: any) {
        setError(err.message || "Could not load subjects.");
      }
    };
    loadSubjects();
  }, [activeUser.id]);

  const fetchOverview = async (subjectId: string, silent = false) => {
    if (!subjectId) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/subjects/${subjectId}/exam/overview`, {
        headers: authHeaders(),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to load Exam Mode overview");
      }
      const data: ExamOverview = await res.json();
      setOverview(data);
    } catch (err: any) {
      setError(err.message || "Failed to load Exam Mode data.");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedSubjectId) {
      setAnswerResult(null);
      setPaperNotice(null);
      fetchOverview(selectedSubjectId);
    }
  }, [selectedSubjectId, activeUser.id]);

  // Poll overview while any uploaded paper is still queued or extracting
  useEffect(() => {
    if (!overview || !selectedSubjectId) return;
    const hasPending = overview.papers.some(
      (p) => p.status === "queued" || p.status === "extracting"
    );
    if (!hasPending) return;

    const timer = setInterval(() => {
      fetchOverview(selectedSubjectId, true);
    }, 1500);
    return () => clearInterval(timer);
  }, [overview, selectedSubjectId, activeUser.id]);

  const handleSubjectChange = (newId: string) => {
    setSelectedSubjectId(newId);
    localStorage.setItem("studygraph_exam_subject_id", newId);
  };

  const handleUploadPaper = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!paperFile || !selectedSubjectId || uploadingPaper) return;

    setUploadingPaper(true);
    setError(null);
    setPaperNotice(null);

    const formData = new FormData();
    formData.append("file", paperFile);
    if (paperYear.trim()) {
      formData.append("year", paperYear.trim());
    }

    try {
      const res = await fetch(`/api/subjects/${selectedSubjectId}/exam/papers`, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Paper upload failed.");
      }
      setPaperNotice(`Uploaded "${data.filename}". Parsing questions & checking repeats...`);
      setPaperFile(null);
      setPaperYear("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await fetchOverview(selectedSubjectId, true);
    } catch (err: any) {
      setError(err.message || "Could not upload question paper.");
    } finally {
      setUploadingPaper(false);
    }
  };

  const handleDeletePaper = async (paperId: string, filename: string) => {
    if (!selectedSubjectId) return;
    setDeletingPaperId(paperId);
    setError(null);
    setPaperNotice(null);
    try {
      const res = await fetch(`/api/subjects/${selectedSubjectId}/exam/papers/${paperId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete paper.");
      }
      setPaperNotice(`Removed "${filename}". Repeat counts updated.`);
      await fetchOverview(selectedSubjectId, true);
    } catch (err: any) {
      setError(err.message || "Could not delete paper.");
    } finally {
      setDeletingPaperId(null);
    }
  };

  const handleAskMarksAnswer = async (questionText: string, marks: ExamMarks) => {
    const cleanQ = questionText.trim();
    if (!cleanQ || !selectedSubjectId || answering) return;

    setSelectedMarks(marks);
    setCustomQuestion(cleanQ);
    setAnswering(true);
    setError(null);

    try {
      const res = await fetch(`/api/subjects/${selectedSubjectId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeaders(),
        },
        body: JSON.stringify({ question: cleanQ, marks }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || "Failed to generate marks-based answer.");
      }
      setAnswerResult({
        question: cleanQ,
        marks,
        text: data.text,
        answered_from: data.answered_from,
        confidence: data.confidence ?? 0,
        citations: data.citations || [],
      });
    } catch (err: any) {
      setError(err.message || "Could not generate answer.");
    } finally {
      setAnswering(false);
    }
  };

  const toggleCluster = (key: string) => {
    setExpandedClusters((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-4 space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <GraduationCap className="w-5 h-5 text-indigo-600" />
            Exam Mode (F18 &bull; F19 &bull; F20)
            <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full border border-indigo-100">
              Honest Revision Engine
            </span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Graph-ranked important concepts, real paper repeat counts (never fabricated), and 2 / 5 / 10-mark grounded answers.
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs">
            <User className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={activeUser.id}
              onChange={(e) => {
                const u = DEMO_USERS.find((item) => item.id === e.target.value);
                if (u) setActiveUser(u);
              }}
              className="bg-transparent font-semibold text-slate-800 outline-hidden cursor-pointer"
            >
              {DEMO_USERS.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs">
            <Folder className="w-3.5 h-3.5 text-indigo-600" />
            <select
              value={selectedSubjectId}
              onChange={(e) => handleSubjectChange(e.target.value)}
              disabled={subjects.length === 0}
              className="bg-transparent font-semibold text-slate-800 outline-hidden cursor-pointer"
            >
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {selectedSubjectId && (
            <button
              type="button"
              onClick={() => fetchOverview(selectedSubjectId)}
              className="p-2 rounded-lg border border-slate-200 bg-white text-slate-600 hover:text-indigo-600 hover:border-indigo-200 transition cursor-pointer"
              title="Refresh Exam Mode"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-xl p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-rose-500 hover:text-rose-700 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Marks-Based Answer Generator (Feature F20) */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              Marks-Based Exam Answer Generator (F20)
            </h2>
            <p className="text-xs text-slate-500">
              Ask any question or click <b>2m / 5m / 10m</b> on any concept or repeated question below. Answers cite your notes.
            </p>
          </div>

          <div className="flex items-center gap-1.5">
            {([2, 5, 10] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setSelectedMarks(m)}
                className={`px-3 py-1 rounded-lg text-xs font-bold border transition cursor-pointer ${
                  selectedMarks === m
                    ? "bg-indigo-600 text-white border-indigo-600 shadow-2xs"
                    : "bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100"
                }`}
              >
                {m} Marks
              </button>
            ))}
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleAskMarksAnswer(customQuestion, selectedMarks);
          }}
          className="flex flex-col sm:flex-row gap-2"
        >
          <input
            type="text"
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            placeholder={`Ask an exam question for ${selectedMarks} marks (${getMarksDescription(selectedMarks)})...`}
            disabled={!selectedSubjectId || answering}
            className="flex-1 px-3.5 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
          />
          <button
            type="submit"
            disabled={!selectedSubjectId || !customQuestion.trim() || answering}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5 cursor-pointer"
          >
            {answering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            <span>Generate {selectedMarks}-Mark Answer</span>
          </button>
        </form>

        {answerResult && (
          <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/70 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-200">
              <div className="flex items-center gap-2 flex-wrap">
                {answerResult.answered_from === "notes" ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    Grounded in Notes
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                    <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                    Not in Notes &bull; General Knowledge
                  </span>
                )}
                <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200">
                  {answerResult.marks} Marks ({getMarksDescription(answerResult.marks)})
                </span>
              </div>
              <button
                type="button"
                onClick={() => setAnswerResult(null)}
                className="text-slate-400 hover:text-slate-700 cursor-pointer"
                title="Close answer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="text-xs font-semibold text-slate-600">
              Question: <span className="text-slate-900">{answerResult.question}</span>
            </div>

            <div className="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap bg-white p-3.5 rounded-lg border border-slate-200">
              {answerResult.text}
            </div>

            {answerResult.citations.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                  <BookOpen className="w-3 h-3 text-indigo-500" />
                  Citations from your notes:
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {answerResult.citations.map((cit, idx) => (
                    <CitationBadge key={idx} citation={cit} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Two-Column Exam Mode Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Column: Important Concepts (F18) */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Network className="w-4 h-4 text-indigo-600" />
                Important Concepts
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Ranked by graph connectivity (links &amp; strength) and module/source coverage.
              </p>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
              <Award className="w-3.5 h-3.5" />
              {overview?.important_concepts_label || IMPORTANT_CONCEPTS_LABEL}
            </span>
          </div>

          {loading && !overview ? (
            <div className="py-12 flex items-center justify-center gap-2 text-xs text-slate-500">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-600" />
              Computing graph centrality &amp; coverage...
            </div>
          ) : !overview || overview.important_concepts.length === 0 ? (
            <div className="border border-dashed border-slate-200 rounded-lg p-8 text-center text-xs text-slate-500">
              No extracted topics in this subject yet. Upload lecture notes or a textbook first to build the concept graph.
            </div>
          ) : (
            <div className="space-y-3">
              {overview.important_concepts.map((concept, index) => (
                <div
                  key={concept.topic_id}
                  className="border border-slate-200 rounded-xl p-3.5 hover:border-indigo-200 transition space-y-2 bg-slate-50/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
                        {index + 1}
                      </span>
                      <h3 className="text-sm font-bold text-slate-900">{concept.keyword}</h3>
                      {concept.module_no && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">
                          Mod {concept.module_no}
                        </span>
                      )}
                      {!concept.reviewed && (
                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                          Unreviewed
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100 shrink-0">
                      Score {Math.round(concept.importance_score * 100)}%
                    </span>
                  </div>

                  <p className="text-xs text-slate-700 leading-relaxed">{concept.explanation}</p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                      <span>{concept.degree} links (strength {concept.weighted_degree})</span>
                      <span>&bull;</span>
                      <span>{concept.modules_covered} module{concept.modules_covered === 1 ? "" : "s"}</span>
                      <span>&bull;</span>
                      <span>{concept.source_count} note chunk{concept.source_count === 1 ? "" : "s"}</span>
                    </div>

                    <div className="flex items-center gap-1">
                      {([2, 5, 10] as const).map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => handleAskMarksAnswer(`Explain ${concept.keyword}`, m)}
                          className="px-2 py-0.5 text-[10px] font-bold rounded border border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition cursor-pointer"
                          title={`Generate ${m}-mark answer for ${concept.keyword}`}
                        >
                          {m}m
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Column: Repeated Questions from Uploaded Papers (F19, R05) */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-4 h-4 text-emerald-600" />
                Repeated Questions
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Grouped by semantic embeddings + LLM confirmation across your uploaded papers.
              </p>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {overview?.repeated_questions_label || REPEATED_QUESTIONS_LABEL}
            </span>
          </div>

          {/* Upload Previous-Year Paper Form */}
          <form
            onSubmit={handleUploadPaper}
            className="bg-slate-50 border border-slate-200 rounded-xl p-3.5 space-y-2.5"
          >
            <div className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5 text-indigo-600" />
              Upload Previous-Year Question Paper (PDF or Image)
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg"
                onChange={(e) => setPaperFile(e.target.files?.[0] || null)}
                className="flex-1 text-xs text-slate-600 file:mr-2.5 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer"
              />
              <input
                type="number"
                placeholder="Year (e.g. 2024)"
                min={1990}
                max={2100}
                value={paperYear}
                onChange={(e) => setPaperYear(e.target.value)}
                className="w-32 px-2.5 py-1.5 text-xs bg-white border border-slate-300 rounded-lg focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20"
              />
              <button
                type="submit"
                disabled={!paperFile || !selectedSubjectId || uploadingPaper}
                className="px-3.5 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5 cursor-pointer"
              >
                {uploadingPaper ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                <span>Upload Paper</span>
              </button>
            </div>
          </form>

          {paperNotice && (
            <div className="bg-indigo-50 border border-indigo-200 text-indigo-800 text-xs rounded-lg p-2.5 flex items-center justify-between">
              <span>{paperNotice}</span>
              <button onClick={() => setPaperNotice(null)} className="text-indigo-500 hover:text-indigo-800 cursor-pointer">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Uploaded Papers List with Delete Action */}
          {overview && overview.papers.length > 0 && (
            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Uploaded Papers ({overview.papers.length})
              </div>
              <div className="space-y-1.5">
                {overview.papers.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-slate-200 bg-white text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      <span className="font-semibold text-slate-800 truncate">{p.filename}</span>
                      {p.year && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-bold shrink-0">
                          {p.year}
                        </span>
                      )}
                      {p.status === "queued" || p.status === "extracting" ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200 shrink-0">
                          <Clock className="w-3 h-3 animate-spin" />
                          {p.status}
                        </span>
                      ) : p.status === "failed" ? (
                        <span className="text-[10px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200 shrink-0">
                          failed
                        </span>
                      ) : (
                        <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 shrink-0">
                          {p.question_count} Qs
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => handleDeletePaper(p.id, p.filename)}
                      disabled={deletingPaperId === p.id}
                      className="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-semibold text-rose-600 hover:bg-rose-50 rounded-md border border-transparent hover:border-rose-200 transition cursor-pointer shrink-0"
                      title="Remove this uploaded paper"
                    >
                      {deletingPaperId === p.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                      <span>Remove</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Honest Empty State or Repeated Question Clusters */}
          {overview && !overview.has_uploaded_papers ? (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-2">
              <div className="flex items-start gap-2.5">
                <ShieldAlert className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <h3 className="text-xs font-bold text-amber-900">
                    No Uploaded Papers Yet (Zero Fabricated Repeats)
                  </h3>
                  <p className="text-xs text-amber-800 leading-relaxed">
                    {overview.honest_notice}
                  </p>
                  <p className="text-[11px] text-amber-700">
                    Meanwhile, use the <b>Important Concepts (by graph importance)</b> list on the left to prioritize high-impact topics.
                  </p>
                </div>
              </div>
            </div>
          ) : overview ? (
            <div className="space-y-3">
              {overview.honest_notice && (
                <div className="bg-slate-50 border border-slate-200 text-slate-700 text-xs rounded-lg p-3 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                  <span>{overview.honest_notice}</span>
                </div>
              )}

              {overview.repeated_questions.map((cluster) => {
                const isExpanded = !!expandedClusters[cluster.cluster_key];
                const isRepeated = cluster.repeat_count >= 2;
                return (
                  <div
                    key={cluster.cluster_key}
                    className={`border rounded-xl p-3.5 space-y-2 transition ${
                      isRepeated
                        ? "border-emerald-200 bg-emerald-50/30"
                        : "border-slate-200 bg-white"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] font-bold px-2.5 py-0.5 rounded-full border ${
                          isRepeated
                            ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                            : "bg-slate-100 text-slate-700 border-slate-200"
                        }`}
                      >
                        {formatPaperFrequencyLabel(cluster.repeat_count, cluster.total_papers)}
                      </span>

                      <div className="flex items-center gap-1.5">
                        {cluster.typical_marks && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                            {cluster.typical_marks} Marks
                          </span>
                        )}
                        {cluster.matched_topic_keyword && (
                          <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                            Topic: {cluster.matched_topic_keyword}
                          </span>
                        )}
                      </div>
                    </div>

                    <p className="text-sm font-semibold text-slate-900 leading-snug">
                      {cluster.canonical_question}
                    </p>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => toggleCluster(cluster.cluster_key)}
                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 cursor-pointer"
                      >
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        <span>
                          {isExpanded ? "Hide" : "Show"} {cluster.occurrences.length} paper occurrence
                          {cluster.occurrences.length === 1 ? "" : "s"}
                        </span>
                      </button>

                      <div className="flex items-center gap-1">
                        {([2, 5, 10] as const).map((m) => (
                          <button
                            key={m}
                            type="button"
                            onClick={() => handleAskMarksAnswer(cluster.canonical_question, m)}
                            className="px-2 py-0.5 text-[10px] font-bold rounded border border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-600 hover:text-white transition cursor-pointer"
                            title={`Answer this exam question for ${m} marks`}
                          >
                            {m}m
                          </button>
                        ))}
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="pt-2 border-t border-slate-200/80 space-y-1.5">
                        {cluster.occurrences.map((occ) => (
                          <div
                            key={occ.question_id}
                            className="text-xs bg-white border border-slate-200 rounded-lg p-2.5 space-y-1"
                          >
                            <div className="flex items-center justify-between text-[11px] text-slate-500 font-semibold">
                              <span>
                                {occ.filename}
                                {occ.year ? ` (${occ.year})` : ""}
                              </span>
                              {occ.marks && <span>{occ.marks} Marks</span>}
                            </div>
                            <p className="text-slate-700">{occ.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

