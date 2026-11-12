import React, { useState, useEffect } from "react";
import { Shield, CheckCircle2, ChevronRight, Info } from "lucide-react";

interface ConsentBannerProps {
  userId: string;
  onConsentChange?: (consented: boolean) => void;
}

export const ConsentBanner: React.FC<ConsentBannerProps> = ({ userId, onConsentChange }) => {
  const [hasConsented, setHasConsented] = useState<boolean>(true);
  const [expanded, setExpanded] = useState<boolean>(false);

  useEffect(() => {
    // Check if this student has acknowledged the first-upload consent notice
    const consentKey = `studygraph_consent_${userId}`;
    const stored = localStorage.getItem(consentKey);
    const isConsented = stored === "true";
    setHasConsented(isConsented);
    if (onConsentChange) {
      onConsentChange(isConsented);
    }
  }, [userId, onConsentChange]);

  const handleAcknowledge = () => {
    const consentKey = `studygraph_consent_${userId}`;
    localStorage.setItem(consentKey, "true");
    setHasConsented(true);
    if (onConsentChange) {
      onConsentChange(true);
    }
  };

  if (hasConsented) {
    return (
      <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs text-emerald-800 mb-6 shadow-2xs">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>
            <strong className="font-semibold">Privacy Protected:</strong> Your notes are encrypted and isolated to your account.
          </span>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-emerald-700 hover:text-emerald-900 underline font-medium cursor-pointer"
        >
          {expanded ? "Hide Terms" : "Review Terms"}
        </button>
        {expanded && (
          <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200">
              <div className="flex items-center gap-2 mb-3">
                <Shield className="w-5 h-5 text-indigo-600" />
                <h3 className="font-bold text-slate-900 text-base">StudyGraph Data Ownership & Consent</h3>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed mb-4">
                Your notes are processed strictly to extract topics, map semantic relationships, and provide grounded study chat.
                Your data is never shared with third parties, never made public without your explicit action, and never used to train external foundation models.
                You have the permanent right to delete all your files and database records with one click.
              </p>
              <button
                onClick={() => setExpanded(false)}
                className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="bg-indigo-50/90 border-2 border-indigo-200 rounded-xl p-4 sm:p-5 mb-6 shadow-xs transition-all">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-xs">
          <Shield className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <div className="flex items-center justify-between gap-2 mb-1">
            <h3 className="text-sm font-bold text-indigo-950 flex items-center gap-1.5">
              <span>First Upload Notice: Privacy & Processing Consent</span>
              <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-2xs font-semibold uppercase tracking-wider">
                Required once
              </span>
            </h3>
          </div>
          <p className="text-xs text-indigo-900/80 leading-relaxed mb-3">
            Before uploading notes, please confirm you understand how your study materials are processed.
            StudyGraph uses local direct parsers and secure AI models (Google Gemini Flash) solely to extract concepts,
            build theory cards, and connect cross-subject links.
            <strong> Your materials remain 100% private to you</strong>, are never published publicly, and you can permanently erase everything at any time.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleAcknowledge}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-xs transition cursor-pointer"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>I Understand & Agree to Processing</span>
            </button>
            <span className="text-2xs text-indigo-700 flex items-center gap-1">
              <Info className="w-3.5 h-3.5" />
              <span>Rule 11: Multi-tenant student privacy isolation enforced</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

