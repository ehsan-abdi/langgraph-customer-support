import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Handle, Position } from '@xyflow/react';
import { motion, AnimatePresence } from 'framer-motion';
import { BrainCircuit, CheckCircle, Loader2, ChevronRight } from 'lucide-react';

export default function AgentNode({ id, data, yPos }) {
  const [isHovered, setIsHovered] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  // Bring node to front on hover
  useEffect(() => {
    const el = document.querySelector(`[data-id="${id}"]`);
    if (el) el.style.zIndex = isHovered ? 9999 : 1;
  }, [isHovered, id]);

  const { status, label, outputs } = data;
  const isBottom = yPos > 500;

  const getStatusStyles = () => {
    switch (status) {
      case 'idle':
        return 'border-slate-700 bg-slate-800/50 text-slate-400';
      case 'thinking':
        return 'border-blue-500 bg-blue-900/30 text-blue-300 shadow-[0_0_20px_rgba(59,130,246,0.5)]';
      case 'stable':
        return 'border-emerald-500 bg-emerald-900/30 text-emerald-300 shadow-[0_0_20px_rgba(16,185,129,0.3)]';
      default:
        return 'border-slate-700 bg-slate-800/50 text-slate-400';
    }
  };

  return (
    <div 
      className="relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      
      <motion.div 
        className={`px-6 py-4 rounded-xl border-2 backdrop-blur-md transition-colors duration-500 min-w-[200px] flex items-center justify-between ${getStatusStyles()}`}
        animate={status === 'thinking' ? { scale: [1, 1.05, 1] } : { scale: 1 }}
        transition={{ repeat: status === 'thinking' ? Infinity : 0, duration: 2 }}
      >
        <div className="flex items-center gap-3">
          {status === 'idle' && <BrainCircuit className="w-5 h-5 opacity-50" />}
          {status === 'thinking' && <Loader2 className="w-5 h-5 animate-spin" />}
          {status === 'stable' && <CheckCircle className="w-5 h-5" />}
          <span className="font-semibold tracking-wide">{label}</span>
        </div>
      </motion.div>

      {/* Hover Popover */}
      <AnimatePresence>
        {isHovered && status === 'stable' && outputs && !modalOpen && (
          <motion.div 
            initial={{ opacity: 0, y: isBottom ? 10 : -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: isBottom ? 10 : -10, scale: 0.95 }}
            className={`absolute ${isBottom ? 'bottom-full mb-4' : 'top-full mt-4'} left-1/2 -translate-x-1/2 w-[350px] bg-slate-800/95 backdrop-blur-xl border border-slate-600 rounded-xl p-5 shadow-2xl z-50 pointer-events-auto`}
          >
            <h4 className="text-sm font-bold text-slate-100 mb-3 border-b border-slate-700 pb-2 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              Node Summary
            </h4>
            <div className="text-xs text-slate-300 space-y-3 max-h-[200px] overflow-auto custom-scrollbar pr-2">
              {Object.entries(outputs).map(([key, value]) => (
                <div key={key} className="bg-slate-900/50 p-2 rounded border border-slate-700/50">
                  <strong className="text-blue-300 capitalize tracking-wide text-[10px] uppercase">{key.replace(/_/g, ' ')}</strong>
                  <div className="mt-1 text-slate-300 font-mono text-[11px] leading-relaxed break-words">
                    {typeof value === 'string' ? value : 
                     Array.isArray(value) ? `${value.length} items collected` : 
                     JSON.stringify(value)}
                  </div>
                </div>
              ))}
            </div>
            
            <button 
              onClick={() => setModalOpen(true)}
              className="mt-4 w-full flex items-center justify-center gap-1 py-2 bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 font-medium text-xs rounded-lg transition-colors border border-blue-500/30"
            >
              Read Full Raw JSON <ChevronRight className="w-4 h-4" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expanded Modal overlay for this specific node */}
      {createPortal(
        <AnimatePresence>
            {modalOpen && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[99999] flex items-center justify-center bg-slate-900/60 backdrop-blur-md p-8"
                onPointerDown={(e) => { e.stopPropagation(); setModalOpen(false); }}
              >
                <div 
                  className="bg-slate-800 border border-slate-600 rounded-xl p-4 shadow-2xl w-[50vw] max-w-[800px] h-[85vh] flex flex-col"
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <h3 className="text-lg font-bold text-white mb-3 flex items-center gap-2 border-b border-slate-700 pb-2">
                    {status === 'stable' ? <CheckCircle className="text-emerald-400 w-5 h-5" /> : <BrainCircuit className="text-blue-400 w-5 h-5" />}
                    {label} Details
                  </h3>
                  <div className="flex-1 overflow-hidden relative mt-2">
                    <pre className="absolute inset-0 overflow-auto text-xs text-slate-300 font-mono whitespace-pre-wrap break-words bg-slate-950 p-4 rounded border border-slate-800 custom-scrollbar">
                      {outputs ? JSON.stringify(outputs, null, 2) : "No detailed output available yet."}
                    </pre>
                  </div>
                  <button 
                    onClick={() => setModalOpen(false)}
                    className="mt-3 w-full py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors border border-slate-600 text-sm"
                  >
                    Close
                  </button>
                </div>
              </motion.div>
            )}
        </AnimatePresence>,
        document.body
      )}

      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
