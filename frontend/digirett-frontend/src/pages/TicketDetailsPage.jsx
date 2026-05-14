import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
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
  Moon
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import useDocumentUpload from "../hooks/useDocumentUpload";
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
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const [currentView, setCurrentView] = useState("details");
  const [isSuccess, setIsSuccess] = useState(false);
  const fileInputRef = React.useRef(null);

  const { uploadDocument, isUploading, uploadError } = useDocumentUpload(ticket?.conversation_id);

  const fetchData = useCallback(async () => {
    try {
      const ticketData = await hitlService.getTicketDetails(id);
      setTicket(ticketData);

      const convData = await conversationService.getConversationWithMessages(ticketData.conversation_id);
      setMessages(convData.messages || []);
    } catch (err) {
      console.error("Failed to fetch details:", err);
      setError(err.message || "Unauthorized or not found");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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

  if (loading) {
    return (
      <div className={`min-h-screen flex items-center justify-center relative overflow-hidden ${isDark ? "bg-gray-950" : "bg-[#F5F7FA]"}`}>
        <BackgroundLayer theme={theme} />
        <Loader2 className="h-8 w-8 animate-spin text-blue-600 relative z-10" />
      </div>
    );
  }

  const userInfo = ticket?.user_info || {};
  const initials = (userInfo.display_name || "U").split(' ').map(n => n[0]).join('').toUpperCase();

  return (
    <div className="min-h-screen flex bg-[#F8F9FC] text-[#1E293B] font-sans">
      
      {/* 1) REFINED SIDEBAR (2nd SS Style) */}
      <aside className="w-[260px] flex-shrink-0 flex flex-col bg-[#0F172A] text-white sticky top-0 h-screen z-50">
        <div className="p-6 flex items-center gap-3 mb-2">
          <div className="h-9 w-9 rounded-xl bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-600/20">
            <ScaleIcon className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-base tracking-tight leading-none">Lawyer Panel</h1>
          </div>
        </div>

        <div className="px-3 py-4 flex-1 space-y-1">
          <p className="px-4 py-2 text-[10px] font-bold text-gray-500 uppercase tracking-widest">Main Console</p>
          
          <button 
            onClick={() => setCurrentView("details")}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${
              currentView === "details" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
            }`}
          >
            <User size={18} />
            <span className="text-xs font-semibold tracking-wide">User Details</span>
          </button>

          <button 
            onClick={() => setCurrentView("resolve")}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all group ${
              currentView === "resolve" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
            }`}
          >
            <CheckCircle2 size={18} />
            <span className="text-xs font-semibold tracking-wide">Resolve Case</span>
          </button>

          <button 
            onClick={() => setCurrentView("context")}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all group ${
              currentView === "context" ? "bg-blue-600/90 text-white shadow-lg shadow-blue-600/20" : "text-gray-400 hover:bg-white/5 hover:text-white"
            }`}
          >
            <div className="flex items-center gap-3">
              <MessageSquare size={18} />
              <span className="text-xs font-semibold tracking-wide">Context Details</span>
            </div>
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400"></div>
          </button>

          <button 
            onClick={() => navigate("/chat")}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-gray-400 hover:bg-white/5 hover:text-white"
          >
            <HistoryIcon size={18} />
            <span className="text-xs font-semibold tracking-wide">Go to Chat</span>
          </button>
        </div>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => signOut()}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-400 hover:text-white hover:bg-white/5 rounded-xl transition-all text-xs font-semibold"
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
            <span>Case Review</span>
            <ChevronRight size={12} />
            <span className="text-blue-600">User Details</span>
          </div>

          <div className="flex items-center gap-3">
            <button 
              onClick={toggleTheme}
              className={`h-9 w-9 rounded-lg border flex items-center justify-center transition-all ${
                isDark ? "bg-slate-800 border-slate-700 text-blue-400 hover:bg-slate-700" : "bg-white border-gray-100 text-gray-400 hover:text-blue-600 hover:bg-blue-50"
              }`}
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>

            <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider border ${
              isDark ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-emerald-50 text-emerald-600 border-emerald-100"
            }`}>
              <div className="h-1 w-1 rounded-full bg-emerald-500"></div>
              ASSIGNED
            </div>
            <button className={`h-9 w-9 rounded-lg border flex items-center justify-center transition-all ${
              isDark ? "bg-slate-800 border-slate-700 text-slate-400 hover:text-white" : "bg-white border-gray-100 text-gray-400 hover:text-gray-900"
            }`}>
              <MoreHorizontal size={18} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
          <div className="max-w-4xl mx-auto">
            
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
                      { icon: <Hash size={16} />, label: "Case ID", value: `#${ticket.ticket_id || id.slice(0, 8).toUpperCase()}`, valueClass: "text-blue-600" },
                      { 
                        icon: <Clock size={16} />, 
                        label: "Assigned", 
                        value: ticket.assigned_at ? `${new Date(ticket.assigned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : "Pending" 
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
                </div>
              </div>
            )}

            {/* VIEW 2: RESOLVE CASE */}
            {currentView === "resolve" && (
              <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                {isSuccess ? (
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
                      <h2 className={`text-3xl font-bold tracking-tight mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Resolve Case</h2>
                      <p className="text-gray-400 font-bold uppercase text-[9px] tracking-widest">Draft legal outcome for client</p>
                    </div>

                    <div className={`rounded-2xl border p-8 shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
                      <textarea
                        value={response}
                        onChange={(e) => setResponse(e.target.value)}
                        placeholder="Type the final resolution details here..."
                        className={`w-full min-h-[350px] p-6 rounded-xl border transition-all outline-none text-sm font-medium leading-relaxed ${
                          isDark ? "bg-slate-950 border-slate-800 text-slate-300 focus:border-blue-500/30" : "bg-gray-50 border-transparent focus:border-blue-600/20 focus:bg-white text-gray-900"
                        }`}
                      />
                      
                      <div className="flex items-center justify-between mt-6">
                        <button
                          type="button"
                          onClick={() => fileInputRef.current?.click()}
                          className={`h-11 px-4 rounded-xl border flex items-center gap-2 text-xs font-semibold transition-all ${
                            isDark ? "bg-slate-800 border-slate-700 text-slate-400 hover:text-white" : "bg-white border-gray-100 text-gray-500 hover:text-blue-600 shadow-sm"
                          }`}
                        >
                          <Paperclip size={16} />
                          Attach File
                        </button>
                        <input type="file" ref={fileInputRef} onChange={(e) => setFile(e.target.files?.[0])} className="hidden" />
                        
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
                  {messages.map((m, idx) => (
                    <div key={m.message_id || idx} className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl p-6 text-sm font-medium leading-relaxed ${
                          m.role === 'user' 
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
      </main>
    </div>
  );
}