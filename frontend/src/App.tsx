import React from "react";
import { UploadPage } from "./features/upload/UploadPage";

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-xs">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
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
          <div className="text-xs text-slate-500 hidden sm:block">
            Pipeline Phase 1: Ingestion & Storage (T03)
          </div>
        </div>
      </header>

      <main className="py-8">
        <UploadPage />
      </main>
    </div>
  );
};

export default App;

