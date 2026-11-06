import React, { useState } from "react";
import { UploadPage } from "./features/upload/UploadPage";
import { LinkManager } from "./features/links/LinkManager";
import { Upload, Network, ShieldCheck } from "lucide-react";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"upload" | "links">("links");

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-xs">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-lg shadow-sm">
              SG
            </div>
            <div>
              <span className="font-bold text-slate-900 tracking-tight text-lg">StudyGraph</span>
              <span className="text-xs text-indigo-600 font-medium ml-2 px-1.5 py-0.5 bg-indigo-50 border border-indigo-100 rounded">
                Semester Knowledge Engine
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg border border-slate-200">
            <button
              onClick={() => setActiveTab("links")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition ${
                activeTab === "links"
                  ? "bg-white text-indigo-600 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Network className="w-3.5 h-3.5" />
              Links & Locks (T10)
            </button>
            <button
              onClick={() => setActiveTab("upload")}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition ${
                activeTab === "upload"
                  ? "bg-white text-indigo-600 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              Upload & Ingest
            </button>
          </div>

          <div className="text-xs text-slate-500 hidden sm:flex items-center gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>User Edits Locked & Sacred</span>
          </div>
        </div>
      </header>

      <main className="py-8">
        {activeTab === "links" ? <LinkManager /> : <UploadPage />}
      </main>
    </div>
  );
};

export default App;
