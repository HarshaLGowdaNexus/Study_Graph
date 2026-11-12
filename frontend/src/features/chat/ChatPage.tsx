import React, { useState, useEffect, useRef } from "react";
import {
  MessageSquare,
  Send,
  Sparkles,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  BookOpen,
  Folder,
  RefreshCw,
  HelpCircle,
  ChevronRight,
  User,
  Bot,
  Plus,
  Trash2,
} from "lucide-react";
import { CitationBadge, CitationItemData } from "./CitationBadge";

interface SubjectItem {
  id: string;
  name: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  marks?: 2 | 5 | 10 | null;
  answered_from?: "notes" | "general";
  confidence?: number;
  citations: CitationItemData[];
  created_at?: string;
}

const DEMO_USERS = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Alex Chen (Student A)", email: "alex@university.edu" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Jordan Taylor (Student B)", email: "jordan@university.edu" },
];

const SUGGESTED_QUESTIONS = [
  {
    type: "in-notes",
    text: "What are the seven layers of the OSI model in order from physical to application?",
    label: "OSI 7 Layers (In Notes)",
  },
  {
    type: "in-notes",
    text: "How does a TCP 3-way handshake establish a connection between client and server?",
    label: "TCP Handshake (In Notes)",
  },
  {
    type: "in-notes",
    text: "What is the primary difference between TCP and UDP regarding reliability?",
    label: "TCP vs UDP (In Notes)",
  },
  {
    type: "out-of-notes",
    text: "How does Shor's quantum algorithm factor large composite integers in polynomial time?",
    label: "Quantum Shor's (Out of Notes)",
  },
  {
    type: "out-of-notes",
    text: "What are the primary stylistic differences between Renaissance and Baroque oil painting?",
    label: "Art History (Out of Notes)",
  },
];

export const ChatPage: React.FC = () => {
  const [activeUser, setActiveUser] = useState(DEMO_USERS[0]);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuestion, setInputQuestion] = useState("");
  const [selectedMarks, setSelectedMarks] = useState<2 | 5 | 10 | null>(null);
  const [loading, setLoading] = useState(false);
  const [subjectsLoading, setSubjectsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Fetch student subjects
  useEffect(() => {
    fetchSubjects(activeUser.id, activeUser.email);
  }, [activeUser.id]);

  // Load chat history when subject changes
  useEffect(() => {
    if (selectedSubjectId) {
      fetchChatHistory(selectedSubjectId, activeUser.id, activeUser.email);
    } else {
      setMessages([]);
    }
  }, [selectedSubjectId, activeUser.id]);

  const fetchSubjects = async (userId: string, userEmail: string) => {
    setSubjectsLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/subjects", {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (!res.ok) throw new Error("Failed to load your enrolled subjects");
      const data: SubjectItem[] = await res.json();
      setSubjects(data);
      if (data.length > 0) {
        const savedSubjectId = localStorage.getItem("studygraph_chat_subject_id");
        const found = data.find((s) => s.id === savedSubjectId);
        if (found) {
          setSelectedSubjectId(found.id);
        } else {
          // If Operating Systems exists, prioritize it or default to first
          const osSub = data.find((s) => s.name.toLowerCase().includes("operating system"));
          setSelectedSubjectId(osSub ? osSub.id : data[0].id);
        }
      } else {
        setSelectedSubjectId("");
      }
    } catch (err: any) {
      setError(err.message || "Failed to load subjects.");
    } finally {
      setSubjectsLoading(false);
    }
  };

  const handleSubjectChange = (newSubjectId: string) => {
    setSelectedSubjectId(newSubjectId);
    localStorage.setItem("studygraph_chat_subject_id", newSubjectId);
  };

  const handleClearChat = async () => {
    if (!selectedSubjectId || messages.length === 0) return;
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/subjects/${selectedSubjectId}/chat/history`, {
        method: "DELETE",
        headers: {
          "x-test-user-id": activeUser.id,
          "x-test-user-email": activeUser.email,
        },
      });
      if (!res.ok) throw new Error("Failed to clear chat history");
      setMessages([]);
    } catch (err: any) {
      setError(err.message || "Failed to clear chat history.");
    } finally {
      setLoading(false);
    }
  };

  const fetchChatHistory = async (subjectId: string, userId: string, userEmail: string) => {
    try {
      const res = await fetch(`/api/subjects/${subjectId}/chat/history`, {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (err) {
      console.error("Error fetching chat history:", err);
    }
  };

  const handleSend = async (questionToSend?: string) => {
    const q = (questionToSend || inputQuestion).trim();
    if (!q || loading || !selectedSubjectId) return;

    // Optimistically append user message
    const tempUserMsg: ChatMessage = {
      id: "temp-" + Date.now(),
      role: "user",
      text: q,
      citations: [],
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setInputQuestion("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`/api/subjects/${selectedSubjectId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-test-user-id": activeUser.id,
          "x-test-user-email": activeUser.email,
        },
        body: JSON.stringify({ question: q, marks: selectedMarks }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Error querying the notes chatbot");
      }

      const answerData = await res.json();
      const assistantMsg: ChatMessage = {
        id: answerData.id,
        role: "assistant",
        text: answerData.text,
        marks: answerData.marks ?? selectedMarks,
        answered_from: answerData.answered_from,
        confidence: answerData.confidence,
        citations: answerData.citations || [],
        created_at: answerData.created_at,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      setError(err.message || "Could not retrieve answer. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId);

  return (
    <div className="max-w-5xl mx-auto px-4 py-4 space-y-4">
      {/* Top Header & Student Selector */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-indigo-600" />
            Study Chat (F14)
            <span className="text-xs bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full border border-indigo-100">
              Honest RAG Engine
            </span>
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Answers strictly from your notes with file & page citations. Never bluffs on topics not in your notes.
          </p>
        </div>

        {/* Student Switcher & Subject Picker */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 bg-slate-50 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs">
            <User className="w-3.5 h-3.5 text-slate-500" />
            <select
              value={activeUser.id}
              onChange={(e) => {
                const u = DEMO_USERS.find((user) => user.id === e.target.value);
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
              disabled={subjectsLoading || subjects.length === 0}
              className="bg-transparent font-semibold text-slate-800 outline-hidden cursor-pointer"
            >
              {subjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Main Chat Workspace */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs flex flex-col h-[650px] overflow-hidden">
        {/* Chat Banner */}
        <div className="bg-slate-50 px-5 py-2.5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span className="font-medium text-slate-700">
              Active Subject:
            </span>
            <div className="flex items-center gap-1.5">
              {subjects.map((sub) => (
                <button
                  key={sub.id}
                  type="button"
                  onClick={() => handleSubjectChange(sub.id)}
                  className={`px-2.5 py-0.5 rounded-md text-xs font-bold transition cursor-pointer ${
                    sub.id === selectedSubjectId
                      ? "bg-indigo-600 text-white shadow-2xs"
                      : "bg-white text-slate-600 hover:bg-slate-100 border border-slate-300"
                  }`}
                >
                  {sub.name}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleClearChat}
              disabled={messages.length === 0 || loading}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md 
                         border border-slate-200 bg-white text-slate-700 hover:text-indigo-600 hover:border-indigo-300 
                         disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer shadow-2xs"
              title="Clear conversation history and start a fresh chat"
            >
              <Plus className="w-3.5 h-3.5 text-indigo-600" />
              <span>New Chat</span>
            </button>

            <span className="h-3.5 w-px bg-slate-200 hidden sm:inline-block"></span>

            <div className="hidden sm:flex items-center gap-3 text-slate-400">
              <span className="flex items-center gap-1 text-[11px]">
                <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
                Grounded in Notes
              </span>
              <span className="flex items-center gap-1 text-[11px]">
                <span className="w-2 h-2 rounded-full bg-amber-500 inline-block"></span>
                Not in Notes (General)
              </span>
            </div>
          </div>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-slate-50/40">
          {messages.length === 0 && !loading && (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 space-y-3">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600">
                <Bot className="w-6 h-6" />
              </div>
              <div className="max-w-md space-y-1">
                <h3 className="text-sm font-bold text-slate-800">
                  Ask StudyGraph about {selectedSubject?.name || "your notes"}
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Questions are embedded and matched against your uploaded PDF chunks. If an answer is found, you get exact page citations. If not, it refuses to bluff.
                </p>
              </div>

              {/* Quick Questions */}
              <div className="mt-4 pt-4 border-t border-slate-200 w-full max-w-lg">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Sample test questions (from T02 ground truth):
                </p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {SUGGESTED_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(q.text)}
                      className={`text-xs px-2.5 py-1.5 rounded-lg border text-left transition cursor-pointer flex items-center gap-1.5 shadow-2xs ${
                        q.type === "in-notes"
                          ? "bg-emerald-50/70 border-emerald-200 text-emerald-800 hover:bg-emerald-100"
                          : "bg-amber-50/70 border-amber-200 text-amber-800 hover:bg-amber-100"
                      }`}
                    >
                      <span>{q.label}</span>
                      <ChevronRight className="w-3 h-3 opacity-60" />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Render Messages */}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-xs">
                  <Bot className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-[85%] rounded-2xl p-4 space-y-2.5 ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-tr-none shadow-xs"
                    : "bg-white border border-slate-200 text-slate-800 rounded-tl-none shadow-xs"
                }`}
              >
                {/* Header status badge for Assistant */}
                {msg.role === "assistant" && (
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-100 text-xs">
                    {msg.answered_from === "notes" ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 text-[11px]">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        Grounded in Notes
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 font-semibold text-amber-800 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200 text-[11px]">
                        <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                        Not in Notes &bull; General Knowledge
                      </span>
                    )}

                    <div className="flex items-center gap-2">
                      {msg.marks && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {msg.marks} Marks Format
                        </span>
                      )}
                      {msg.confidence !== undefined && (
                        <span className="text-[10px] text-slate-400 font-medium">
                          Similarity: {Math.round(msg.confidence * 100)}%
                        </span>
                      )}
                    </div>
                  </div>
                )}

                {/* Message Text */}
                <div className="text-sm leading-relaxed whitespace-pre-wrap">
                  {msg.text}
                </div>

                {/* Citations section if answered from notes */}
                {msg.role === "assistant" && msg.citations && msg.citations.length > 0 && (
                  <div className="pt-2 border-t border-slate-100 space-y-1.5">
                    <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
                      <BookOpen className="w-3 h-3 text-indigo-500" />
                      Sources Cited (Click to inspect):
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((c, cIdx) => (
                        <CitationBadge key={cIdx} citation={c} />
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-xs">
                  <User className="w-4 h-4" />
                </div>
              )}
            </div>
          ))}

          {/* Loading Animation */}
          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shrink-0 mt-0.5 shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-none p-4 shadow-xs space-y-2 max-w-sm">
                <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  Embedding question & searching notes...
                </div>
                <p className="text-xs text-slate-400">
                  Retrieving matching chunks from pgvector and checking confidence threshold (0.60)...
                </p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Error Notice */}
        {error && (
          <div className="px-5 py-2 bg-rose-50 border-t border-rose-200 text-xs text-rose-700 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <AlertCircle className="w-4 h-4 text-rose-600" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-rose-500 hover:text-rose-700 font-bold"
            >
              &times;
            </button>
          </div>
        )}

        {/* Question Input Footer */}
        <div className="p-3 bg-white border-t border-slate-200 space-y-2">
          {/* Marks-Based Answer Format Selector (Feature F20) */}
          <div className="flex flex-wrap items-center justify-between gap-2 px-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] font-semibold text-slate-500">Answer Length:</span>
              {([null, 2, 5, 10] as const).map((m) => (
                <button
                  key={m ?? "std"}
                  type="button"
                  onClick={() => setSelectedMarks(m)}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-semibold border transition cursor-pointer ${
                    selectedMarks === m
                      ? "bg-indigo-600 text-white border-indigo-600 shadow-2xs"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  {m === null ? "Standard" : `${m} Marks`}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-slate-400">
              {selectedMarks === 2
                ? "1-2 crisp lines"
                : selectedMarks === 5
                ? "Short structured bullet points"
                : selectedMarks === 10
                ? "Detailed structured headings"
                : "Default study answer"}
            </span>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder={`Ask a question about ${selectedSubject?.name || "your notes"}...`}
              disabled={loading || !selectedSubjectId}
              className="flex-1 px-4 py-2.5 text-sm bg-slate-50 border border-slate-200 rounded-xl 
                         focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition"
            />
            <button
              type="submit"
              disabled={loading || !inputQuestion.trim() || !selectedSubjectId}
              className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl font-semibold text-sm 
                         hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition 
                         flex items-center gap-1.5 shadow-xs cursor-pointer"
            >
              <Send className="w-4 h-4" />
              <span>Ask</span>
            </button>
          </form>
          <div className="flex items-center justify-between px-1 pt-2 text-[11px] text-slate-400">
            <span>Anti-hallucination active &bull; Rule 13.4 &bull; Citations with page numbers</span>
            <span>Confidence threshold: 0.60</span>
          </div>
        </div>
      </div>
    </div>
  );
};

