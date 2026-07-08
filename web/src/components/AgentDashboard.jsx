import React, { useState, useEffect, useRef } from 'react';
import GraphCanvas from './GraphCanvas';
import HitlOverlay from './HitlOverlay';
import '@xyflow/react/dist/style.css';
import { Play, Download, Loader2, Network, CheckCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { createPortal } from 'react-dom';

export default function AgentDashboard() {
  const [wsEvents, setWsEvents] = useState([]);
  const [currentHitl, setCurrentHitl] = useState(null);
  const [threadId, setThreadId] = useState(null);
  const [ticketKey, setTicketKey] = useState("AURA-99");
  const [complaint, setComplaint] = useState("I am very upset about this overdraft fee.");
  const [isRunning, setIsRunning] = useState(false);
  const [isFetching, setIsFetching] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [showGraphState, setShowGraphState] = useState(false);
  const ws = useRef(null);

  // Connect to WebSocket on mount
  useEffect(() => {
    ws.current = new WebSocket('ws://localhost:8000/api/ticket/stream');
    
    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("WS Event:", data);
      
      if (data.type === 'node_update') {
        setWsEvents(prev => [...prev, data]);
      } else if (data.type === 'interrupted') {
        setCurrentHitl({ node: data.node, state: data.state });
      } else if (data.type === 'completed') {
        setCurrentHitl(null);
        setIsRunning(false);
        setShowToast(true);
        setTimeout(() => setShowToast(false), 3500); // Fades away naturally
      }
    };

    // Auto-fetch latest ticket on mount
    fetchLatestTicket();

    return () => {
      if (ws.current) ws.current.close();
    };
  }, []);

  const fetchLatestTicket = async () => {
    setIsFetching(true);
    try {
      const res = await fetch('http://localhost:8000/api/ticket/latest');
      const data = await res.json();
      setTicketKey(data.ticket_key);
      setComplaint(data.raw_complaint);
    } catch (err) {
      console.error("Failed to fetch latest ticket", err);
    } finally {
      setIsFetching(false);
    }
  };

  const startPipeline = async () => {
    if (!ticketKey || !complaint) return;
    setIsRunning(true);
    setWsEvents([]);
    setCurrentHitl(null);

    try {
      const res = await fetch('http://localhost:8000/api/ticket/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_key: ticketKey, raw_complaint: complaint })
      });
      const data = await res.json();
      setThreadId(data.thread_id);
    } catch (err) {
      console.error(err);
      setIsRunning(false);
    }
  };

  const handleResume = async (updates) => {
    setCurrentHitl(null);
    try {
      await fetch('http://localhost:8000/api/ticket/resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, node: currentHitl.node, updates })
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="relative w-full h-full overflow-hidden bg-slate-900">
      {/* HUD Controls */}
      <div className="absolute top-4 left-4 z-50 bg-slate-800/80 backdrop-blur-md border border-slate-700 rounded-xl p-4 shadow-2xl w-[350px]">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-xl font-bold text-slate-100">Graph Engine</h1>
          <button 
            onClick={fetchLatestTicket}
            disabled={isFetching || isRunning}
            className="p-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 rounded-md text-slate-300 transition-colors"
            title="Fetch Latest Submitted Ticket"
          >
            {isFetching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          </button>
        </div>
        
        <div className="space-y-3">
          <div>
            <label className="text-xs font-semibold text-slate-400">Ticket Key</label>
            <input 
              className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-slate-200 mt-1"
              value={ticketKey}
              onChange={e => setTicketKey(e.target.value)}
              disabled={isRunning}
            />
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-400">Complaint Context</label>
            <textarea 
              className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-slate-200 mt-1 resize-none h-64"
              value={complaint}
              onChange={e => setComplaint(e.target.value)}
              disabled={isRunning}
            />
          </div>
          
          <button
            onClick={startPipeline}
            disabled={isRunning}
            className="w-full py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white rounded font-medium flex items-center justify-center gap-2 transition-colors shadow-lg"
          >
            {isRunning && wsEvents.length === 0 ? <><Loader2 className="w-4 h-4 animate-spin" /> Starting...</> : isRunning ? 'Running...' : <><Play className="w-4 h-4" /> Start Pipeline</>}
          </button>
        </div>
      </div>

      {/* Main Canvas */}
      <GraphCanvas wsEvents={wsEvents} currentHitl={currentHitl} />

      {/* HITL Overlay */}
      {currentHitl && (
        <HitlOverlay hitlData={currentHitl} onResume={handleResume} />
      )}

      {/* Network Button for Global Graph State */}
      <button 
        onClick={() => setShowGraphState(true)}
        className="absolute top-4 right-4 z-50 px-4 py-3 bg-slate-800 hover:bg-slate-700 rounded-full border border-slate-600 text-blue-400 shadow-[0_0_20px_rgba(37,99,235,0.2)] transition-colors flex items-center gap-2 font-medium"
        title="View Graph State"
      >
        <Network className="w-5 h-5" />
        View Graph State
      </button>

      {/* Global Graph State Modal */}
      {typeof document !== 'undefined' && createPortal(
        <AnimatePresence>
          {showGraphState && (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[99999] flex items-center justify-center bg-slate-900/60 backdrop-blur-md p-8"
              onPointerDown={(e) => { e.stopPropagation(); setShowGraphState(false); }}
            >
              <div 
                className="bg-slate-800 border border-slate-600 rounded-xl p-4 shadow-2xl w-[60vw] max-w-[1000px] h-[80vh] flex flex-col"
                onPointerDown={(e) => e.stopPropagation()}
              >
                <h3 className="text-xl font-bold text-white mb-3 flex items-center gap-3 border-b border-slate-700 pb-3">
                  <Network className="text-blue-400 w-6 h-6" />
                  Global Graph State Record
                </h3>
                <div className="flex-1 overflow-hidden relative mt-2">
                  <pre className="absolute inset-0 overflow-auto text-xs text-emerald-400 font-mono whitespace-pre bg-slate-950 p-4 rounded border border-slate-800 custom-scrollbar">
                    {wsEvents.length > 0 ? JSON.stringify(wsEvents, null, 2) : "Graph has not run yet."}
                  </pre>
                </div>
                <button 
                  onClick={() => setShowGraphState(false)}
                  className="mt-4 w-full py-3 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition-colors border border-slate-600"
                >
                  Close
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}

      {/* Toast Notification */}
      <AnimatePresence>
        {showToast && (
          <motion.div
            initial={{ opacity: 0, y: 50, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 50, x: '-50%' }}
            className="fixed bottom-10 left-1/2 z-[100] px-8 py-4 bg-emerald-600/90 backdrop-blur-lg text-white rounded-full shadow-[0_0_30px_rgba(16,185,129,0.4)] flex items-center gap-3 font-bold border border-emerald-500"
          >
            <CheckCircle className="w-6 h-6" />
            Pipeline Completed Successfully!
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
