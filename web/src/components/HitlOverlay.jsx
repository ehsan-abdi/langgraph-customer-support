import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';

export default function HitlOverlay({ hitlData, onResume }) {
  const { node, state } = hitlData;
  const [manualText, setManualText] = useState("");

  const renderContent = () => {
    if (node === 'hitl_approve_action') {
      return (
        <>
          <div className="mb-6 p-4 bg-slate-950 rounded-lg border border-slate-800">
            <h4 className="text-sm font-semibold text-slate-400 mb-2">Proposed Action Summary:</h4>
            <p className="text-slate-200">{state.investigation_summary}</p>
          </div>
          <div className="flex gap-4 w-full">
            <button 
              onClick={() => onResume({ action_approved: true })}
              className="flex-1 py-3 px-4 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-lg shadow-emerald-900/20"
            >
              <CheckCircle className="w-5 h-5" /> Approve Action
            </button>
            <button 
              onClick={() => onResume({ action_approved: false })}
              className="flex-1 py-3 px-4 bg-rose-600 hover:bg-rose-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-lg shadow-rose-900/20"
            >
              <XCircle className="w-5 h-5" /> Reject Action
            </button>
          </div>
        </>
      );
    }

    if (node === 'hitl_final_review') {
      return (
        <>
          <div className="mb-6 p-4 bg-slate-950 rounded-lg border border-slate-800">
            <h4 className="text-sm font-semibold text-slate-400 mb-2">Drafted Response:</h4>
            <p className="text-slate-200 whitespace-pre-wrap text-sm">{state.drafted_response}</p>
          </div>
          <div className="flex gap-4 w-full">
            <button 
              onClick={() => onResume({ final_review_approved: true })}
              className="flex-1 py-3 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-900/20"
            >
              <CheckCircle className="w-5 h-5" /> Approve Final Draft
            </button>
            <button 
              onClick={() => onResume({ final_review_approved: false })}
              className="flex-1 py-3 px-4 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-all"
            >
              <XCircle className="w-5 h-5" /> Reject & Edit Manually
            </button>
          </div>
        </>
      );
    }

    if (node === 'hitl_manual_resolution') {
      return (
        <>
          <div className="mb-6">
            <label className="block text-sm font-semibold text-slate-400 mb-2">Manual Resolution / Override Text:</label>
            <textarea 
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              placeholder="Enter the manual resolution response to send to the customer..."
              className="w-full h-32 bg-slate-950 border border-slate-700 rounded-lg p-4 text-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
            />
          </div>
          <button 
            onClick={() => onResume({ drafted_response: manualText })}
            disabled={!manualText.trim()}
            className="w-full py-3 px-4 bg-purple-600 hover:bg-purple-500 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-lg font-medium flex items-center justify-center gap-2 transition-all shadow-lg shadow-purple-900/20"
          >
            <CheckCircle className="w-5 h-5" /> Submit Resolution
          </button>
        </>
      );
    }
    
    return null;
  };

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center pointer-events-none p-6">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" />
      
      <motion.div 
        initial={{ opacity: 0, y: 50, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        className="relative bg-slate-900 border border-slate-700 rounded-2xl p-8 max-w-2xl w-full shadow-2xl pointer-events-auto"
      >
        <div className="flex items-center gap-3 mb-6 border-b border-slate-800 pb-4">
          <AlertCircle className="w-8 h-8 text-amber-500" />
          <div>
            <h2 className="text-2xl font-bold text-slate-100">Human Intervention Required</h2>
            <p className="text-slate-400 text-sm mt-1">
              {node === 'hitl_approve_action' && "The Action Agent requires authorization to mutate the database."}
              {node === 'hitl_final_review' && "High-priority ticket requires final sign-off before submission."}
              {node === 'hitl_manual_resolution' && "This ticket has been escalated for manual resolution."}
            </p>
          </div>
        </div>

        {renderContent()}
      </motion.div>
    </div>
  );
}
