import React from "react";
import {
  X,
  BookOpen,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertCircle,
  Network,
  Share2,
} from "lucide-react";

export interface GraphNodeData {
  id: string;
  name: string;
  keyword: string;
  explanation: string;
  real_world_use?: string;
  module_no?: number;
  reviewed?: boolean;
  cluster_id?: string;
  cluster_label?: string;
  parent_cluster_label?: string;
  subject_id?: string;
  subject_name?: string;
  x?: number;
  y?: number;
  val?: number; // node degree
}

interface NodeDetailPanelProps {
  node: GraphNodeData | null;
  onClose: () => void;
  connectedEdgeCount?: number;
  onFocusCluster?: (clusterId: string) => void;
}

export const NodeDetailPanel: React.FC<NodeDetailPanelProps> = ({
  node,
  onClose,
  connectedEdgeCount = 0,
  onFocusCluster,
}) => {
  if (!node) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-96 bg-white border-l border-slate-200 shadow-2xl z-30 flex flex-col transform transition-transform duration-300 ease-out">
      {/* Header */}
      <div className="p-5 border-b border-slate-100 flex items-start justify-between bg-slate-50">
        <div className="space-y-1.5 pr-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 text-xs font-bold rounded bg-indigo-100 text-indigo-700">
              Module {node.module_no || 1}
            </span>
            {node.reviewed ? (
              <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded bg-emerald-100 text-emerald-800">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Reviewed
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded bg-amber-100 text-amber-800">
                <AlertCircle className="w-3 h-3 text-amber-600" />
                Unreviewed
              </span>
            )}
          </div>
          <h2 className="text-lg font-bold text-slate-900 leading-snug">
            {node.keyword || node.name}
          </h2>
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <Layers className="w-3.5 h-3.5 text-slate-400" />
            <span>{node.parent_cluster_label || node.cluster_label || "General"}</span>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition"
          title="Close panel"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 text-sm">
        {/* Theory Explanation (Rule 13.3: 1-4 lines) */}
        <div className="bg-indigo-50/50 rounded-xl p-4 border border-indigo-100/80 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-900 uppercase tracking-wider">
            <BookOpen className="w-3.5 h-3.5 text-indigo-600" />
            <span>Theory Card (Max 4 Lines)</span>
          </div>
          <p className="text-slate-800 leading-relaxed whitespace-pre-line text-sm">
            {node.explanation || "No explanation provided for this topic."}
          </p>
        </div>

        {/* Real-World Application */}
        {node.real_world_use && (
          <div className="bg-emerald-50/50 rounded-xl p-4 border border-emerald-100/80 space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-900 uppercase tracking-wider">
              <Sparkles className="w-3.5 h-3.5 text-emerald-600" />
              <span>Real-World / Industry Use</span>
            </div>
            <p className="text-slate-800 leading-relaxed text-sm">
              {node.real_world_use}
            </p>
          </div>
        )}

        {/* Graph Connectivity Statistics */}
        <div className="bg-slate-50 rounded-xl p-4 border border-slate-200/80 space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-500">
            <span className="flex items-center gap-1.5">
              <Network className="w-4 h-4 text-indigo-500" />
              Connected Links
            </span>
            <span className="px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-700 font-bold">
              {connectedEdgeCount} edges
            </span>
          </div>

          <div className="text-xs text-slate-600 flex items-center justify-between">
            <span>Cluster Sub-Group:</span>
            <span className="font-medium text-slate-800">
              {node.cluster_label || "Unclustered"}
            </span>
          </div>

          {node.cluster_id && onFocusCluster && (
            <button
              onClick={() => onFocusCluster(node.cluster_id!)}
              className="w-full mt-2 py-2 px-3 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg text-xs font-semibold text-indigo-600 flex items-center justify-center gap-1.5 transition shadow-xs"
            >
              <Share2 className="w-3.5 h-3.5" />
              Focus & Zoom To Cluster
            </button>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between text-xs text-slate-500">
        <span>Topic ID: {node.id.slice(0, 12)}...</span>
        <button
          onClick={onClose}
          className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 rounded-md font-medium text-slate-700 transition"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};

