import React, { useState, useEffect, useCallback } from "react";
import hitlService from "../../services/hitlService";
import BookingSystem from "./BookingSystem";
import { Loader2, Scale, CheckCircle2, Clock, Calendar, ExternalLink, ShieldCheck, AlertCircle, AlertTriangle, ChevronLeft, X, Quote, Star, Paperclip, FileText, Download } from "lucide-react";
import ReactMarkdown from "react-markdown";
import useDocumentUpload from "../../hooks/useDocumentUpload";
import { API_BASE_URL } from "../../utils/constants";

const DOMAIN_ENGLISH_NAMES = {
  "arbeidsrett": "Company Law", // wait, "arbeidsrett" is Employment Law! Let's map it correctly.
  "selskapsrett": "Company Law",
  "avtalerett": "Contract Law",
  "manda_fusjon_fisjon": "M&A, Mergers & Acquisitions",
  "arsregnskap_og_selskapsrapportering": "Financial Statements & Reporting",
  "inkasso_og_tvangsfullbyrdelse": "Debt Collection & Enforcement",
  "konkursrett_og_insolvens": "Bankruptcy & Insolvency",
  "obligasjonsrett": "Law of Obligations",
  "panterett_og_sikkerhetsrett": "Liens & Security Rights",
  "pengekravsrett_fordringer": "Monetary Claims & Debt",
  "personvern_gdpr_business_compliance": "Privacy & GDPR Compliance",
  "tvistelosning_smb": "Dispute Resolution for SMBs",
  "arbeidsrett_en": "Employment Law" // Fallback / alias
};

// Map keys to correct English names
const getDomainEnglishName = (domain) => {
  if (!domain) return null;
  const normalized = domain.toLowerCase().trim();
  if (normalized === "arbeidsrett") return "Employment Law";
  if (normalized === "selskapsrett") return "Company Law";
  if (normalized === "avtalerett") return "Contract Law";
  if (normalized === "manda_fusjon_fisjon") return "M&A, Mergers & Acquisitions";
  if (normalized === "arsregnskap_og_selskapsrapportering") return "Financial Statements & Reporting";
  if (normalized === "inkasso_og_tvangsfullbyrdelse") return "Debt Collection & Enforcement";
  if (normalized === "konkursrett_og_insolvens") return "Bankruptcy & Insolvency";
  if (normalized === "obligasjonsrett") return "Law of Obligations";
  if (normalized === "panterett_og_sikkerhetsrett") return "Liens & Security Rights";
  if (normalized === "pengekravsrett_fordringer") return "Monetary Claims & Debt";
  if (normalized === "personvern_gdpr_business_compliance") return "Privacy & GDPR Compliance";
  if (normalized === "tvistelosning_smb") return "Dispute Resolution for SMBs";

  // Format custom domains nicely (e.g. criminal_law -> Criminal Law)
  return normalized
    .split(/[_-]/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
};

export default function EscalationStatusCard({ conversationId, theme = "dark", isSidebar = false }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cancellationNotice, setCancellationNotice] = useState(false);
  const isDark = theme === "dark";

  const [showReescalateOptions, setShowReescalateOptions] = useState(false);
  const [isClosing, setIsClosing] = useState(false);
  const [reescalateOption, setReescalateOption] = useState(null);
  const [caseClosed, setCaseClosed] = useState(false);

  const handleCloseCase = async () => {
    const t = statusData?.ticket;
    if (!t?.ticket_id) return;
    setIsClosing(true);
    try {
      await hitlService.closeTicket(t.ticket_id);
      setCaseClosed(true);
      fetchStatus();
    } catch (err) {
      alert(err.message || "Failed to close the case");
    } finally {
      setIsClosing(false);
    }
  };

  const handleReescalateCase = async (option) => {
    const t = statusData?.ticket;
    if (!t?.ticket_id) return;
    setReescalateOption(option);
    try {
      await hitlService.reEscalateTicket(t.ticket_id, option);
      setShowReescalateOptions(false);
      window.dispatchEvent(new CustomEvent("escalation_status_changed", { detail: true }));
      fetchStatus();
    } catch (err) {
      alert(err.message || "Failed to re-escalate the case");
    } finally {
      setReescalateOption(null);
    }
  };

  const [rating, setRating] = useState(0);
  const [ratingHover, setRatingHover] = useState(0);
  const [ratingComment, setRatingComment] = useState("");
  const [ratingSubmitted, setRatingSubmitted] = useState(false);
  const [submittingRating, setSubmittingRating] = useState(false);
  const [ratingError, setRatingError] = useState(null);

  const prevStatusRef = React.useRef();

  useEffect(() => {
    const t = statusData?.ticket;
    if (t?.ticket_id) {
      if (t.rating !== null && t.rating !== undefined) {
        setRating(t.rating);
        setRatingComment(t.comment || t.rating_comment || "");
        setRatingSubmitted(true);
      } else {
        const cached = localStorage.getItem(`rated_ticket_${t.ticket_id}`);
        if (cached) {
          try {
            const parsed = JSON.parse(cached);
            setRating(parsed.rating);
            setRatingComment(parsed.comment || "");
            setRatingSubmitted(true);
          } catch (e) {
            console.error("Failed to parse cached rating", e);
          }
        }
      }
    }
  }, [statusData]);

  const handleRatingSubmit = async (e) => {
    e.preventDefault();
    const t = statusData?.ticket;
    if (rating === 0 || !t?.ticket_id) return;
    setSubmittingRating(true);
    setRatingError(null);
    try {
      await hitlService.submitRating(t.ticket_id, rating, ratingComment);
      setRatingSubmitted(true);
      fetchStatus();
    } catch (err) {
      setRatingError(err.message || "Failed to submit rating");
    } finally {
      setSubmittingRating(false);
    }
  };

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
    } catch (err) {
      console.error("Failed to fetch escalation status:", err);
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

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

  const renderPriorityBadge = () => {
    const priority = ticket?.priority || "normal";
    if (priority === "normal") return null;
    const classes = priority === "urgent"
      ? (isDark ? "bg-rose-500/10 text-rose-400 border-rose-500/20" : "bg-rose-50 text-rose-600 border-rose-100")
      : (isDark ? "bg-amber-500/10 text-amber-400 border-amber-500/20" : "bg-amber-50 text-amber-600 border-amber-100");
    return (
      <span className={`px-2 py-0.5 rounded-md text-[8px] font-black uppercase tracking-wider border flex-shrink-0 ${classes}`}>
        {priority}
      </span>
    );
  };

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
    const domainName = getDomainEnglishName(ticket?.detected_domain);
    return (
      <div className={containerClass}>
        <div className={`p-5 rounded-2xl border animate-pulse-subtle ${isDark ? "bg-indigo-500/5 border-indigo-500/20" : "bg-indigo-50 border-indigo-100"
          }`}>
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 bg-indigo-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-500/20 flex-shrink-0">
              <Scale className="text-white w-5 h-5" />
            </div>
            <div className="flex-1">
              <div className="flex justify-between items-start gap-2">
                <h4 className={`text-xs font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  {domainName ? `Finding an expert in ${domainName}...` : "Searching for a Lawyer..."}
                </h4>
                {renderPriorityBadge()}
              </div>
              <p className="text-[10px] text-slate-500 font-medium leading-relaxed">
                {domainName ? (
                  <>
                    Your matter has been escalated. A lawyer specializing in <strong>{domainName}</strong> is currently reviewing your details and will accept shortly.
                  </>
                ) : (
                  "Your matter has been escalated. A specialized lawyer is currently reviewing your matter and will accept shortly."
                )}
              </p>
              <div className="mt-4 flex items-center gap-2">
                <Loader2 className="w-3 h-3 text-indigo-500 animate-spin" />
                <span className="text-[9px] font-black uppercase tracking-widest text-indigo-500">Awaiting Assignment</span>
              </div>
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
            <div className="flex-1">
              <div className="flex justify-between items-start gap-2">
                <h4 className={`text-xs font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  Under Legal Review
                </h4>
                {renderPriorityBadge()}
              </div>
              <p className="text-[10px] text-slate-500 font-medium leading-relaxed">
                <span className="text-indigo-500 font-bold">{ticket.assigned_lawyer_name || "An expert"}</span> is reviewing your details. Your lawyer has received a brief about your matter.
              </p>
            </div>
          </div>
        </div>

        {/* Pre-Consultation Messages */}
        <PreConsultationChat ticketId={ticket.ticket_id} isDark={isDark} userRole="user" conversationId={conversationId} />

        {/* Translucent 'or' Divider */}
        <div className="relative my-2 flex items-center justify-center">
          <div className="absolute inset-0 flex items-center" aria-hidden="true">
            <div className={`w-full border-t ${isDark ? "border-white/5" : "border-slate-200"}`}></div>
          </div>
          <div className="relative flex justify-center text-[10px] font-black uppercase tracking-widest">
            <span className={`px-3 py-1 rounded-full border shadow-sm backdrop-blur-md ${isDark
                ? "bg-slate-900/60 border-white/5 text-slate-400"
                : "bg-white/80 border-slate-200 text-slate-500"
              }`}>
              or
            </span>
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
            <div className="flex justify-between items-start gap-2">
              <div>
                <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                  Meeting with {ticket.assigned_lawyer_name || "Lawyer"}
                </h4>
                <p className="text-[10px] text-slate-500 font-medium">
                  {meetingDate.toLocaleString()}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                <span className="px-2 py-1 bg-blue-500/20 text-blue-500 rounded-lg text-[8px] font-black uppercase tracking-widest">
                  Booked
                </span>
                {renderPriorityBadge()}
              </div>
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

        {/* Pre-Consultation Messages */}
        <PreConsultationChat ticketId={ticket.ticket_id} isDark={isDark} userRole="user" conversationId={conversationId} />
      </div>
    );
  }

  // 4. RESOLVED: Lawyer finished
  // 4. RESOLVED: Lawyer finished
  if (status === "resolved") {
    const isClosedOrResolvedClosed = caseClosed || ticket?.status === "closed";

    return (
      <div className={`p-6 rounded-2xl border-2 border-dashed animate-in fade-in zoom-in duration-500 ${isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-100"
        }`}>
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center mb-4 shadow-xl shadow-emerald-500/20">
            <ShieldCheck className="text-white w-6 h-6" />
          </div>
          <h4 className={`text-base font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
            {isClosedOrResolvedClosed ? "Matter Closed" : "Resolution Ready"}
          </h4>
          <p className="text-[11px] text-slate-500 font-medium">
            {isClosedOrResolvedClosed
              ? (ticket.outcome_notes && ticket.outcome_notes.toLowerCase().includes("automatically closed")
                ? "This case has been automatically closed as no action was taken within 24 hours of lawyer resolution. Please rate your experience."
                : "This case has been closed. Please rate your experience.")
              : "Your legal consultation has been completed."}
          </p>
        </div>

        {/* The Actual Lawyer Response */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Scale size={12} className="text-indigo-500" />
            <span className="text-indigo-600 text-[10px] font-bold uppercase tracking-wider">Legal Resolution</span>
          </div>
          <div className={`relative p-4 rounded-xl border-l-4 border-indigo-500 shadow-sm ${isDark
              ? "bg-slate-900/60 border-slate-800 text-slate-200"
              : "bg-slate-50 border-slate-200 text-slate-750"
            }`}>
            <div className="prose prose-sm dark:prose-invert max-w-none relative z-10 text-[11px] leading-relaxed font-medium">
              <ReactMarkdown
                components={{
                  p: ({ node, ...props }) => <p className="mb-2 last:mb-0" {...props} />,
                  strong: ({ node, ...props }) => <strong className="font-bold text-indigo-500" {...props} />,
                  ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-2" {...props} />,
                }}
              >
                {ticket.lawyer_response || ticket.outcome_notes || "No specific feedback notes were recorded for this resolution."}
              </ReactMarkdown>
            </div>
          </div>

          {isClosedOrResolvedClosed ? (
            /* Rating Section */
            <div className={`mt-6 p-6 rounded-3xl border ${isDark ? "bg-[#0b1329]/60 border-white/5" : "bg-white border-slate-100"
              } shadow-sm transition-all duration-300`}>
              {ratingSubmitted ? (
                <div className="flex flex-col items-center text-center">
                  <h5 className={`text-xs font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
                    Feedback Submitted
                  </h5>
                  <p className="text-[10px] text-slate-500 font-medium mb-3">
                    Thank you for rating your consultation!
                  </p>
                  <div className="flex gap-1 mb-2">
                    {[1, 2, 3, 4, 5].map((star) => (
                      <Star
                        key={star}
                        size={14}
                        fill={star <= rating ? "#f59e0b" : "none"}
                        color={star <= rating ? "#f59e0b" : "#64748b"}
                      />
                    ))}
                  </div>
                  {ratingComment && (
                    <p className="text-[10px] text-slate-400 italic max-w-xs leading-relaxed mt-2 border-t border-white/5 pt-2 w-full">
                      "{ratingComment}"
                    </p>
                  )}
                </div>
              ) : (
                <form onSubmit={handleRatingSubmit} className="space-y-4">
                  <div className="text-center">
                    <h5 className={`text-xs font-black uppercase tracking-widest ${isDark ? "text-indigo-450" : "text-indigo-600"} mb-1`}>
                      Rate Your Consultation
                    </h5>
                    <p className="text-[9px] text-slate-500 font-medium">
                      How was your discussion with {ticket.assigned_lawyer_name || "your lawyer"}?
                    </p>
                  </div>

                  {/* Stars Selector */}
                  <div className="flex justify-center gap-2 py-2">
                    {[1, 2, 3, 4, 5].map((star) => {
                      const isLit = star <= (ratingHover || rating);
                      return (
                        <button
                          type="button"
                          key={star}
                          onMouseEnter={() => setRatingHover(star)}
                          onMouseLeave={() => setRatingHover(0)}
                          onClick={() => setRating(star)}
                          className="transition-transform duration-150 hover:scale-125 focus:outline-none"
                        >
                          <Star
                            size={24}
                            fill={isLit ? "#f59e0b" : "none"}
                            color={isLit ? "#f59e0b" : "#475569"}
                            className="cursor-pointer"
                          />
                        </button>
                      );
                    })}
                  </div>

                  {/* Comment field */}
                  <div className="space-y-1">
                    <textarea
                      value={ratingComment}
                      onChange={(e) => setRatingComment(e.target.value)}
                      placeholder="Describe your experience (optional)..."
                      rows={2}
                      className={`w-full p-3 rounded-xl border text-xs font-medium resize-none transition-all outline-none ${isDark
                          ? "bg-slate-955 border-white/5 focus:border-indigo-500/30 text-slate-300"
                          : "bg-slate-50 border-slate-200 focus:border-indigo-600/30 text-slate-900 focus:bg-white"
                        }`}
                    />
                  </div>

                  {ratingError && (
                    <p className="text-[10px] text-red-500 text-center font-semibold">
                      {ratingError}
                    </p>
                  )}

                  <div className="flex justify-center">
                    <button
                      type="submit"
                      disabled={rating === 0 || submittingRating}
                      className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-md ${rating === 0
                          ? "bg-slate-800 text-slate-500 cursor-not-allowed opacity-50"
                          : "bg-indigo-600 hover:bg-indigo-500 active:scale-95"
                        }`}
                    >
                      {submittingRating ? "Submitting..." : "Submit Feedback"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          ) : showReescalateOptions ? (
            <div className={`mt-5 p-5 rounded-2xl border ${isDark ? "bg-slate-900/60 border-slate-800" : "bg-slate-50 border-slate-200"} shadow-sm text-center space-y-3`}>
              <h5 className={`text-xs font-bold ${isDark ? "text-indigo-400" : "text-indigo-650"}`}>
                Re-escalation Options
              </h5>
              <p className="text-[10px] text-slate-500 font-medium leading-relaxed">
                Would you like to assign this back to the same lawyer or submit it to a different professional?
              </p>
              <div className="flex flex-col gap-2 pt-1">
                <button
                  onClick={() => handleReescalateCase("same")}
                  disabled={reescalateOption !== null}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold transition-all shadow-sm"
                >
                  {reescalateOption === "same" ? "Re-escalating..." : "Same Lawyer"}
                </button>
                <button
                  onClick={() => handleReescalateCase("different")}
                  disabled={reescalateOption !== null}
                  className={`w-full py-2 rounded-xl text-xs font-semibold border transition-all ${isDark
                      ? "bg-slate-800 hover:bg-slate-700 text-white border-slate-700"
                      : "bg-white hover:bg-slate-100 text-slate-700 border-slate-300"
                    }`}
                >
                  {reescalateOption === "different" ? "Re-escalating..." : "Different Lawyer"}
                </button>
                <button
                  onClick={() => setShowReescalateOptions(false)}
                  className="text-[10px] font-bold text-slate-500 hover:text-slate-450 pt-1"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-5 flex gap-3">
              <button
                onClick={handleCloseCase}
                disabled={isClosing}
                className="flex-1 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-semibold shadow-sm transition-all"
              >
                {isClosing ? "Closing..." : "Close the Case"}
              </button>
              <button
                onClick={() => setShowReescalateOptions(true)}
                className={`flex-1 py-2 rounded-xl text-xs font-semibold border transition-all ${isDark
                    ? "bg-slate-800 hover:bg-slate-700 text-white border-slate-700"
                    : "bg-white hover:bg-slate-100 text-slate-700 border-slate-300"
                  }`}
              >
                Re-escalate
              </button>
            </div>
          )}
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
        {!ratingSubmitted ? (
          <form onSubmit={handleRatingSubmit} className="space-y-4">
            <div className="text-center">
              {ticket.outcome_notes && ticket.outcome_notes.toLowerCase().includes("automatically closed") && (
                <div className={`mb-3 p-3 rounded-xl text-[10px] leading-relaxed font-semibold text-center border border-dashed ${isDark ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-400" : "bg-indigo-50 border-indigo-100 text-indigo-700"
                  }`}>
                  This case has been automatically closed as no action was taken within 24 hours of lawyer resolution. Please rate your experience.
                </div>
              )}
              <h5 className={`text-xs font-black uppercase tracking-widest ${isDark ? "text-indigo-450" : "text-indigo-600"} mb-1`}>
                Rate Your Consultation
              </h5>
              <p className="text-[9px] text-slate-500 font-medium">
                How was your discussion with {ticket.assigned_lawyer_name || "your lawyer"}?
              </p>
            </div>

            {/* Stars Selector */}
            <div className="flex justify-center gap-2 py-2">
              {[1, 2, 3, 4, 5].map((star) => {
                const isLit = star <= (ratingHover || rating);
                return (
                  <button
                    type="button"
                    key={star}
                    onMouseEnter={() => setRatingHover(star)}
                    onMouseLeave={() => setRatingHover(0)}
                    onClick={() => setRating(star)}
                    className="transition-transform duration-150 hover:scale-125 focus:outline-none"
                  >
                    <Star
                      size={24}
                      fill={isLit ? "#f59e0b" : "none"}
                      color={isLit ? "#f59e0b" : "#475569"}
                      className="cursor-pointer"
                    />
                  </button>
                );
              })}
            </div>

            {/* Comment field */}
            <div className="space-y-1">
              <textarea
                value={ratingComment}
                onChange={(e) => setRatingComment(e.target.value)}
                placeholder="Describe your experience (optional)..."
                rows={2}
                className={`w-full p-3 rounded-xl border text-xs font-medium resize-none transition-all outline-none ${isDark
                    ? "bg-slate-955 border-white/5 focus:border-indigo-500/30 text-slate-300"
                    : "bg-slate-50 border-slate-200 focus:border-indigo-600/30 text-slate-900 focus:bg-white"
                  }`}
              />
            </div>

            {ratingError && (
              <p className="text-[10px] text-red-500 text-center font-semibold">
                {ratingError}
              </p>
            )}

            <div className="flex justify-center">
              <button
                type="submit"
                disabled={rating === 0 || submittingRating}
                className={`px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest text-white transition-all shadow-md ${rating === 0
                    ? "bg-slate-800 text-slate-500 cursor-not-allowed opacity-50"
                    : "bg-indigo-600 hover:bg-indigo-500 active:scale-95"
                  }`}
              >
                {submittingRating ? "Submitting..." : "Submit Feedback"}
              </button>
            </div>
          </form>
        ) : (
          <div className="flex flex-col items-center text-center">
            <ShieldCheck className="text-slate-500 w-8 h-8 mb-3 opacity-50" />
            <h4 className={`text-sm font-black tracking-tight mb-1 ${isDark ? "text-white" : "text-slate-900"}`}>
              Matter Archived
            </h4>
            <p className="text-[10px] text-slate-500 font-medium">
              This legal consultation has been closed and archived.
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="p-4 text-center text-[10px] text-slate-500 italic">
      Waiting for legal status updates...
    </div>
  );
}

function PreConsultationChat({ ticketId, isDark, userRole = "user", conversationId }) {
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = React.useRef(null);

  const fileInputRef = React.useRef(null);
  const { uploadDocument, isUploading, uploadError, clearUploadError } = useDocumentUpload(conversationId);

  const fetchMessages = useCallback(async (shouldMarkRead = false) => {
    try {
      const data = await hitlService.getTicketMessages(ticketId);
      const msgList = Array.isArray(data) ? data : (data?.messages || []);
      setMessages(msgList);
      setLoading(false);

      // Check if there are any unread messages from the other side
      const hasUnread = Array.isArray(msgList) && msgList.some(m => !m.is_read && m.sender_role !== userRole);
      if (hasUnread || shouldMarkRead) {
        await hitlService.markTicketMessagesRead(ticketId);
      }
    } catch (err) {
      console.error("Failed to fetch ticket messages:", err);
    }
  }, [ticketId, userRole]);


  useEffect(() => {
    fetchMessages(true);

    const interval = setInterval(() => {
      fetchMessages();
    }, 15000); // 15 seconds polling

    return () => clearInterval(interval);
  }, [fetchMessages]);

  useEffect(() => {
    // Scroll to bottom on new messages
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (uploadError) {
      const timer = setTimeout(() => {
        clearUploadError();
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [uploadError, clearUploadError]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!newMessage.trim() || sending) return;

    setSending(true);
    try {
      await hitlService.sendTicketMessage(ticketId, newMessage.trim());
      setNewMessage("");
      await fetchMessages();
    } catch (err) {
      console.error("Failed to send message:", err);
    } finally {
      setSending(false);
    }
  };

  const handleAttachClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const result = await uploadDocument(file, conversationId);
      if (result && result.document_id) {
        await hitlService.sendTicketMessage(
          ticketId,
          `Sent a document: ${result.file_name}`,
          result.file_name,
          result.document_id
        );
        await fetchMessages();
      }
    } catch (err) {
      console.error("Failed to upload document in chat:", err);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDownload = async (documentId, fileName) => {
    try {
      const token = await window.Clerk?.session?.getToken();
      const url = `${API_BASE_URL}/api/v1/documents/view/${documentId}${token ? `?token=${token}` : ""}`;
      window.open(url, "_blank");
    } catch (err) {
      console.error("Failed to download document:", err);
    }
  };

  if (loading && messages.length === 0) {
    return (
      <div className="flex justify-center p-4">
        <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className={`mt-6 rounded-2xl border flex flex-col overflow-hidden ${isDark ? "bg-slate-900/40 border-white/5" : "bg-slate-50 border-slate-200"
      }`}>
      {/* Header */}
      <div className={`px-4 py-3 border-b flex items-center justify-between ${isDark ? "bg-slate-900/60 border-white/5" : "bg-slate-100 border-slate-200"
        }`}>
        <div className="flex items-center gap-2">
          <Scale size={14} className={isDark ? "text-indigo-400" : "text-indigo-600"} />
          <span className={`text-[10px] font-black uppercase tracking-widest ${isDark ? "text-slate-300" : "text-slate-700"
            }`}>
            Pre-Consultation Messages
          </span>
        </div>
        {messages.some(m => !m.is_read && m.sender_role !== userRole) && (
          <span className="w-2 h-2 bg-red-500 rounded-full animate-ping" />
        )}
      </div>

      {/* Message List */}
      <div className="p-4 max-h-[240px] overflow-y-auto space-y-3 flex-1 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-[10px] text-slate-500 font-medium">
              No messages yet. Ask your lawyer a question or share draft documents.
            </p>
          </div>
        ) : (
          messages.map((msg) => {
            const isMe = msg.sender_role === userRole;
            const hasAttachment = !!msg.document_id;
            return (
              <div
                key={msg.message_id}
                className={`flex flex-col ${isMe ? "items-end" : "items-start"}`}
              >
                <div className="flex items-center gap-1 mb-0.5 px-1">
                  <span className="text-[9px] font-black text-slate-500">
                    {isMe ? "You" : (msg.sender_role === "lawyer" ? "Lawyer" : "👤 Client")}
                  </span>
                  <span className="text-[8px] text-slate-400">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className={`max-w-[85%] px-3.5 py-2 rounded-2xl text-[11px] font-medium leading-relaxed shadow-sm flex flex-col gap-2 ${isMe
                    ? "bg-indigo-600 text-white rounded-tr-none"
                    : (isDark
                      ? "bg-slate-800 text-slate-200 border border-white/5 rounded-tl-none"
                      : "bg-white text-slate-800 border border-slate-200 rounded-tl-none")
                  }`}>
                  {hasAttachment ? (
                    <div
                      onClick={() => handleDownload(msg.document_id, msg.file_name)}
                      className={`flex items-center gap-2.5 p-2 rounded-xl border transition-all cursor-pointer select-none ${isMe
                          ? "bg-indigo-700/50 border-indigo-500/30 hover:bg-indigo-700/70"
                          : (isDark
                            ? "bg-slate-900/60 border-white/5 hover:bg-slate-900/80"
                            : "bg-slate-50 border-slate-100 hover:bg-slate-100/70")
                        }`}
                    >
                      <div className={`p-1.5 rounded-lg ${isMe ? "bg-indigo-500/30" : "bg-indigo-500/10 text-indigo-500"
                        }`}>
                        <FileText size={14} className={isMe ? "text-indigo-200" : "text-indigo-500"} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-[10px] font-bold truncate max-w-[140px] ${isMe ? "text-white" : (isDark ? "text-slate-200" : "text-slate-800")
                          }`}>
                          {msg.file_name || "Document"}
                        </p>
                        <p className={`text-[8px] ${isMe ? "text-indigo-200" : "text-slate-400"
                          }`}>
                          Click to download
                        </p>
                      </div>
                      <Download size={12} className={isMe ? "text-indigo-200" : "text-slate-400"} />
                    </div>
                  ) : (
                    <div>{msg.content}</div>
                  )}
                  {hasAttachment && msg.content && !msg.content.startsWith("Sent a document:") && (
                    <div className="text-[11px] leading-relaxed whitespace-pre-wrap mt-1">
                      {msg.content}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {uploadError && (
        <div className={`px-4 py-2 text-[10px] font-bold text-center border-t transition-all animate-in fade-in duration-300 ${isDark ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-red-50 text-red-600 border-red-100"
          }`}>
          {uploadError}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSend} className={`p-3 border-t flex gap-2 items-center ${isDark ? "bg-slate-900/30 border-white/5" : "bg-white border-slate-200"
        }`}>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileUpload}
          accept=".pdf,.docx,.doc"
          style={{ display: "none" }}
        />

        <button
          type="button"
          onClick={handleAttachClick}
          disabled={isUploading || sending}
          className={`p-2 rounded-xl transition-all flex items-center justify-center flex-shrink-0 ${isDark
              ? "bg-slate-950 border border-white/5 text-slate-400 hover:text-white hover:bg-slate-800/50"
              : "bg-slate-50 border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-100"
            }`}
          title="Attach a document (.pdf, .docx)"
        >
          {isUploading ? (
            <Loader2 size={14} className="animate-spin text-indigo-500" />
          ) : (
            <Paperclip size={14} />
          )}
        </button>

        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type a message to your lawyer..."
          disabled={sending || isUploading}
          style={{ flex: "1 1 0%", minWidth: "0" }}
          className={`flex-1 min-w-0 px-3 py-2 rounded-xl text-[11px] font-medium outline-none transition-all ${isDark
              ? "bg-slate-950 border border-white/5 text-slate-300 focus:border-indigo-500/30"
              : "bg-slate-50 border border-slate-200 text-slate-900 focus:border-indigo-600/30 focus:bg-white"
            }`}
        />
        <button
          type="submit"
          disabled={!newMessage.trim() || sending || isUploading}
          className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest text-white flex-shrink-0 transition-all ${!newMessage.trim() || sending || isUploading
              ? (isDark ? "bg-slate-800 text-slate-600" : "bg-slate-200 text-slate-400")
              : "bg-indigo-600 hover:bg-indigo-500 active:scale-95 shadow-md"
            }`}
        >
          {sending ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
