import React, { useState, useEffect, useCallback } from "react";
import hitlService from "../../services/hitlService";
import BookingSystem from "./BookingSystem";
import { Loader2, Scale, CheckCircle2, Clock, Calendar, ExternalLink, ShieldCheck, AlertCircle, ChevronLeft } from "lucide-react";

export default function EscalationStatusCard({ conversationId, theme = "dark", isSidebar = false }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showReschedule, setShowReschedule] = useState(false);
  const [reviewSubmitted, setReviewSubmitted] = useState(false);
  const isDark = theme === "dark";

  const fetchStatus = useCallback(async () => {
    try {
      const data = await hitlService.getEscalationStatus(conversationId);
      setStatusData(data);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch escalation status:", err);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchStatus();
    
    const pollInterval = setInterval(() => {
      const currentStatus = statusData?.ticket?.status;
      if (statusData?.is_escalated && (currentStatus === "open" || currentStatus === "assigned")) {
        fetchStatus();
      }
    }, 10000);

    return () => clearInterval(pollInterval);
  }, [fetchStatus, statusData?.is_escalated, statusData?.ticket?.status]);

  if (loading && !statusData) {
    return (
      <div className="flex flex-col items-center justify-center p-8">
        <Loader2 className="w-6 h-6 text-indigo-500 animate-spin mb-3" />
        <p className="text-[10px] font-black uppercase tracking-widest text-slate-500">Loading Status...</p>
      </div>
    );
  }
  if (!statusData?.is_escalated) return null;

  const ticket = statusData.ticket;
  const status = ticket?.status || "open";

  const containerClass = isSidebar 
    ? "flex flex-col gap-4" 
    : "my-6 p-6 rounded-3xl border";

  // ── Render States ──────────────────────────────────────────────────

  // 1. OPEN: Waiting for lawyer to claim
  if (status === "open") {
    return (
      <div className={`${containerClass} animate-pulse-subtle ${
        !isSidebar ? (isDark ? "bg-indigo-500/5 border-indigo-500/20" : "bg-indigo-50 border-indigo-100") : ""
      }`}>
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/20 flex-shrink-0">
            <Scale className="text-white w-5 h-5" />
          </div>
          <div>
            <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
              Searching for a Lawyer...
            </h4>
            <p className="text-[11px] text-slate-500 font-medium leading-relaxed">
              Your case has been escalated. A specialized lawyer is currently reviewing your matter and will accept shortly.
            </p>
            <div className="mt-4 flex items-center gap-2">
              <Loader2 className="w-3 h-3 text-indigo-500 animate-spin" />
              <span className="text-[9px] font-black uppercase tracking-widest text-indigo-500">Awaiting Assignment</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. ASSIGNED: Lawyer claimed, user needs to book
  if (status === "assigned") {
    return (
      <div className={containerClass}>
        <div className={`p-5 rounded-2xl border ${
          isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
        }`}>
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 bg-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20 flex-shrink-0">
              <ShieldCheck className="text-white w-4 h-4" />
            </div>
            <div>
              <h4 className={`text-xs font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                Under Legal Review
              </h4>
              <p className="text-[10px] text-slate-500 font-medium leading-relaxed">
                <span className="text-indigo-500 font-bold">{ticket.assigned_lawyer_name || "An expert"}</span> is reviewing your details.
              </p>
            </div>
          </div>
        </div>

        {/* CAL.COM BOOKING SYSTEM */}
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <BookingSystem 
            ticketId={ticket?.ticket_id} 
            theme={theme}
            onBookingComplete={() => fetchStatus()} 
            isSidebar={isSidebar}
          />
        </div>
      </div>
    );
  }

  // 3. BOOKED: Meeting is scheduled
  if (status === "booked") {
    const meetingDate = new Date(ticket.booking_confirmed_at);
    const now = new Date();
    // Consider meeting passed 1 hour after start time
    const isMeetingPassed = now > new Date(meetingDate.getTime() + 60 * 60 * 1000);

    if (showReschedule) {
      return (
        <div className={containerClass}>
          <div className="flex items-center justify-between mb-2">
            <button 
              onClick={() => setShowReschedule(false)}
              className="text-[10px] font-bold text-slate-500 hover:text-indigo-500 transition-colors flex items-center gap-1"
            >
              <ChevronLeft className="w-3 h-3" /> Back to Status
            </button>
          </div>
          <BookingSystem 
            ticketId={ticket?.ticket_id} 
            theme={theme}
            onBookingComplete={() => {
              setShowReschedule(false);
              fetchStatus();
            }} 
            isSidebar={isSidebar}
          />
        </div>
      );
    }

    if (reviewSubmitted) {
      return (
        <div className={`${containerClass} animate-in fade-in duration-500 ${
          !isSidebar ? (isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100") : ""
        }`}>
          <div className="flex flex-col items-center text-center p-4">
            <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20 mb-4">
              <CheckCircle2 className="text-white w-6 h-6" />
            </div>
            <h4 className={`text-sm font-black tracking-tight mb-2 ${isDark ? "text-white" : "text-slate-900"}`}>
              Thank You!
            </h4>
            <p className="text-[11px] text-slate-500 font-medium leading-relaxed">
              We're glad we could assist you. Your feedback helps us improve our legal assistance.
            </p>
          </div>
        </div>
      );
    }

    return (
      <div className={`${containerClass} ${
        !isSidebar ? (isDark ? "bg-blue-500/5 border-blue-500/20" : "bg-blue-50 border-blue-100") : ""
      }`}>
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-blue-500 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/20 flex-shrink-0">
            <Clock className="text-white w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="flex justify-between items-start">
              <div>
                <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  Consultation with {ticket.assigned_lawyer_name || "Lawyer"}
                </h4>
                <p className="text-[10px] text-slate-500 font-medium">
                  {meetingDate.toLocaleString()}
                </p>
              </div>
              <span className={`px-2 py-1 rounded-lg text-[8px] font-black uppercase tracking-widest ${
                isMeetingPassed 
                  ? (isDark ? "bg-slate-800 text-slate-400" : "bg-slate-100 text-slate-500")
                  : "bg-blue-500/20 text-blue-500"
              }`}>
                {isMeetingPassed ? "Ended" : "Booked"}
              </span>
            </div>
            
            {!isMeetingPassed ? (
              <>
                <p className="mt-4 text-[10px] font-black text-center text-blue-500 uppercase tracking-widest">
                  Consultation Booked
                </p>
                <p className="mt-2 text-[10px] text-slate-500 text-center font-medium leading-relaxed">
                  Please check your email. Your lawyer will contact you shortly with the meeting details.
                </p>
              </>
            ) : (
              <div className="mt-6 pt-6 border-t border-white/5 animate-in slide-in-from-top-2 duration-500">
                <p className={`text-[11px] font-bold mb-4 text-center ${isDark ? "text-white" : "text-slate-900"}`}>
                  How was your consultation?
                </p>
                <div className="flex flex-col gap-2">
                  <button 
                    onClick={() => setReviewSubmitted(true)}
                    className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white text-[10px] font-black uppercase tracking-widest rounded-xl transition-all shadow-lg shadow-indigo-500/20 flex items-center justify-center gap-2"
                  >
                    <CheckCircle2 className="w-3 h-3" /> Everything is Resolved
                  </button>
                  <button 
                    onClick={() => setShowReschedule(true)}
                    className={`w-full py-2.5 px-4 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all flex items-center justify-center gap-2 ${
                      isDark 
                        ? "bg-white/5 hover:bg-white/10 text-white border border-white/10" 
                        : "bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200"
                    }`}
                  >
                    <Calendar className="w-3 h-3" /> Need to Reschedule
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 4. RESOLVED: Lawyer finished
  if (status === "resolved") {
    return (
      <div className={`p-6 rounded-2xl border-2 border-dashed ${
        isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
      }`}>
        <div className="flex flex-col items-center text-center mb-4">
          <div className="w-10 h-10 bg-emerald-500 rounded-xl flex items-center justify-center mb-3 shadow-xl shadow-emerald-500/20">
            <CheckCircle2 className="text-white w-5 h-5" />
          </div>
          <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Review Complete
          </h4>
          <p className="text-[10px] text-slate-500 font-medium">
            The lawyer has provided a final outcome.
          </p>
        </div>

        <div className={`p-4 rounded-xl border text-[11px] leading-relaxed ${
          isDark ? "bg-slate-900 border-slate-800 text-slate-300" : "bg-white border-slate-200 text-slate-700"
        }`}>
          {ticket.outcome_notes || "No outcome notes provided."}
        </div>
      </div>
    );
  }

  // 5. CLOSED: Final archiving
  if (status === "closed") {
    return (
      <div className={`p-6 rounded-2xl border ${
        isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
      }`}>
        <div className="flex flex-col items-center text-center">
          <ShieldCheck className="text-slate-500 w-8 h-8 mb-3 opacity-50" />
          <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Case Archived
          </h4>
          <p className="text-[10px] text-slate-500 font-medium">
            This legal consultation has been closed and archived.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 text-center text-[10px] text-slate-500 italic">
      Waiting for legal status updates...
    </div>
  );
}
