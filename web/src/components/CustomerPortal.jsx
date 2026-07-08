import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, Send, Loader2 } from 'lucide-react';

export default function CustomerPortal() {
  const [fullName, setFullName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [sortCode, setSortCode] = useState('');
  const [complaint, setComplaint] = useState('');
  const [status, setStatus] = useState('idle'); // idle, submitting, success
  const [ticketKey, setTicketKey] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!complaint.trim() || !fullName.trim() || !accountNumber.trim()) return;
    
    setStatus('submitting');
    
    // Combine everything into the raw complaint string for the graph ingestion
    const combinedComplaint = `Customer Name: ${fullName}\nAccount Number: ${accountNumber}\nSort Code: ${sortCode}\n\nMessage: ${complaint}`;

    try {
      const res = await fetch('http://localhost:8000/api/ticket/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          raw_complaint: combinedComplaint
        })
      });
      const data = await res.json();
      setTicketKey(data.ticket_key);
      setStatus('success');
    } catch (error) {
      console.error(error);
      setStatus('idle');
    }
  };

  return (
    <div className="w-full h-full min-h-full overflow-y-auto bg-slate-50 flex flex-col items-center p-6 relative">
      {/* Abstract Background Shapes */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-400/20 rounded-full blur-3xl" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-indigo-400/20 rounded-full blur-3xl" />
      
      <div className="z-10 w-full max-w-lg">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-600/30 mb-4 rotate-3 hover:rotate-0 transition-transform">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-slate-800 tracking-tight">Aura Bank</h1>
          <p className="text-slate-500 text-sm mt-1">We're here to help.</p>
        </div>

        {/* Card */}
        <motion.div 
          className="bg-white/80 backdrop-blur-xl border border-white rounded-3xl p-8 shadow-2xl shadow-slate-200/50"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {status === 'success' ? (
            <motion.div 
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="flex flex-col items-center text-center py-6"
            >
              <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mb-4">
                <CheckCircle2 className="w-8 h-8 text-emerald-600" />
              </div>
              <h2 className="text-2xl font-bold text-slate-800 mb-2">Complaint Received</h2>
              <p className="text-slate-500 mb-6 text-sm">
                Your ticket has been securely submitted to our automated triage system.
              </p>
              <div className="bg-slate-50 border border-slate-200 rounded-xl px-6 py-4 w-full">
                <p className="text-xs text-slate-400 uppercase font-semibold mb-1">Ticket Reference</p>
                <p className="text-lg font-mono font-bold text-slate-700">{ticketKey}</p>
              </div>
              <button 
                onClick={() => { 
                  setStatus('idle'); 
                  setComplaint(''); 
                  setFullName('');
                  setAccountNumber('');
                  setSortCode('');
                }}
                className="mt-6 text-blue-600 font-medium text-sm hover:text-blue-700"
              >
                Submit another ticket
              </button>
            </motion.div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name</label>
                  <input 
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="e.g. Jane Doe"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-shadow"
                    disabled={status === 'submitting'}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Account Number</label>
                  <input 
                    type="text"
                    value={accountNumber}
                    onChange={(e) => setAccountNumber(e.target.value)}
                    placeholder="e.g. 12345678"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-shadow"
                    disabled={status === 'submitting'}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Sort Code</label>
                  <input 
                    type="text"
                    value={sortCode}
                    onChange={(e) => setSortCode(e.target.value)}
                    placeholder="e.g. 20-20-20"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-shadow"
                    disabled={status === 'submitting'}
                  />
                </div>
              </div>
              
              <div className="mt-2">
                <label className="block text-xs font-semibold text-slate-700 mb-1">How can we assist you?</label>
                <textarea 
                  value={complaint}
                  onChange={(e) => setComplaint(e.target.value)}
                  placeholder="Please describe the issue in detail..."
                  className="w-full h-32 bg-slate-50 border border-slate-200 rounded-lg p-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none transition-shadow"
                  disabled={status === 'submitting'}
                />
              </div>
              <button
                type="submit"
                disabled={status === 'submitting' || !complaint.trim() || !fullName.trim() || !accountNumber.trim() || !sortCode.trim()}
                className="w-full py-4 mt-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 disabled:text-slate-500 text-white rounded-xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-blue-600/20"
              >
                {status === 'submitting' ? (
                  <><Loader2 className="w-5 h-5 animate-spin" /> Processing...</>
                ) : (
                  <><Send className="w-5 h-5" /> Secure Submit</>
                )}
              </button>
            </form>
          )}
        </motion.div>
      </div>
    </div>
  );
}
