import React, { useState, useEffect, useCallback } from "react";
import hitlService from "../../services/hitlService";
import BookingSystem from "./BookingSystem";
import { Loader2, Scale, CheckCircle2, Clock, Calendar, ExternalLink, ShieldCheck, AlertCircle, AlertTriangle, ChevronLeft, X, Quote } from "lucide-react";
import ReactMarkdown from "react-markdown";

export default function EscalationStatusCard({ conversationId, theme = "dark", isSidebar = false }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cancellationNotice, setCancellationNotice] = useState(false);
  const isDark = theme === "dark";

  const prevStatusRef = React.useRef();

  const fetchStatus = useCallback(async () => {
    try {
      const data = await hitlService.getEscalationStatus(conversationId);

      // Detect cancellation: booked -> assigned
      const oldStatus = prevStatusRef.current;
      const newStatus = data?.ticket?.status;
      if (oldStatus === "booked" && newStatus === "assigned") {
        setCancellationNotice(true);
      }
      prevStatusRef.current = newStatus;

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
      // Poll if active (searching, assigned, or waiting for meeting)
      if (statusData?.is_escalated && (currentStatus === "open" || currentStatus === "assigned" || currentStatus === "booked")) {
        fetchStatus();
      }
    }, 30000); // Poll every 30 seconds as per user pro-tip

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
  if (!statusData?.is_escalated &&
    statusData?.ticket?.status !== "no_show" &&
    statusData?.ticket?.status !== "closed") return null;

  const ticket = statusData.ticket;
  let status = ticket?.status || "open";

  // Handle DB-compatible no_show mapping
  if (status === "closed" && ticket?.outcome_notes?.includes("[NO-SHOW]")) {
    status = "no_show";
  }

  const containerClass = isSidebar
    ? "flex flex-col gap-4"
    : "my-6 p-6 rounded-3xl border";

  // ── Render States ──────────────────────────────────────────────────

  // 1. OPEN: Waiting for lawyer to claim
  if (status === "open") {
    return (
      <div className={`${containerClass} animate-pulse-subtle ${!isSidebar ? (isDark ? "bg-indigo-500/5 border-indigo-500/20" : "bg-indigo-50 border-indigo-100") : ""
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
              Your matter has been escalated. A specialized lawyer is currently reviewing your matter and will accept shortly.
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
        {cancellationNotice && (
          <div className="p-3 mb-2 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-2 animate-in slide-in-from-top-2 duration-500">
            <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-[10px] font-bold text-amber-600">Meeting Cancelled</p>
              <p className="text-[9px] text-amber-600/80 font-medium leading-tight">
                Your previous meeting was cancelled. Please book a new slot below.
              </p>
            </div>
            <button onClick={() => setCancellationNotice(false)} className="text-amber-500 hover:text-amber-600">
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {(ticket.outcome_notes?.includes("[USER-NO-SHOW]") || ticket.outcome_notes?.includes("[BOTH-NO-SHOW]")) && (
          <div className="p-4 mb-4 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-start gap-3 animate-in zoom-in-95 duration-500">
            <div className="w-8 h-8 rounded-xl bg-red-500/20 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-4 h-4 text-red-500" />
            </div>
            <div className="flex-1">
              <p className="text-[11px] font-black text-red-600 uppercase tracking-widest">Appointment Missed</p>
              <p className="text-[10px] text-red-700/80 font-medium leading-relaxed mt-1">
                {ticket.outcome_notes.includes("[USER-NO-SHOW]")
                  ? "It seems you were unable to attend the scheduled meeting. Please pick a new time slot below to reschedule."
                  : "Both parties were unable to attend the meeting. We apologize for the inconvenience. Please reschedule below."}
              </p>
            </div>
          </div>
        )}

        <div className={`p-5 rounded-2xl border ${isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
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

    return (
      <div className={`${containerClass} ${!isSidebar ? (isDark ? "bg-blue-500/5 border-blue-500/20" : "bg-blue-50 border-blue-100") : ""
        }`}>
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 bg-blue-500 rounded-2xl flex items-center justify-center shadow-lg shadow-blue-500/20 flex-shrink-0">
            <Clock className="text-white w-5 h-5" />
          </div>
          <div className="flex-1">
            <div className="flex justify-between items-start">
              <div>
                <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  Meeting with {ticket.assigned_lawyer_name || "Lawyer"}
                </h4>
                <p className="text-[10px] text-slate-500 font-medium">
                  {meetingDate.toLocaleString()}
                </p>
              </div>
              <span className="px-2 py-1 bg-blue-500/20 text-blue-500 rounded-lg text-[8px] font-black uppercase tracking-widest">
                Booked
              </span>
            </div>

            <div className="mt-4 flex flex-col items-center">
              <p className="text-[10px] font-black text-blue-500 uppercase tracking-widest text-center">
                Consultation Booked
              </p>
              <p className="mt-2 text-[10px] text-slate-500 text-center font-medium leading-relaxed">
                Please check your email. Your lawyer will contact you shortly with the meeting details.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 4. RESOLVED: Lawyer finished
  if (status === "resolved") {
    return (
      <div className={`p-6 rounded-2xl border-2 border-dashed animate-in fade-in zoom-in duration-500 ${isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
        }`}>
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center mb-4 shadow-xl shadow-emerald-500/20">
            <ShieldCheck className="text-white w-6 h-6" />
          </div>
          <h4 className={`text-base font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Resolution Ready
          </h4>
          <p className="text-[11px] text-slate-500 font-medium">
            Your legal consultation has been completed.
          </p>
        </div>

        {/* The Actual Lawyer Response */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Scale size={12} className="text-indigo-500" />
            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Matter Feedback</span>
          </div>

          <div className={`relative p-6 rounded-3xl border shadow-sm ${
            isDark 
              ? "bg-emerald-500/10 border-emerald-500/20 text-slate-200" 
              : "bg-emerald-500/5 border-emerald-500/10 text-slate-700"
          }`}>
            <div className="prose prose-sm dark:prose-invert max-w-none relative z-10 text-xs leading-relaxed font-medium">
              <ReactMarkdown 
                components={{
                  p: ({node, ...props}) => <p className="mb-3 last:mb-0" {...props} />,
                  strong: ({node, ...props}) => <strong className="font-black text-indigo-500" {...props} />,
                  ul: ({node, ...props}) => <ul className="list-disc pl-4 mb-3" {...props} />,
                }}
              >
                {ticket.lawyer_response || ticket.outcome_notes || "No specific feedback notes were recorded for this resolution."}
              </ReactMarkdown>
            </div>
          </div>

          <div className="pt-2 flex flex-col items-center gap-2">
            <p className="text-[10px] text-slate-400 italic">
              If you have further questions, you can start a new escalation.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 5. NO SHOW: User didn't attend
  if (status === "no_show") {
    return (
      <div className={`p-6 rounded-2xl border ${isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
        }`}>
        <div className="flex flex-col items-center text-center">
          <div className="w-10 h-10 bg-amber-500 rounded-xl flex items-center justify-center mb-3 shadow-lg shadow-amber-500/20">
            <AlertCircle className="text-white w-5 h-5" />
          </div>
          <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Consultation Missed
          </h4>
          <p className="text-[10px] text-slate-500 font-medium leading-relaxed">
            The lawyer reported that you were unable to attend the scheduled meeting. This matter has been archived.
          </p>
        </div>
      </div>
    );
  }

  // 6. CLOSED: Final archiving
  if (status === "closed") {
    return (
      <div className={`p-6 rounded-2xl border ${isDark ? "bg-white/5 border-white/10" : "bg-slate-50 border-slate-200"
        }`}>
        <div className="flex flex-col items-center text-center">
          <ShieldCheck className="text-slate-500 w-8 h-8 mb-3 opacity-50" />
          <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            Matter Archived
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
