import React, { useState, useEffect } from "react";
import { DollarSign, Cpu, FileText, MessageSquare, RefreshCw, X, HelpCircle, CheckCircle } from "lucide-react";

interface CostSummaryProps {
  userId: string;
  userEmail: string;
  onClose: () => void;
}

interface UploadBreakdown {
  document_id: string;
  filename: string;
  subject_name: string;
  uploaded_at: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  operations: string[];
}

interface ChatBreakdown {
  id: string;
  timestamp: string | null;
  subject_name: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
}

interface OperationStat {
  operation: string;
  total_tokens: number;
  cost_usd: number;
  call_count: number;
}

interface CostSummaryData {
  user_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_estimated_cost_usd: number;
  per_upload_breakdown: UploadBreakdown[];
  per_chat_breakdown: ChatBreakdown[];
  by_operation: OperationStat[];
  pricing_reference: {
    gemini_flash_input_per_million: number;
    gemini_flash_output_per_million: number;
    free_tier_notice: string;
  };
}

export const CostSummaryModal: React.FC<CostSummaryProps> = ({ userId, userEmail, onClose }) => {
  const [data, setData] = useState<CostSummaryData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<"uploads" | "chats" | "operations">("uploads");

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/cost/summary", {
        headers: {
          "x-test-user-id": userId,
          "x-test-user-email": userEmail,
        },
      });
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch (err) {
      console.error("Failed to load cost summary:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSummary();
  }, [userId, userEmail]);

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-600 text-white flex items-center justify-center">
              <DollarSign className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">AI Token Usage & Cost Summary</h2>
              <p className="text-xs text-slate-500">Transparent accounting of every AI call (Rule 11)</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1">
          {loading ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
              <span className="text-xs">Calculating token usage...</span>
            </div>
          ) : !data ? (
            <div className="text-center py-8 text-slate-500 text-sm">
              Unable to load usage logs at this time.
            </div>
          ) : (
            <div className="space-y-6">
              {/* Summary Metrics Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl">
                  <div className="text-xs text-slate-500 font-medium mb-1">Total Tokens</div>
                  <div className="text-xl font-black text-slate-900">{data.total_tokens.toLocaleString()}</div>
                  <div className="text-2xs text-slate-400 mt-1">
                    {data.total_prompt_tokens.toLocaleString()} prompt / {data.total_completion_tokens.toLocaleString()} output
                  </div>
                </div>

                <div className="bg-emerald-50/70 border border-emerald-200 p-4 rounded-xl">
                  <div className="text-xs text-emerald-700 font-medium mb-1">Estimated Cost</div>
                  <div className="text-xl font-black text-emerald-800">
                    ${data.total_estimated_cost_usd.toFixed(4)}
                  </div>
                  <div className="text-2xs text-emerald-600 mt-1">Based on commercial rates</div>
                </div>

                <div className="bg-indigo-50/70 border border-indigo-200 p-4 rounded-xl">
                  <div className="text-xs text-indigo-700 font-medium mb-1">Student Free Tier</div>
                  <div className="text-base font-bold text-indigo-900 flex items-center gap-1">
                    <CheckCircle className="w-4 h-4 text-emerald-600" />
                    <span>$0.00 (Free)</span>
                  </div>
                  <div className="text-2xs text-indigo-600 mt-1">Under 1,500 daily requests</div>
                </div>
              </div>

              {/* Free Tier Notice Banner */}
              <div className="bg-slate-100 border border-slate-200 rounded-lg p-3 text-xs text-slate-600 flex items-start gap-2">
                <HelpCircle className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                <div>
                  <strong>How cost is calculated:</strong> Gemini Flash costs $0.075 per 1M input tokens and $0.30 per 1M output tokens.
                  Because Google AI Studio provides a generous free tier of 1,500 requests per day, your actual spend is $0.
                </div>
              </div>

              {/* Sub-tab Navigation */}
              <div className="flex border-b border-slate-200 gap-4 text-xs font-semibold">
                <button
                  onClick={() => setActiveTab("uploads")}
                  className={`pb-2 border-b-2 transition ${
                    activeTab === "uploads"
                      ? "border-indigo-600 text-indigo-600"
                      : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Per-Upload Breakdown ({data.per_upload_breakdown.length})
                </button>
                <button
                  onClick={() => setActiveTab("chats")}
                  className={`pb-2 border-b-2 transition ${
                    activeTab === "chats"
                      ? "border-indigo-600 text-indigo-600"
                      : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  Per-Chat Breakdown ({data.per_chat_breakdown.length})
                </button>
                <button
                  onClick={() => setActiveTab("operations")}
                  className={`pb-2 border-b-2 transition ${
                    activeTab === "operations"
                      ? "border-indigo-600 text-indigo-600"
                      : "border-transparent text-slate-500 hover:text-slate-800"
                  }`}
                >
                  By Operation ({data.by_operation.length})
                </button>
              </div>

              {/* Tab 1: Uploads */}
              {activeTab === "uploads" && (
                <div>
                  {data.per_upload_breakdown.length === 0 ? (
                    <div className="text-center py-6 text-slate-400 text-xs">No document uploads recorded yet.</div>
                  ) : (
                    <div className="border border-slate-200 rounded-lg overflow-hidden">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                          <tr>
                            <th className="p-2.5">File & Subject</th>
                            <th className="p-2.5">Tokens</th>
                            <th className="p-2.5 text-right">Est. Cost</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {data.per_upload_breakdown.map((item) => (
                            <tr key={item.document_id} className="hover:bg-slate-50/50">
                              <td className="p-2.5">
                                <div className="font-medium text-slate-900 flex items-center gap-1.5">
                                  <FileText className="w-3.5 h-3.5 text-indigo-500" />
                                  <span>{item.filename}</span>
                                </div>
                                <div className="text-2xs text-slate-400 mt-0.5">{item.subject_name}</div>
                              </td>
                              <td className="p-2.5 text-slate-700">
                                <div>{item.total_tokens.toLocaleString()} tokens</div>
                                <div className="text-2xs text-slate-400">
                                  {item.prompt_tokens.toLocaleString()} in / {item.completion_tokens.toLocaleString()} out
                                </div>
                              </td>
                              <td className="p-2.5 text-right font-medium text-slate-900">
                                ${item.estimated_cost_usd.toFixed(4)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Chats */}
              {activeTab === "chats" && (
                <div>
                  {data.per_chat_breakdown.length === 0 ? (
                    <div className="text-center py-6 text-slate-400 text-xs">No chat queries recorded yet.</div>
                  ) : (
                    <div className="border border-slate-200 rounded-lg overflow-hidden">
                      <table className="w-full text-xs text-left">
                        <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                          <tr>
                            <th className="p-2.5">Chat Query</th>
                            <th className="p-2.5">Tokens</th>
                            <th className="p-2.5 text-right">Est. Cost</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {data.per_chat_breakdown.map((c) => (
                            <tr key={c.id} className="hover:bg-slate-50/50">
                              <td className="p-2.5">
                                <div className="font-medium text-slate-900 flex items-center gap-1.5">
                                  <MessageSquare className="w-3.5 h-3.5 text-emerald-500" />
                                  <span>{c.subject_name}</span>
                                </div>
                                <div className="text-2xs text-slate-400 mt-0.5">
                                  {c.timestamp ? new Date(c.timestamp).toLocaleTimeString() : "Recent"}
                                </div>
                              </td>
                              <td className="p-2.5 text-slate-700">{c.total_tokens.toLocaleString()}</td>
                              <td className="p-2.5 text-right font-medium text-slate-900">
                                ${c.estimated_cost_usd.toFixed(4)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* Tab 3: Operations */}
              {activeTab === "operations" && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <table className="w-full text-xs text-left">
                    <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="p-2.5">Operation Type</th>
                        <th className="p-2.5">Calls</th>
                        <th className="p-2.5">Tokens</th>
                        <th className="p-2.5 text-right">Est. Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.by_operation.map((op) => (
                        <tr key={op.operation} className="hover:bg-slate-50/50">
                          <td className="p-2.5 font-medium text-slate-900 capitalize">
                            {op.operation.replace(/_/g, " ")}
                          </td>
                          <td className="p-2.5 text-slate-600">{op.call_count}</td>
                          <td className="p-2.5 text-slate-700">{op.total_tokens.toLocaleString()}</td>
                          <td className="p-2.5 text-right font-medium text-slate-900">
                            ${op.cost_usd.toFixed(4)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <button
            onClick={fetchSummary}
            className="inline-flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh Counts</span>
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-semibold transition cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

