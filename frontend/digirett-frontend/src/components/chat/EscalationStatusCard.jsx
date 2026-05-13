import React, { useState, useEffect, useCallback } from "react";
import hitlService from "../../services/hitlService";
import BookingSystem from "./BookingSystem";
import { Loader2, Scale, CheckCircle2, Clock, Calendar, ExternalLink, ShieldCheck, AlertCircle } from "lucide-react";

export default function EscalationStatusCard({ conversationId, theme = "dark" }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const isDark = theme === "dark";

  const fetchStatus = useCallback(async () => {
    try {
      const data = await hitlService.getEscalationStatus(conversationId);
      setStatusData(data);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch escalation status:", err);
      // Don't show error immediately as we might be polling
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchStatus();
    
    // Poll for updates every 10 seconds if ticket is open or assigned
    const pollInterval = setInterval(() => {
      const currentStatus = statusData?.ticket?.status;
      if (statusData?.is_escalated && (currentStatus === "open" || currentStatus === "assigned")) {
        fetchStatus();
      }
    }, 10000);

    return () => clearInterval(pollInterval);
  }, [fetchStatus, statusData?.is_escalated, statusData?.ticket?.status]);

  if (loading && !statusData) return null;
  if (!statusData?.is_escalated) return null;

  const ticket = statusData.ticket;
  const status = ticket?.status || "open";

  // ── Render States ──────────────────────────────────────────────────

  // 1. OPEN: Waiting for lawyer to claim
  if (status === "open") {
    return (
      <div className={`my-6 p-6 rounded-3xl border animate-pulse-subtle ${
        isDark ? "bg-indigo-500/5 border-indigo-500/20" : "bg-indigo-50 border-indigo-100"
      }`}>
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/20 flex-shrink-0">
            <Scale className="text-white w-5 h-5" />
          </div>
          <div>
            <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
              Searching for a Lawyer...
            </h4>
            <p className="text-xs text-slate-500 font-medium leading-relaxed">
              Your case has been escalated. A specialized lawyer is currently reviewing your matter and will accept shortly.
            </p>
            <div className="mt-4 flex items-center gap-2">
              <Loader2 className="w-3 h-3 text-indigo-500 animate-spin" />
              <span className="text-[10px] font-black uppercase tracking-widest text-indigo-500">Awaiting Assignment</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. ASSIGNED: Lawyer claimed, user needs to book
  if (status === "assigned") {
    return (
      <div className="my-6">
        <div className={`mb-4 p-6 rounded-3xl border ${
          isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
        }`}>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20 flex-shrink-0">
              <ShieldCheck className="text-white w-5 h-5" />
            </div>
            <div>
              <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                Lawyer Assigned!
              </h4>
              <p className="text-xs text-slate-500 font-medium leading-relaxed">
                A lawyer has accepted your case. Please schedule a time for your legal consultation below.
              </p>
            </div>
          </div>
        </div>
        <BookingSystem ticketId={ticket.ticket_id} onBookingComplete={fetchStatus} />
      </div>
    );
  }

  // 3. BOOKED: Meeting is scheduled
  if (status === "booked") {
    return (
      <div className={`my-6 p-6 rounded-3xl border ${
        isDark ? "bg-blue-500/5 border-blue-500/20" : "bg-blue-50 border-blue-100"
      }`}>
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-blue-500 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/20 flex-shrink-0">
            <Clock className="text-white w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="flex justify-between items-start">
              <div>
                <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  Consultation Booked
                </h4>
                <p className="text-xs text-slate-500 font-medium">
                  {new Date(ticket.booking_confirmed_at).toLocaleString()}
                </p>
              </div>
              <span className="px-2 py-1 bg-blue-500/20 text-blue-500 rounded-lg text-[9px] font-black uppercase tracking-widest">
                Upcoming
              </span>
            </div>
            
            {ticket.booking_url && (
              <a 
                href={ticket.booking_url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="mt-4 flex items-center justify-center gap-2 w-full py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl text-xs font-bold transition-all shadow-lg shadow-blue-500/20"
              >
                <ExternalLink size={14} />
                Join Google Meet
              </a>
            )}
            <p className="mt-3 text-[10px] text-slate-500 text-center font-medium italic italic">
              A link has also been sent to your email.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 4. RESOLVED: Lawyer finished
  if (status === "resolved") {
    return (
      <div className={`my-8 p-8 rounded-3xl border-2 border-dashed ${
        isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
      }`}>
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center mb-4 shadow-xl shadow-emerald-500/20">
            <CheckCircle2 className="text-white w-6 h-6" />
          </div>
          <h4 className={`text-lg font-black tracking-tight mb-2 ${isDark ? "text-white" : "text-slate-900"}`}>
            Legal Review Complete
          </h4>
          <p className="text-xs text-slate-500 font-medium max-w-sm">
            Your legal consultation has concluded. The lawyer has provided the following final outcome.
          </p>
        </div>

        <div className={`p-6 rounded-2xl border text-sm leading-relaxed ${
          isDark ? "bg-slate-900 border-slate-800 text-slate-300" : "bg-white border-slate-200 text-slate-700"
        }`}>
          <div className="flex items-center gap-2 mb-4 text-[10px] font-black uppercase tracking-widest text-emerald-500">
            <ShieldCheck size={12} />
            Official Outcome Notes
          </div>
          {ticket.outcome_notes || ticket.hitl_responses?.[0]?.content || "No outcome notes provided."}
        </div>
        
        <p className="mt-6 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center opacity-50">
          This case is now resolved.
        </p>
      </div>
    );
  }

  return null;
}
