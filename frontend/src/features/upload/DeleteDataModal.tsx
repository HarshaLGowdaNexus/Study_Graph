import React, { useState } from "react";
import { AlertTriangle, Trash2, X, Loader2, CheckCircle2 } from "lucide-react";

interface DeleteDataModalProps {
  userId: string;
  userEmail: string;
  userName: string;
  onClose: () => void;
  onDataDeleted: () => void;
}

export const DeleteDataModal: React.FC<DeleteDataModalProps> = ({
  userId,
  userEmail,
  userName,
  onClose,
  onDataDeleted,
}) => {
  const [confirmText, setConfirmText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [deletedResult, setDeletedResult] = useState<any | null>(null);

  const isConfirmed = confirmText.trim() === "DELETE";

  const handleDelete = async () => {
    if (!isConfirmed || isDeleting) return;

    setIsDeleting(true);
    setErrorMessage(null);

    try {
      const res = await fetch("/api/user/data", {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
        body: JSON.stringify({ confirmation: "DELETE" }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to delete user data");
      }

      setDeletedResult(data);
      // Clean up local storage consent or UI caches
      localStorage.removeItem(`studygraph_consent_${userId}`);

      setTimeout(() => {
        onDataDeleted();
        onClose();
      }, 1800);
    } catch (err: any) {
      setErrorMessage(err.message || "An error occurred while wiping data.");
      setIsDeleting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-red-200">
        {deletedResult ? (
          <div className="text-center py-6">
            <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto mb-3">
              <CheckCircle2 className="w-7 h-7" />
            </div>
            <h3 className="text-base font-bold text-slate-900 mb-1">Data Scrubbed Successfully</h3>
            <p className="text-xs text-slate-600">
              Purged {deletedResult.files_deleted} storage files and wiped all personal graph records.
            </p>
          </div>
        ) : (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-red-100 text-red-600 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Delete All My Data</h3>
                  <p className="text-xs text-slate-500">Irreversible Privacy Wipe (Feature F22)</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-red-50/70 border border-red-200 rounded-xl p-3.5 text-xs text-red-900 mb-4 space-y-2">
              <p className="font-semibold text-red-800">
                You are about to permanently delete all data for: {userName}
              </p>
              <ul className="list-disc list-inside space-y-1 text-2xs text-red-700">
                <li>Original uploaded PDFs, slide decks, and images in cloud storage</li>
                <li>Extracted topics, theory cards, and aliases</li>
                <li>All graph connections and verified evidence snippets</li>
                <li>Complete study chatbot query and answer history</li>
                <li>Exam paper questions and cluster analysis</li>
                <li>Token logs and cached graph snapshots</li>
              </ul>
              <p className="text-2xs font-medium text-red-800">
                * Note: Other students' data (e.g., Jordan Taylor / Student B) is untouched.
              </p>
            </div>

            {errorMessage && (
              <div className="mb-4 p-2.5 bg-red-100 border border-red-200 text-red-800 rounded-lg text-xs">
                {errorMessage}
              </div>
            )}

            <div className="mb-5">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Type <span className="font-mono text-red-600 bg-red-50 px-1 py-0.5 rounded border border-red-200">DELETE</span> to confirm:
              </label>
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="DELETE"
                disabled={isDeleting}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 font-mono"
              />
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                disabled={isDeleting}
                className="flex-1 py-2 px-3 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={!isConfirmed || isDeleting}
                className={`flex-1 py-2 px-3 text-xs font-semibold rounded-lg flex items-center justify-center gap-1.5 transition ${
                  isConfirmed && !isDeleting
                    ? "bg-red-600 hover:bg-red-700 text-white shadow-xs cursor-pointer"
                    : "bg-slate-200 text-slate-400 cursor-not-allowed"
                }`}
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Wiping Data...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    <span>Permanently Wipe</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

