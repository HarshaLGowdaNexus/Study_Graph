import React, { useState, useEffect, useRef } from "react";
import {
  Upload,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  FolderPlus,
  BookOpen,
  ShieldCheck,
  RefreshCw,
  X,
  Sparkles,
} from "lucide-react";
import { TopicReviewModal } from "../review/TopicReviewModal";

// Student Profiles for testing user isolation (Privacy Rule 11)
const DEMO_USERS = [
  { id: "11111111-1111-4111-8111-111111111111", name: "Alex Chen (Student A)", email: "alex@university.edu" },
  { id: "22222222-2222-4222-8222-222222222222", name: "Jordan Taylor (Student B)", email: "jordan@university.edu" },
];

const ALLOWED_EXTS = [".pdf", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"];
const MAX_FILE_SIZE_MB = 50;

interface Subject {
  id: string;
  name: string;
  source_preference: string;
}

interface DocumentItem {
  id: string;
  filename: string;
  status: "queued" | "extracting" | "done" | "failed" | string;
  module_no?: number;
  error_message?: string;
  storage_path?: string;
  uploaded_at?: string;
  summary?: string;
  topic_count?: number;
  unreviewed_count?: number;
}

export const UploadPage: React.FC = () => {
  // Current Student state (Privacy demonstration)
  const [activeUser, setActiveUser] = useState(DEMO_USERS[0]);

  // Subject and Module selection
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [moduleNo, setModuleNo] = useState<number>(1);
  const [sourceKind, setSourceKind] = useState<string>("notes");

  // New subject inline creation
  const [newSubjectName, setNewSubjectName] = useState<string>("");
  const [isCreatingSubject, setIsCreatingSubject] = useState<boolean>(false);

  // File state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState<boolean>(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // Documents and tracking
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Review Screen Modal state (T06)
  const [reviewingDoc, setReviewingDoc] = useState<DocumentItem | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset all upload inputs & transient notifications cleanly
  const resetUploadState = () => {
    setSelectedFile(null);
    setClientError(null);
    setStatusMessage(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Fetch subjects for a specific user ID
  const fetchSubjectsForUser = async (userId: string, userEmail: string) => {
    try {
      const res = await fetch("/api/subjects", {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (res.ok) {
        const data: Subject[] = await res.json();
        setSubjects(data);
        if (data.length > 0) {
          setSelectedSubjectId(data[0].id);
          loadDocumentsForSubject(data[0].id, userId, userEmail);
        } else {
          setSelectedSubjectId("");
          setDocuments([]);
        }
      }
    } catch (err) {
      console.error("Failed to fetch subjects:", err);
    }
  };

  // Fetch documents for a given subject and user
  const loadDocumentsForSubject = async (subId: string, userId: string, userEmail: string) => {
    if (!subId) {
      setDocuments([]);
      return;
    }
    try {
      const res = await fetch(`/api/subjects/${subId}/documents`, {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (res.ok) {
        const data: DocumentItem[] = await res.json();
        setDocuments(data);
      }
    } catch (err) {
      console.error("Failed to load documents:", err);
    }
  };

  // Switch student handler: cleanly resets all old banners and reloads student's private workspace
  const handleSwitchUser = (newUserId: string) => {
    const user = DEMO_USERS.find((u) => u.id === newUserId);
    if (!user) return;

    setActiveUser(user);
    resetUploadState();
    setSelectedSubjectId("");
    setDocuments([]);
    setIsCreatingSubject(false);
    setNewSubjectName("");

    // Fetch new student's private folders
    fetchSubjectsForUser(user.id, user.email);
  };

  // Initial load
  useEffect(() => {
    fetchSubjectsForUser(activeUser.id, activeUser.email);
  }, []);

  // When selected subject changes, reload documents for that folder
  const handleSubjectChange = (newSubjectId: string) => {
    setSelectedSubjectId(newSubjectId);
    resetUploadState();
    loadDocumentsForSubject(newSubjectId, activeUser.id, activeUser.email);
  };

  // Live polling for in-progress documents (queued or extracting)
  useEffect(() => {
    const hasPending = documents.some((d) => d.status === "queued" || d.status === "extracting");
    if (!hasPending) return;

    const interval = setInterval(async () => {
      let updated = false;
      const updatedList = await Promise.all(
        documents.map(async (doc) => {
          if (doc.status === "queued" || doc.status === "extracting") {
            try {
              const res = await fetch(`/api/documents/${doc.id}/status`, {
                headers: {
                  "x-test-user-id": activeUser.id,
                  "x-test-user-email": activeUser.email,
                },
              });
              if (res.ok) {
                const refreshedDoc: DocumentItem = await res.json();
                if (refreshedDoc.status !== doc.status) {
                  updated = true;
                }
                return refreshedDoc;
              }
            } catch (err) {
              console.error("Polling error for doc:", doc.id, err);
            }
          }
          return doc;
        })
      );

      if (updated) {
        setDocuments(updatedList);
      }
    }, 1200);

    return () => clearInterval(interval);
  }, [documents, activeUser.id, activeUser.email]);

  // File validation
  const validateAndSetFile = (file: File) => {
    // Clear any previous error or success banners immediately when picking a new file
    setClientError(null);
    setStatusMessage(null);

    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ALLOWED_EXTS.includes(ext)) {
      setClientError(
        `Friendly Notice: "${file.name}" is an unsupported file format. Please upload PDF, PowerPoint (.ppt, .pptx), or image (.png, .jpg) notes.`
      );
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    const sizeMb = file.size / (1024 * 1024);
    if (sizeMb > MAX_FILE_SIZE_MB) {
      setClientError(
        `File is too large (${sizeMb.toFixed(1)} MB). The maximum allowed upload size is ${MAX_FILE_SIZE_MB} MB.`
      );
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setSelectedFile(file);
  };

  // Drag and drop handlers
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  // Create subject (either custom name or quick starter)
  const createSubjectWithName = async (name: string) => {
    if (!name.trim()) return;

    try {
      const res = await fetch("/api/subjects", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-test-user-id": activeUser.id,
          "x-test-user-email": activeUser.email,
        },
        body: JSON.stringify({ name: name.trim(), source_preference: "notes" }),
      });

      if (res.ok) {
        const created: Subject = await res.json();
        setSubjects((prev) => [...prev, created]);
        setSelectedSubjectId(created.id);
        setDocuments([]);
        setNewSubjectName("");
        setIsCreatingSubject(false);
      }
    } catch (err) {
      console.error("Error creating subject:", err);
    }
  };

  const handleCreateSubject = async (e: React.FormEvent) => {
    e.preventDefault();
    await createSubjectWithName(newSubjectName);
  };

  // Upload handler
  const handleUpload = async () => {
    if (!selectedFile) {
      setClientError("Please choose a lecture notes file to upload.");
      return;
    }
    if (!selectedSubjectId) {
      setClientError("Please choose or create a subject folder first.");
      return;
    }

    setIsUploading(true);
    setClientError(null);
    setStatusMessage(null);

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("subject_id", selectedSubjectId);
    formData.append("module_no", moduleNo.toString());
    formData.append("source_kind", sourceKind);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        headers: {
          "x-test-user-id": activeUser.id,
          "x-test-user-email": activeUser.email,
        },
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        setClientError(data.detail || "Upload failed. Please check the file and try again.");
      } else {
        setStatusMessage(`"${selectedFile.name}" uploaded successfully! Background processing started.`);
        // Reset file input after upload so the dropzone is ready for the next file
        setSelectedFile(null);
        if (fileInputRef.current) fileInputRef.current.value = "";

        // Add newly queued document to the top of the list immediately
        const newDoc: DocumentItem = {
          id: data.id,
          filename: data.filename,
          status: data.status,
          module_no: data.module_no,
          storage_path: data.storage_path,
          uploaded_at: new Date().toISOString(),
        };
        setDocuments((prev) => [newDoc, ...prev]);
      }
    } catch (err) {
      setClientError("Could not reach backend server. Please verify the server is running.");
    } finally {
      setIsUploading(false);
    }
  };

  // Compute clear, honest state for the upload button
  const canUpload = Boolean(selectedFile && selectedSubjectId && !isUploading);

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-8">
      {/* Top Header */}
      <div className="border-b border-slate-200 pb-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <BookOpen className="w-7 h-7 text-indigo-600" />
            StudyGraph Ingestion Hub
          </h1>
          <p className="text-slate-600 text-sm mt-1">
            Upload study notes into organized Subject & Module folders with real-time background processing.
          </p>
        </div>

        {/* User Privacy Switcher (Demonstrates Rule 11: Privacy) */}
        <div className="bg-white border border-slate-200 rounded-lg p-2.5 shadow-sm flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            Active Student:
          </div>
          <select
            value={activeUser.id}
            onChange={(e) => handleSwitchUser(e.target.value)}
            className="text-sm font-medium text-slate-800 bg-slate-50 border border-slate-300 rounded px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
          >
            {DEMO_USERS.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Folder Configuration & Upload Box */}
        <div className="lg:col-span-2 space-y-6">
          {/* Folder Hierarchy Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <FolderPlus className="w-5 h-5 text-indigo-600" />
              1. Choose Destination Folder
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Subject Selection */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Subject Folder
                </label>
                {subjects.length > 0 ? (
                  <select
                    value={selectedSubjectId}
                    onChange={(e) => handleSubjectChange(e.target.value)}
                    className="w-full text-sm border border-slate-300 rounded-lg p-2.5 bg-white text-slate-800 focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                  >
                    {subjects.map((sub) => (
                      <option key={sub.id} value={sub.id}>
                        {sub.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="space-y-2">
                    <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 p-2.5 rounded-lg flex items-start gap-1.5">
                      <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                      <span>No subjects found for <b>{activeUser.name.split(" ")[0]}</b> yet.</span>
                    </div>
                    {/* 1-Click quick starter folder */}
                    <button
                      type="button"
                      onClick={() => createSubjectWithName(activeUser.id.startsWith("1111") ? "Database Systems" : "Operating Systems")}
                      className="w-full py-1.5 px-3 bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold rounded-lg hover:bg-indigo-100 flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                      + Create "{activeUser.id.startsWith("1111") ? "Database Systems" : "Operating Systems"}" Folder
                    </button>
                  </div>
                )}
              </div>

              {/* Module Selection */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Module Number
                </label>
                <select
                  value={moduleNo}
                  onChange={(e) => setModuleNo(Number(e.target.value))}
                  className="w-full text-sm border border-slate-300 rounded-lg p-2.5 bg-white text-slate-800 focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                >
                  {[1, 2, 3, 4, 5].map((m) => (
                    <option key={m} value={m}>
                      Module {m}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Create Custom Subject Option */}
            <div className="pt-1">
              {!isCreatingSubject ? (
                <button
                  type="button"
                  onClick={() => setIsCreatingSubject(true)}
                  className="text-xs text-indigo-600 font-semibold hover:text-indigo-800 flex items-center gap-1"
                >
                  + Add a custom subject folder
                </button>
              ) : (
                <form onSubmit={handleCreateSubject} className="flex items-center gap-2 mt-2">
                  <input
                    type="text"
                    placeholder="e.g. Computer Networks"
                    value={newSubjectName}
                    onChange={(e) => setNewSubjectName(e.target.value)}
                    className="flex-1 text-sm border border-slate-300 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-indigo-500"
                    autoFocus
                  />
                  <button
                    type="submit"
                    className="bg-indigo-600 text-white text-xs font-semibold px-3 py-2 rounded-lg hover:bg-indigo-700 cursor-pointer"
                  >
                    Save Subject
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsCreatingSubject(false)}
                    className="text-xs text-slate-500 hover:text-slate-800 px-2 py-2 cursor-pointer"
                  >
                    Cancel
                  </button>
                </form>
              )}
            </div>
          </div>

          {/* Upload Drop Zone Card */}
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
              <Upload className="w-5 h-5 text-indigo-600" />
              2. Select Lecture Notes
            </h2>

            {/* Drag and Drop Zone */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors duration-150 flex flex-col items-center justify-center space-y-3 relative ${dragActive
                ? "border-indigo-500 bg-indigo-50"
                : selectedFile
                  ? "border-emerald-500 bg-emerald-50/50"
                  : "border-slate-300 hover:border-indigo-400 bg-slate-50/50"
                }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.ppt,.pptx,.png,.jpg,.jpeg"
                onChange={(e) => e.target.files?.[0] && validateAndSetFile(e.target.files[0])}
                className="hidden"
              />

              {selectedFile ? (
                <>
                  <div className="flex items-center gap-2">
                    <FileText className="w-10 h-10 text-emerald-600 animate-pulse" />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        resetUploadState();
                      }}
                      title="Remove selected file"
                      className="absolute top-3 right-3 p-1 rounded-full bg-slate-200 hover:bg-rose-100 hover:text-rose-600 text-slate-600 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-emerald-900">{selectedFile.name}</p>
                    <p className="text-xs text-emerald-700 mt-0.5">
                      {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Ready to upload into Module {moduleNo}
                    </p>
                  </div>
                  <span className="text-xs text-indigo-600 font-medium underline">Click to choose a different file</span>
                </>
              ) : (
                <>
                  <Upload className="w-10 h-10 text-slate-400" />
                  <div>
                    <p className="text-sm font-medium text-slate-800">
                      Drag and drop your lecture notes here, or <span className="text-indigo-600 underline">browse</span>
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      Supports PDF, PowerPoint (.ppt, .pptx), and images (.png, .jpg) up to {MAX_FILE_SIZE_MB} MB
                    </p>
                  </div>
                </>
              )}
            </div>

            {/* Error Banner */}
            {clientError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs rounded-lg p-3 flex items-start justify-between gap-2">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                  <span>{clientError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setClientError(null)}
                  className="text-rose-400 hover:text-rose-700"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Success Banner (Dismissible with ✕) */}
            {statusMessage && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs rounded-lg p-3 flex items-start justify-between gap-2">
                <div className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                  <span>{statusMessage}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setStatusMessage(null)}
                  className="text-emerald-500 hover:text-emerald-800"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Dynamic Upload Button */}
            <button
              type="button"
              disabled={!canUpload}
              onClick={handleUpload}
              className={`w-full py-3 px-4 rounded-lg font-semibold text-sm flex items-center justify-center gap-2 transition-all ${canUpload
                ? "bg-indigo-600 hover:bg-indigo-700 text-white shadow-md hover:shadow-lg cursor-pointer"
                : "bg-slate-200 text-slate-500 cursor-not-allowed"
                }`}
            >
              {isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Uploading and Queueing Job...
                </>
              ) : !selectedSubjectId ? (
                <>
                  <FolderPlus className="w-4 h-4 text-slate-400" />
                  ⚠️ Select or Create a Subject Folder to Enable Upload
                </>
              ) : !selectedFile ? (
                <>
                  <Upload className="w-4 h-4 text-slate-400" />
                  Select Notes Above to Upload
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  Upload & Start Ingestion
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Ingestion Progress Tracker */}
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
                <Clock className="w-5 h-5 text-indigo-600" />
                Folder Documents & Live Progress
              </h2>
              {selectedSubjectId && (
                <button
                  onClick={() => loadDocumentsForSubject(selectedSubjectId, activeUser.id, activeUser.email)}
                  title="Refresh list"
                  className="text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              )}
            </div>

            <p className="text-xs text-slate-500">
              Files uploaded into this folder update automatically without reloading the page.
            </p>

            {documents.length === 0 ? (
              <div className="border border-dashed border-slate-200 rounded-lg p-8 text-center text-xs text-slate-400">
                {selectedSubjectId
                  ? "No documents uploaded to this folder yet. Drop a file to begin!"
                  : "Choose or create a subject folder to view its documents."}
              </div>
            ) : (
              <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="border border-slate-200 rounded-lg p-3.5 space-y-2 hover:border-slate-300 transition-colors bg-white shadow-xs"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-4 h-4 text-slate-500 flex-shrink-0" />
                        <span className="text-xs font-semibold text-slate-800 truncate" title={doc.filename}>
                          {doc.filename}
                        </span>
                      </div>
                      <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 flex-shrink-0">
                        Mod {doc.module_no || 1}
                      </span>
                    </div>

                    {/* Status Pill Badge */}
                    <div className="flex items-center justify-between pt-1">
                      {doc.status === "queued" && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-200">
                          <Clock className="w-3 h-3 animate-pulse" />
                          Queued in background
                        </span>
                      )}

                      {doc.status === "extracting" && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Extracting content...
                        </span>
                      )}

                      {doc.status === "done" && (
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3" />
                            Done
                          </span>

                          {doc.topic_count !== undefined && doc.topic_count > 0 ? (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200">
                              <Sparkles className="w-3 h-3 text-indigo-500" />
                              {doc.topic_count} Topics
                              {doc.unreviewed_count ? ` (${doc.unreviewed_count} unreviewed)` : " (All reviewed)"}
                            </span>
                          ) : null}

                          <button
                            type="button"
                            onClick={() => setReviewingDoc(doc)}
                            className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-md transition-colors cursor-pointer"
                            title="Review extracted topics from this document"
                          >
                            <Sparkles className="w-3 h-3 text-indigo-600" />
                            Review Topics
                          </button>
                        </div>
                      )}

                      {doc.status === "failed" && (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
                          <AlertCircle className="w-3 h-3" />
                          Failed
                        </span>
                      )}

                      <span className="text-[10px] text-slate-400">
                        {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now"}
                      </span>
                    </div>

                    {/* What Changed Summary Badge (Task T11) */}
                    {doc.summary && (
                      <div className="text-[11px] text-indigo-900 bg-indigo-50/70 border border-indigo-100 rounded-md px-2.5 py-1.5 flex items-center gap-1.5 mt-1">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                        <span className="font-medium text-slate-700 leading-tight">{doc.summary}</span>
                      </div>
                    )}

                    {doc.error_message && (
                      <p className="text-[11px] text-rose-600 bg-rose-50 p-1.5 rounded">
                        Error: {doc.error_message}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Review Screen Modal (T06) */}
      {reviewingDoc && (
        <TopicReviewModal
          isOpen={!!reviewingDoc}
          documentId={reviewingDoc.id}
          documentTitle={reviewingDoc.filename}
          moduleNo={reviewingDoc.module_no}
          activeUserId={activeUser.id}
          activeUserEmail={activeUser.email}
          onClose={() => setReviewingDoc(null)}
          onTopicsUpdated={() => {
            if (selectedSubjectId) {
              loadDocumentsForSubject(selectedSubjectId, activeUser.id, activeUser.email);
            }
          }}
        />
      )}
    </div>
  );
};
