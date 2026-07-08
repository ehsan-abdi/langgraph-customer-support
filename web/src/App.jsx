import React, { useState } from 'react';
import CustomerPortal from './components/CustomerPortal';
import AgentDashboard from './components/AgentDashboard';
import { LayoutDashboard, Users } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('customer'); // 'customer' or 'agent'

  return (
    <div className="w-screen h-screen flex flex-col bg-slate-900">
      {/* Top Navigation Bar */}
      <nav className="h-14 bg-slate-950 border-b border-slate-800 flex items-center justify-between px-6 shrink-0 z-50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="text-slate-100 font-bold tracking-tight">Aura Bank</span>
        </div>
        
        <div className="flex bg-slate-900 border border-slate-800 rounded-lg p-1">
          <button
            onClick={() => setActiveTab('customer')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-all ${
              activeTab === 'customer' 
                ? 'bg-blue-600 text-white shadow-sm' 
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <Users className="w-4 h-4" /> Customer Portal
          </button>
          <button
            onClick={() => setActiveTab('agent')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium flex items-center gap-2 transition-all ${
              activeTab === 'agent' 
                ? 'bg-blue-600 text-white shadow-sm' 
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            <LayoutDashboard className="w-4 h-4" /> Agent Dashboard
          </button>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="flex-1 relative">
        {activeTab === 'customer' ? <CustomerPortal /> : <AgentDashboard />}
      </main>
    </div>
  );
}
