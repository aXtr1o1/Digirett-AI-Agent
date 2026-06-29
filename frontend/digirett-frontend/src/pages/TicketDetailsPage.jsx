import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useClerk } from "@clerk/clerk-react";
import hitlService from "../services/hitlService";
import conversationService from "../services/conversationService";
import {
  User,
  MessageSquare,
  Send,
  Loader2,
  Clock,
  Paperclip,
  X,
  LogOut,
  ShieldCheck,
  ChevronRight,
  CheckCircle2,
  Scale as ScaleIcon,
  MoreHorizontal,
  MapPin,
  Tag,
  AlertTriangle,
  Calendar,
  Hash,
  CheckCircle,
  History as HistoryIcon,
  Sun,
  Moon,
  UserX,
  LayoutDashboard,
  Star,
  FileText,
  Download
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import useDocumentUpload from "../hooks/useDocumentUpload";
import { API_BASE_URL } from "../utils/constants";
import { useTheme } from "../providers/ThemeProvider";
import BackgroundLayer from "../components/common/BackgroundLayer";

export default function TicketDetailsPage() {
  const { theme, isDark, toggleTheme } = useTheme();
  const { signOut } = useClerk();
  const { id } = useParams();
  const navigate = useNavigate();

  // State
  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [ticketRating, setTicketRating] = useState(null);
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const currentView = searchParams.get("view") || "details";
  const setCurrentView = (view) => setSearchParams({ view });
  const [isSuccess, setIsSuccess] = useState(false);
  const [showNoShowConfirm, setShowNoShowConfirm] = useState(false);
  const [noShowType, setNoShowType] = useState("user");
  const [hasUnreadMessages, setHasUnreadMessages] = useState(false);
  const [isBriefExpanded, setIsBriefExpanded] = useState(true);
  const fileInputRef = React.useRef(null);

  const { uploadDocument, isUploading, uploadError } = useDocumentUpload(ticket?.conversation_id);

  const checkUnreadStatus = useCallback(async () => {
    try {
      const msgs = await hitlService.getTicketMessages(id);
      const hasUnread = msgs.some(m => !m.is_read && m.sender_role === "user");
      setHasUnreadMessages(hasUnread);
    } catch (err) {
      console.error("Failed to check unread messages:", err);
    }
  }, [id]);

  const fetchData = useCallback(async () => {
    try {
      const ticketData = await hitlService.getTicketDetails(id);
      setTicket(ticketData);

      const convData = await conversationService.getConversationWithMessages(ticketData.conversation_id);
      setMessages(convData.messages || []);

      // Pull ratings to support localStorage fallback mapping
      const ratingsData = await hitlService.getLawyerRatings().catch(() => []);
      const ratingInfo = ratingsData.find(r => r.ticket_id === id);
      if (ratingInfo) {
        setTicketRating(ratingInfo);
      }
      
      await checkUnreadStatus();
    } catch (err) {
      console.error("Failed to fetch details:", err);
      setError(err.message || "Unauthorized or not found");
    } finally {
      setLoading(false);
    }
  }, [id, checkUnreadStatus]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (currentView === "messages") {
      setHasUnreadMessages(false);
    } else {
      checkUnreadStatus();
      const interval = setInterval(checkUnreadStatus, 15000);
      return () => clearInterval(interval);
    }
  }, [currentView, checkUnreadStatus]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!response.trim() && !file) return;
    setSubmitting(true);
    try {
      let finalResponse = response;
      if (file) {
        const uploadResult = await uploadDocument(file, ticket.conversation_id);
        if (uploadResult) {
          finalResponse += `\n\n[Attached Document: ${uploadResult.file_name}]`;
        } else {
          throw new Error(uploadError || "File upload failed");
        }
      }
      await hitlService.respondToTicket(id, finalResponse);
      setIsSuccess(true);
      // Optional: Navigate after a delay
      // setTimeout(() => navigate("/lawyer"), 3000);
    } catch (err) {
      alert(err.message || "Failed to submit response");
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-GB', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  const handleNoShow = async () => {
    setSubmitting(true);
    try {
      await hitlService.markNoShow(id, "User did not attend the scheduled meeting.", "user");
      setIsSuccess(true);
      setShowNoShowConfirm(false);
    } catch (err) {
      alert(err.message || "Failed to mark as no-show");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className={`min-h-screen flex items-center justify-center relative overflow-hidden ${isDark ? "bg-gray-950" : "bg-[#F5F7FA]"}`}>
        <BackgroundLayer theme={theme} />
        <Loader2 className="h-8 w-8 animate-spin text-blue-600 relative z-10" />
      </div>
    );
  }

  if (error && !ticket) {
    return (
      <div className={`min-h-screen flex flex-col items-center justify-center relative overflow-hidden ${isDark ? "bg-[#020617] text-white" : "bg-[#f1f5f9] text-gray-900"}`}>
        <BackgroundLayer theme={theme} />
        <div className={`relative z-10 p-8 rounded-2xl border max-w-md text-center shadow-xl ${isDark ? "bg-slate-900/80 border-red-500/30" : "bg-white border-red-200"}`}>
          <div className="h-16 w-16 rounded-full bg-red-500/10 text-red-500 flex items-center justify-center mx-auto mb-6">
            <AlertTriangle size={32} />
          </div>
          <h2 className="text-xl font-bold mb-2">Error Loading Ticket</h2>
          <p className={`text-sm font-medium mb-8 ${isDark ? "text-red-400" : "text-red-600"}`}>{error}</p>
          <button
            onClick={() => navigate("/lawyer")}
            className="h-11 px-8 rounded-xl bg-blue-600 text-white font-bold text-xs uppercase tracking-widest shadow-lg shadow-blue-600/20 hover:bg-blue-700 transition-all"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const userInfo = ticket?.user_info || {};
  const initials = (userInfo.display_name || "U").split(' ').map(n => n[0]).join('').toUpperCase();

  return (
    <div className="h-screen overflow-hidden flex bg-[#F8F9FC] text-[#1E293B] font-sans">

      {/* 1) REFINED SIDEBAR (2nd SS Style) */}
      <aside className="w-[260px] flex-shrink-0 flex flex-col bg-[#0F172A] text-white relative h-full z-50">
        <div className="p-6 flex items-center gap-3 mb-2">
          <div className="h-7 w-7 overflow-hidden flex items-center justify-center bg-transparent">
            <img src="/digirett-logo.png" alt="Digirett Logo" className="w-full h-full object-contain" />
          </div>
          <div>
            <h1 className="font-bold text-base tracking-tight leading-none text-white">Lawyer Panel</h1>
          </div>
        </div>

        <div className="px-3 py-4 flex-1 space-y-1">
          <p className="px-4 py-2 text-[10px] font-black text-gray-500 uppercase tracking-widest opacity-50">Main Console</p>

          <button
            onClick={() => setCurrentView("details")}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${currentView === "details" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
              }`}
          >
            <User size={18} />
            <span className="text-sm font-semibold tracking-wide">User Details</span>
          </button>

          {ticket?.ai_brief && (
            <button
              onClick={() => setCurrentView("brief")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${currentView === "brief" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
                }`}
            >
              <FileText size={18} />
              <span className="text-sm font-semibold tracking-wide">Case Brief</span>
            </button>
          )}

          <button
            onClick={() => setCurrentView("resolve")}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${currentView === "resolve" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
              }`}
          >
            <CheckCircle2 size={18} />
            <span className="text-sm font-semibold tracking-wide">Resolve Matter</span>
          </button>

          {(ticket?.status === 'resolved' || ticket?.status === 'closed') && (
            <button
              onClick={() => setCurrentView("feedback")}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${currentView === "feedback" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
                }`}
            >
              <Star size={18} />
              <span className="text-sm font-semibold tracking-wide">Client Feedback</span>
            </button>
          )}

          <button
            onClick={() => setShowNoShowConfirm(true)}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group text-gray-400 hover:bg-red-500/10 hover:text-red-400"
          >
            <UserX size={18} />
            <span className="text-sm font-semibold tracking-wide">Mark No-Show</span>
          </button>

          <button
            onClick={() => setCurrentView("messages")}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all group ${currentView === "messages" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
              }`}
          >
            <div className="flex items-center gap-3">
              <MessageSquare size={18} />
              <span className="text-sm font-semibold tracking-wide">Pre-Consultation Chat</span>
            </div>
            {hasUnreadMessages && (
              <div className="h-2 w-2 rounded-full bg-red-500 animate-ping"></div>
            )}
          </button>

          <button
            onClick={() => setCurrentView("context")}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all group ${currentView === "context" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
              }`}
          >
            <div className="flex items-center gap-3">
              <MessageSquare size={18} />
              <span className="text-sm font-semibold tracking-wide">Context Details</span>
            </div>
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400"></div>
          </button>

          <button
            onClick={() => navigate("/lawyer")}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-gray-400 hover:bg-white/5 hover:text-white"
          >
            <LayoutDashboard size={18} />
            <span className="text-sm font-semibold tracking-wide">Go to Dashboard</span>
          </button>

        </div>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => signOut()}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all text-sm font-bold"
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className={`flex-1 flex flex-col h-screen overflow-hidden ${isDark ? "bg-[#020617] text-slate-200" : "bg-[#f1f5f9] text-slate-900"}`}>
        {/* COMPACT TOP BAR */}
        <header className={`px-8 h-16 border-b flex items-center justify-between z-10 shrink-0 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-200"}`}>
          <div className="flex items-center gap-3 text-[11px] font-bold uppercase tracking-wider text-gray-400">
            <button onClick={() => navigate("/lawyer")} className={`transition-colors ${isDark ? "hover:text-white" : "hover:text-gray-900"}`}>
              Matter Review
            </button>
            <ChevronRight size={12} />
            <span className="text-blue-600">{currentView === "details" ? "User Details" : currentView === "brief" ? "Case Brief" : currentView === "resolve" ? "Resolve Matter" : currentView === "context" ? "Context Details" : currentView === "feedback" ? "Client Feedback" : "User Details"}</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={toggleTheme}
              className={`h-9 w-9 rounded-lg border flex items-center justify-center transition-all ${isDark ? "bg-slate-800 border-slate-700 text-blue-400 hover:bg-slate-700" : "bg-white border-gray-100 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                }`}
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider border ${ticket.status === 'resolved' || ticket.status === 'closed'
              ? (isDark ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-emerald-50 text-emerald-600 border-emerald-100")
              : ticket.status === 'booked'
                ? (isDark ? "bg-blue-500/10 text-blue-400 border-blue-500/20" : "bg-blue-50 text-blue-600 border-blue-100")
                : (isDark ? "bg-amber-500/10 text-amber-400 border-amber-500/20" : "bg-amber-50 text-amber-600 border-amber-100")
              }`}>
              <div className={`h-1 w-1 rounded-full ${ticket.status === 'resolved' || ticket.status === 'closed' ? "bg-emerald-500" : ticket.status === 'booked' ? "bg-blue-500" : "bg-amber-500"
                }`}></div>
              {ticket.status?.toUpperCase() || 'OPEN'}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="max-w-4xl mx-auto">

            {/* ERROR BANNER FOR PARTIAL FAILURES (e.g., messages failed to load) */}
            {error && ticket && (
              <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
                <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-bold text-red-500">Partial Data Load Error</h4>
                  <p className="text-xs text-red-400/90 mt-1 font-medium">{error}</p>
                </div>
              </div>
            )}

            {/* VIEW 1: USER DETAILS */}
            {currentView === "details" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-gray-400 mb-4">Active Client</p>

                <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                  <div className="flex items-center gap-6 mb-10">
                    <div className="h-20 w-20 rounded-2xl bg-blue-600 flex items-center justify-center text-3xl font-bold text-white">
                      {initials}
                    </div>
                    <div>
                      <h2 className={`text-2xl font-bold tracking-tight ${isDark ? "text-white" : "text-gray-900"}`}>{userInfo.display_name || "Client"}</h2>
                      <p className={`text-sm font-medium mt-0.5 ${isDark ? "text-slate-400" : "text-gray-500"}`}>{userInfo.email || "No contact verified"}</p>
                      <div className="flex items-center gap-1.5 mt-3 px-2 py-0.5 bg-emerald-50 border border-emerald-100 rounded-md w-fit">
                        <CheckCircle size={12} className="text-emerald-500" />
                        <span className="text-[9px] font-bold text-emerald-600 uppercase tracking-widest">Verified</span>
                      </div>
                    </div>
                  </div>

                  <div className={`grid grid-cols-1 divide-y ${isDark ? "divide-slate-800" : "divide-gray-50"}`}>
                    {[
                      { icon: <Hash size={16} />, label: "Matter ID", value: `#${ticket.ticket_id || id.slice(0, 8).toUpperCase()}`, valueClass: "text-blue-600" },
                      {
                        icon: <Clock size={16} />,
                        label: "Assigned",
                        value: ticket.assigned_at ? formatDate(ticket.assigned_at) : "Pending"
                      },
                      {
                        icon: <Calendar size={16} />,
                        label: "Scheduled",
                        value: ticket.booking_confirmed_at ? formatDate(ticket.booking_confirmed_at) : "Not yet scheduled"
                      },
                      ticket.region && { icon: <MapPin size={16} />, label: "Region", value: ticket.region },
                      ticket.category && { icon: <Tag size={16} />, label: "Category", value: ticket.category },
                      ticket.priority && { icon: <AlertTriangle size={16} />, label: "Priority", value: ticket.priority, valueClass: "text-orange-500" },
                      ticket.created_at && { icon: <Calendar size={16} />, label: "Opened", value: new Date(ticket.created_at).toLocaleDateString() }
                    ].filter(Boolean).map((item, i) => (
                      <div key={i} className="flex items-center justify-between py-4">
                        <div className="flex items-center gap-3">
                          <div className="text-gray-400">{item.icon}</div>
                          <span className={`text-xs font-medium ${isDark ? "text-slate-400" : "text-gray-500"}`}>{item.label}</span>
                        </div>
                        <span className={`text-xs font-bold ${item.valueClass || (isDark ? "text-slate-200" : "text-gray-900")}`}>{item.value}</span>
                      </div>
                    ))}
                  </div>

                  {ticket.conversation_summary && (
                    <div className="mt-8 pt-8 border-t border-slate-100 dark:border-slate-800 space-y-4">
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500">Summary of the matter</h4>
                      <div className={`p-6 rounded-2xl ${isDark ? "bg-slate-950/50" : "bg-slate-50"}`}>
                        <p className="text-sm leading-relaxed text-slate-500 italic">
                          {ticket.conversation_summary}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {currentView === "resolve" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                {ticket.status === 'resolved' || ticket.status === 'closed' ? (
                  <div className="space-y-6">
                    <div className="mb-8">
                      <h2 className={`text-3xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Matter Resolved</h2>
                      <p className="text-gray-400 font-bold uppercase text-[9px] tracking-widest">Final legal outcome provided on {new Date(ticket.resolved_at || ticket.closed_at).toLocaleDateString()}</p>
                    </div>

                    <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-indigo-500 mb-4">Official Lawyer Response</h4>
                      <div className={`p-6 rounded-xl border text-sm leading-relaxed font-medium ${isDark ? "bg-slate-950 border-slate-800 text-slate-300" : "bg-slate-50 border-transparent text-slate-700"}`}>
                        <ReactMarkdown>{ticket.lawyer_response || "No written response was recorded."}</ReactMarkdown>
                      </div>

                      {ticket.outcome_notes && (
                        <>
                          <h4 className="text-[10px] font-black uppercase tracking-widest text-amber-500 mt-8 mb-4">Internal Outcome Notes</h4>
                          <div className={`p-6 rounded-xl border text-sm leading-relaxed font-medium italic ${isDark ? "bg-slate-950 border-slate-800 text-slate-400" : "bg-amber-50/30 border-transparent text-slate-600"}`}>
                            {ticket.outcome_notes}
                          </div>
                        </>
                      )}

                      <div className="mt-10 pt-6 border-t border-slate-100 dark:border-slate-800">
                        <button
                          onClick={() => navigate("/lawyer")}
                          className="h-11 px-8 rounded-xl bg-[#0F172A] text-white font-bold text-xs uppercase tracking-widest hover:bg-gray-800 transition-all shadow-lg"
                        >
                          Back to Workspace
                        </button>
                      </div>
                    </div>
                  </div>
                ) : isSuccess ? (
                  <div className={`flex flex-col items-center justify-center py-20 rounded-2xl border shadow-sm text-center ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                    <div className="h-20 w-20 rounded-full bg-emerald-500 flex items-center justify-center mb-8 shadow-xl shadow-emerald-500/20 animate-in zoom-in duration-500">
                      <CheckCircle2 size={40} className="text-white" />
                    </div>
                    <h2 className={`text-3xl font-bold tracking-tight mb-8 ${isDark ? "text-white" : "text-gray-900"}`}>Resolution Successfully Dispatched</h2>
                    <button
                      onClick={() => navigate("/lawyer")}
                      className="h-12 px-10 rounded-xl bg-[#0F172A] text-white font-bold text-xs uppercase tracking-widest hover:bg-gray-800 transition-all shadow-lg"
                    >
                      Return to Workspace
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="mb-8">
                      <h2 className={`text-3xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Resolve Matter</h2>
                      <p className="text-gray-400 font-bold uppercase text-[9px] tracking-widest">Draft legal outcome for client</p>
                    </div>

                    <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                      <textarea
                        value={response}
                        onChange={(e) => setResponse(e.target.value)}
                        placeholder="Type the final resolution details here..."
                        className={`w-full min-h-[350px] p-6 rounded-xl border transition-all outline-none text-sm font-medium leading-relaxed ${isDark ? "bg-slate-950 border-slate-800 text-slate-300 focus:border-blue-500/30" : "bg-gray-50 border-transparent focus:border-blue-600/20 focus:bg-white text-gray-900"
                          }`}
                      />

                      <div className="flex items-center justify-end mt-6">
                        <button
                          onClick={handleSubmit}
                          disabled={submitting || (!response.trim() && !file)}
                          className="h-11 px-8 rounded-xl bg-blue-600 text-white font-bold text-xs uppercase tracking-widest shadow-lg shadow-blue-600/20 hover:bg-blue-700 transition-all disabled:opacity-50"
                        >
                          {submitting ? "Submitting..." : "Submit Resolution"}
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* VIEW: CASE BRIEF */}
            {currentView === "brief" && ticket.ai_brief && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-gray-400 mb-4">AI Matter Intelligence</p>

                <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                  <div className="flex items-center justify-between mb-8 border-b pb-6 dark:border-slate-800">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">📋</span>
                      <div>
                        <h2 className={`text-xl font-bold tracking-tight ${isDark ? "text-white" : "text-gray-900"}`}>Case Brief</h2>
                        <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider mt-0.5">Automated Pre-Consultation Summary</p>
                      </div>
                    </div>
                    <span className="px-3 py-1 bg-indigo-500/10 text-indigo-400 rounded-lg text-[10px] font-black uppercase tracking-widest border border-indigo-500/20">
                      AI Generated
                    </span>
                  </div>

                  <div className="space-y-8">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                      {/* Matter Type */}
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-450 dark:text-slate-500">Matter Type</span>
                        <p className="text-sm font-bold text-slate-850 dark:text-slate-200">
                          {ticket.ai_brief.matter_type || "N/A"}
                        </p>
                      </div>

                      {/* Risk Level */}
                      <div className="space-y-2">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-450 dark:text-slate-500">Risk Level</span>
                        <div>
                          <span className={`inline-block px-3 py-1 rounded-lg text-[10px] font-black uppercase tracking-widest border ${
                            ticket.ai_brief.risk_level?.toLowerCase() === "high"
                              ? "bg-red-500/10 text-red-500 border-red-500/20"
                              : ticket.ai_brief.risk_level?.toLowerCase() === "moderate" || ticket.ai_brief.risk_level?.toLowerCase() === "medium"
                                ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                                : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                          }`}>
                            {ticket.ai_brief.risk_level || "Low"}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Key Issues */}
                    <div className="space-y-3 pt-6 border-t dark:border-slate-800">
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-455 dark:text-slate-500">Key Issues</span>
                      {Array.isArray(ticket.ai_brief.key_issues) && ticket.ai_brief.key_issues.length > 0 ? (
                        <ul className="list-disc list-inside space-y-2.5 text-sm text-slate-600 dark:text-slate-300 font-medium">
                          {ticket.ai_brief.key_issues.map((issue, idx) => (
                            <li key={idx} className="leading-relaxed">{issue}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-slate-455 dark:text-slate-500 italic">None identified</p>
                      )}
                    </div>

                    {/* Relevant Law */}
                    <div className="space-y-3 pt-6 border-t dark:border-slate-800">
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-455 dark:text-slate-500">Relevant Law</span>
                      <div className="flex flex-wrap gap-2.5">
                        {Array.isArray(ticket.ai_brief.relevant_laws) && ticket.ai_brief.relevant_laws.length > 0 ? (
                          ticket.ai_brief.relevant_laws.map((law, idx) => (
                            <span key={idx} className="px-3 py-1.5 bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-xl text-xs font-bold border border-slate-300 dark:border-slate-700">
                              {law}
                            </span>
                          ))
                        ) : (
                          <span className="text-sm text-slate-455 dark:text-slate-500 italic">None specified</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* VIEW: PRE-CONSULTATION CHAT */}
            {currentView === "messages" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="mb-8">
                  <h2 className={`text-3xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Pre-Consultation Chat</h2>
                  <p className="text-gray-400 font-bold uppercase text-[9px] tracking-widest">Secure pre-consultation thread with client</p>
                </div>
                
                <PreConsultationChat ticketId={id} isDark={isDark} userRole="lawyer" onReadMarked={() => setHasUnreadMessages(false)} conversationId={ticket?.conversation_id} />
              </div>
            )}

            {/* VIEW: CLIENT FEEDBACK */}
            {currentView === "feedback" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-gray-400 mb-4">Client Feedback</p>
                <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                  <div className="flex items-center gap-4 mb-6">
                    <div>
                      <h3 className={`text-lg font-bold ${isDark ? "text-white" : "text-gray-900"}`}>Consultation Rating</h3>
                      <p className="text-xs text-slate-500 mt-0.5">Submitted by the client after resolution</p>
                    </div>
                  </div>

                  {(ticket.rating || ticketRating) ? (
                    <>
                      <div className="flex items-center gap-1.5 mb-6">
                        {[1, 2, 3, 4, 5].map((star) => {
                          const currentRating = ticket.rating || ticketRating?.rating || 0;
                          return (
                            <Star
                              key={star}
                              size={20}
                              fill={star <= currentRating ? "#f59e0b" : "none"}
                              color={star <= currentRating ? "#f59e0b" : "#475569"}
                            />
                          );
                        })}
                        <span className="ml-2 font-bold text-lg text-amber-500">
                          {(ticket.rating || ticketRating?.rating || 0).toFixed(1)} / 5.0
                        </span>
                      </div>

                      {(ticket.comment || ticket.rating_comment || ticketRating?.comment) ? (
                        <div className={`p-6 rounded-2xl border ${isDark ? "bg-[#0b1329] border-white/5 text-slate-300" : "bg-slate-50 border-slate-100 text-slate-700"} italic leading-relaxed text-sm`}>
                          "{ticket.comment || ticket.rating_comment || ticketRating?.comment}"
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 italic">No written comment was provided for this rating.</p>
                      )}
                    </>
                  ) : (
                    <div className="py-10 text-center text-slate-400 dark:text-slate-500">
                      <Star size={36} className="mx-auto mb-3 opacity-20" />
                      <p className="text-xs font-bold uppercase tracking-wider">Awaiting Client Feedback</p>
                      <p className="text-[10px] mt-1">The client has not rated this consultation yet.</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* VIEW 3: CONTEXT DETAILS */}
            {currentView === "context" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="mb-8 flex items-center justify-between">
                  <div>
                    <h2 className={`text-3xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Conversation Context</h2>
                    <p className="text-gray-400 font-bold uppercase text-[9px] tracking-widest">Full chat history with intelligence points</p>
                  </div>
                </div>

                <div className="space-y-6">
                  {messages.length === 0 && !error && (
                    <div className={`p-8 rounded-2xl border text-center ${isDark ? "bg-slate-900/50 border-slate-800" : "bg-gray-50 border-gray-100"}`}>
                      <MessageSquare className="h-10 w-10 mx-auto text-gray-400 mb-4 opacity-50" />
                      <h3 className={`text-sm font-bold ${isDark ? "text-slate-300" : "text-gray-700"}`}>No messages found</h3>
                      <p className="text-xs text-gray-500 mt-1">This conversation has no chat history.</p>
                    </div>
                  )}
                  {messages.map((m, idx) => (
                    <div key={m.message_id || idx} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl p-6 text-sm font-medium leading-relaxed ${m.role === 'user'
                        ? "bg-blue-600 text-white rounded-tr-none shadow-lg shadow-blue-600/10"
                        : `${isDark ? "bg-slate-800 border-slate-700 text-slate-200" : "bg-white border-gray-100 text-gray-900 shadow-sm"} rounded-tl-none`
                        }`}>
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                      <div className="mt-2 flex items-center gap-2 px-1 text-[9px] font-bold uppercase tracking-wider text-gray-400">
                        <span>{m.role === 'user' ? (userInfo.display_name || "CLIENT") : "AI SYSTEM"}</span>
                        <span>•</span>
                        <span>{new Date(m.created_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>

        {/* NO-SHOW CONFIRMATION MODAL */}
        {showNoShowConfirm && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className={`w-full max-w-md rounded-3xl border p-8 shadow-2xl animate-in zoom-in-95 duration-200 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
              <div className="h-14 w-14 rounded-2xl bg-red-500/10 text-red-500 flex items-center justify-center mb-6">
                <AlertTriangle size={28} />
              </div>
              <h3 className={`text-xl font-bold mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Mark as No-Show?</h3>
              <p className="text-sm text-gray-500 font-medium leading-relaxed mb-8">
                This will mark the client as a no-show for this meeting. The client will be notified and given the option to reschedule their appointment.
              </p>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => setShowNoShowConfirm(false)}
                  className={`flex-1 h-12 rounded-xl text-xs font-bold transition-all ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleNoShow}
                  disabled={submitting}
                  className="flex-1 h-12 rounded-xl bg-red-600 text-white text-xs font-bold shadow-lg shadow-red-600/20 hover:bg-red-700 transition-all disabled:opacity-50"
                >
                  {submitting ? "Processing..." : "Confirm No-Show"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function PreConsultationChat({ ticketId, isDark, userRole = "user", onReadMarked, conversationId }) {
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
      setMessages(data);
      setLoading(false);
      
      // Check if there are any unread messages from the other side
      const hasUnread = data.some(m => !m.is_read && m.sender_role !== userRole);
      if (hasUnread || shouldMarkRead) {
        await hitlService.markTicketMessagesRead(ticketId);
        if (onReadMarked) onReadMarked();
      }
    } catch (err) {
      console.error("Failed to fetch ticket messages:", err);
    }
  }, [ticketId, userRole, onReadMarked]);

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
      <div className="flex justify-center p-8">
        <Loader2 className="w-6 h-6 text-indigo-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className={`rounded-2xl border flex flex-col overflow-hidden h-[500px] ${
      isDark ? "bg-slate-900/40 border-white/5" : "bg-slate-50 border-slate-200"
    }`}>
      {/* Header */}
      <div className={`px-6 py-4 border-b flex items-center justify-between ${
        isDark ? "bg-slate-900/60 border-white/5" : "bg-slate-100 border-slate-200"
      }`}>
        <div className="flex items-center gap-2">
          <ScaleIcon size={16} className={isDark ? "text-indigo-400" : "text-indigo-600"} />
          <span className={`text-xs font-black uppercase tracking-widest ${
            isDark ? "text-slate-300" : "text-slate-700"
          }`}>
            Communication Thread
          </span>
        </div>
        {messages.some(m => !m.is_read && m.sender_role !== userRole) && (
          <span className="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black uppercase tracking-widest rounded animate-pulse">
            New
          </span>
        )}
      </div>

      {/* Message List */}
      <div className="p-6 overflow-y-auto space-y-4 flex-1 scrollbar-thin">
        {messages.length === 0 ? (
          <div className="text-center py-16">
            <MessageSquare size={32} className="mx-auto text-slate-500 opacity-30 mb-3" />
            <p className="text-xs text-slate-500 font-medium">
              No pre-consultation messages yet. Start the conversation by sending a message below.
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
                <div className="flex items-center gap-1.5 mb-1 px-1">
                  <span className="text-[10px] font-black text-slate-400">
                    {isMe ? "You" : (msg.sender_role === "lawyer" ? "Lawyer" : "👤 Client")}
                  </span>
                  <span className="text-[9px] text-slate-500 font-medium">
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-xs font-semibold leading-relaxed shadow-sm flex flex-col gap-2 ${
                  isMe
                    ? "bg-blue-600 text-white rounded-tr-none"
                    : (isDark 
                        ? "bg-slate-800 text-slate-200 border border-white/5 rounded-tl-none" 
                        : "bg-white text-slate-800 border border-slate-200 rounded-tl-none")
                }`}>
                  {hasAttachment ? (
                    <div 
                      onClick={() => handleDownload(msg.document_id, msg.file_name)}
                      className={`flex items-center gap-3 p-2.5 rounded-xl border transition-all cursor-pointer select-none ${
                        isMe
                          ? "bg-blue-700/50 border-blue-500/30 hover:bg-blue-700/70"
                          : (isDark
                              ? "bg-slate-900/60 border-white/5 hover:bg-slate-900/80"
                              : "bg-slate-100/50 border-slate-200 hover:bg-slate-100/80")
                      }`}
                    >
                      <div className={`p-1.5 rounded-lg ${
                        isMe ? "bg-blue-500/30" : "bg-blue-500/10 text-blue-500"
                      }`}>
                        <FileText size={16} className={isMe ? "text-blue-200" : "text-blue-500"} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-xs font-bold truncate max-w-[180px] ${
                          isMe ? "text-white" : (isDark ? "text-slate-200" : "text-slate-800")
                        }`}>
                          {msg.file_name || "Document"}
                        </p>
                        <p className={`text-[10px] ${
                          isMe ? "text-blue-200" : "text-slate-400"
                        }`}>
                          Click to download
                        </p>
                      </div>
                      <Download size={14} className={isMe ? "text-blue-200" : "text-slate-400"} />
                    </div>
                  ) : (
                    <div>{msg.content}</div>
                  )}
                  {hasAttachment && msg.content && !msg.content.startsWith("Sent a document:") && (
                    <div className="text-xs leading-relaxed whitespace-pre-wrap mt-1">
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
        <div className={`px-6 py-2.5 text-xs font-bold text-center border-t transition-all animate-in fade-in duration-300 ${
          isDark ? "bg-red-500/10 text-red-400 border-red-500/20" : "bg-red-50 text-red-600 border-red-100"
        }`}>
          {uploadError}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSend} className={`p-4 border-t flex gap-3 items-center ${
        isDark ? "bg-slate-900/30 border-white/5" : "bg-white border-slate-200"
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
          className={`p-2.5 rounded-xl transition-all flex items-center justify-center flex-shrink-0 ${
            isDark
              ? "bg-slate-950 border border-white/5 text-slate-400 hover:text-white hover:bg-slate-800/50"
              : "bg-slate-50 border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-100"
          }`}
          title="Attach a document (.pdf, .docx)"
        >
          {isUploading ? (
            <Loader2 size={16} className="animate-spin text-blue-500" />
          ) : (
            <Paperclip size={16} />
          )}
        </button>

        <input
          type="text"
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          placeholder="Type a message to the client..."
          disabled={sending || isUploading}
          className={`flex-1 min-w-0 px-4 py-3 rounded-xl text-xs font-medium outline-none transition-all ${
            isDark
              ? "bg-slate-950 border border-white/5 text-slate-300 focus:border-blue-500/30"
              : "bg-slate-50 border border-slate-200 text-gray-900 focus:border-blue-600/20 focus:bg-white"
          }`}
        />
        <button
          type="submit"
          disabled={!newMessage.trim() || sending || isUploading}
          className={`px-6 py-3 rounded-xl text-xs font-black uppercase tracking-widest text-white flex-shrink-0 transition-all ${
            !newMessage.trim() || sending || isUploading
              ? (isDark ? "bg-slate-800 text-slate-600" : "bg-slate-200 text-slate-400")
              : "bg-blue-600 hover:bg-blue-700 active:scale-95 shadow-md"
          }`}
        >
          {sending ? "Sending..." : "Send Message"}
        </button>
      </form>
    </div>
  );
}