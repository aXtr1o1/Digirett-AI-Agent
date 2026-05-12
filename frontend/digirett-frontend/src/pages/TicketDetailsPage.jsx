import React, { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import hitlService from "../services/hitlService";
import conversationService from "../services/conversationService";
import {
  ArrowLeft,
  User,
  Mail,
  Phone,
  MessageSquare,
  Send,
  Loader2,
  CheckCircle,
  Clock,
  ExternalLink,
  Paperclip,
  X
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import useDocumentUpload from "../hooks/useDocumentUpload";
import { useTheme } from "../providers/ThemeProvider";
import BackgroundLayer from "../components/common/BackgroundLayer";

export default function TicketDetailsPage() {
  const { theme, isDark } = useTheme();
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [messages, setMessages] = useState([]);
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [file, setFile] = useState(null);
  const fileInputRef = React.useRef(null);

  const { uploadDocument, isUploading, uploadError, clearUploadError } = useDocumentUpload(ticket?.conversation_id);

  const fetchData = useCallback(async () => {
    try {
      const ticketData = await hitlService.getTicketDetails(id);
      setTicket(ticketData);

      // Fetch the conversation history
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
      alert("Response submitted and ticket resolved.");
      navigate("/lawyer");
    } catch (err) {
      alert(err.message || "Failed to submit response");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className={`min-h-screen flex items-center justify-center relative overflow-hidden ${isDark ? "bg-gray-950" : "bg-gray-50"}`}>
        <BackgroundLayer theme={theme} />
        <Loader2 className="h-10 w-10 animate-spin text-blue-600 relative z-10" />
      </div>
    );
  }

  if (error) {
    return (
      <div className={`min-h-screen flex items-center justify-center relative overflow-hidden ${isDark ? "bg-gray-950" : "bg-gray-50"}`}>
        <BackgroundLayer theme={theme} />
        <div className="text-center relative z-10">
          <p className="text-red-500 font-bold mb-4">{error}</p>
          <button onClick={() => navigate("/lawyer")} className="text-blue-600 hover:underline">Return to Queue</button>
        </div>
      </div>
    );
  }

  const userInfo = ticket?.user_info || {};

  return (
    <div className={`min-h-screen flex flex-col relative overflow-hidden ${isDark ? "bg-gray-950 text-white" : "bg-gray-50 text-gray-900"}`}>
      <BackgroundLayer theme={theme} />
      {/* Header */}
      <header className={`px-6 py-4 sticky top-0 z-20 border-b shadow-sm backdrop-blur-md ${isDark ? "bg-gray-900/80 border-gray-800" : "bg-white/80 border-gray-100"
        }`}>
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/lawyer")}
              className={`p-2 rounded-full transition-colors ${isDark ? "hover:bg-gray-800 text-gray-400" : "hover:bg-gray-100 text-gray-500"
                }`}
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className={`text-xl font-bold ${isDark ? "text-white" : "text-gray-900"}`}>Review Case</h1>
              <div className="flex items-center text-xs text-gray-500 mt-0.5">
                <span className={`font-medium ${isDark ? "text-blue-400" : "text-blue-600"}`}>Ticket #{id.slice(0, 8)}</span>
                <span className="mx-2">•</span>
                <span className="flex items-center"><Clock className="h-3 w-3 mr-1" /> Opened {new Date(ticket.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider border ${isDark ? "bg-blue-900/30 text-blue-400 border-blue-800" : "bg-blue-50 text-blue-700 border-blue-100"
              }`}>
              {ticket.status}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 grid lg:grid-cols-12 gap-8 overflow-hidden relative z-10">
        {/* Left Col: User Info & Case Context */}
        <div className="lg:col-span-4 space-y-6 overflow-y-auto pr-2 custom-scrollbar">
          {/* User Card */}
          <div className={`rounded-3xl shadow-sm border p-6 ${isDark ? "bg-gray-900/40 border-gray-800" : "bg-white border-gray-100"
            }`}>
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-6">User Information</h2>
            <div className="space-y-5">
              <div className="flex items-center gap-4">
                <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${isDark ? "bg-gray-800 text-blue-400" : "bg-gray-50 text-blue-600"
                  }`}>
                  <User className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Full Name</p>
                  <p className={`font-bold text-lg ${isDark ? "text-white" : "text-gray-900"}`}>{userInfo.display_name || userInfo.user_name || "N/A"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${isDark ? "bg-gray-800 text-blue-400" : "bg-gray-50 text-blue-600"
                  }`}>
                  <Mail className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Email Address</p>
                  <p className={`font-bold ${isDark ? "text-white" : "text-gray-900"}`}>{userInfo.email || "N/A"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${isDark ? "bg-gray-800 text-blue-400" : "bg-gray-50 text-blue-600"
                  }`}>
                  <Phone className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Phone Number</p>
                  <p className={`font-bold ${isDark ? "text-white" : "text-gray-900"}`}>{userInfo.phone_number || "Not provided"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4 pt-2">
                <div className={`h-12 w-12 rounded-2xl flex items-center justify-center ${isDark ? "bg-gray-800 text-blue-400" : "bg-gray-50 text-blue-600"
                  }`}>
                  <Clock className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Assigned At</p>
                  <p className={`font-bold ${isDark ? "text-white" : "text-gray-900"}`}>{ticket.assigned_at ? new Date(ticket.assigned_at).toLocaleString() : "Pending"}</p>
                </div>
              </div>
            </div>
            <div className={`mt-8 pt-8 border-t ${isDark ? "border-gray-800" : "border-gray-50"}`}>
              <button className={`w-full flex items-center justify-center gap-2 py-3 border rounded-xl text-sm font-bold transition-all ${isDark ? "border-gray-700 text-gray-300 hover:bg-gray-800" : "border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}>
                <ExternalLink className="h-4 w-4" />
                View Full User Profile
              </button>
            </div>
          </div>

          {/* Guidelines */}
          <div className={`rounded-3xl p-6 text-white shadow-xl ${isDark ? "bg-blue-600/80 backdrop-blur-md" : "bg-blue-600"}`}>
            <h3 className="font-bold text-lg mb-2">Lawyer Guidelines</h3>
            <ul className="text-blue-100 text-sm space-y-3 list-disc pl-4">
              <li>Review the conversation context carefully.</li>
              <li>Provide clear, legally-grounded advice.</li>
              <li>Always cite specific sections of the law.</li>
              <li>Closing this ticket will notify the user via email.</li>
            </ul>
          </div>
        </div>

        {/* Right Col: Conversation & Response */}
        <div className="lg:col-span-8 flex flex-col gap-6 h-full min-h-[500px]">
          {/* Conversation History */}
          <div className={`rounded-3xl shadow-sm border flex-1 flex flex-col overflow-hidden ${isDark ? "bg-gray-900/40 border-gray-800" : "bg-white border-gray-100"
            }`}>
            <div className={`p-4 border-b flex items-center gap-2 ${isDark ? "border-gray-800 bg-gray-800/50" : "border-gray-50 bg-white"}`}>
              <MessageSquare className="h-5 w-5 text-gray-400" />
              <h2 className={`font-bold ${isDark ? "text-white" : "text-gray-900"}`}>Conversation Context</h2>
            </div>
            <div className={`flex-1 overflow-y-auto p-6 space-y-6 ${isDark ? "bg-gray-950/20" : "bg-gray-50/30"}`}>
              {messages.length === 0 ? (
                <p className="text-center text-gray-400 py-12">No messages in this conversation.</p>
              ) : (
                messages.map((m) => (
                  <div key={m.message_id || Math.random()} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-2xl p-4 shadow-sm ${m.role === 'user'
                        ? (isDark ? 'bg-blue-600 text-white rounded-tr-none' : 'bg-blue-600 text-white rounded-tr-none')
                        : (isDark ? 'bg-gray-800 border border-gray-700 text-gray-100 rounded-tl-none' : 'bg-white border border-gray-100 text-gray-800 rounded-tl-none')
                      } ${m.message_id === ticket.trigger_message_id ? 'ring-4 ring-amber-400 ring-offset-2' : ''}`}>
                      {m.message_id === ticket.trigger_message_id && (
                        <div className="flex items-center gap-1.5 mb-2 text-amber-500 font-bold text-[10px] uppercase tracking-widest">
                          <div className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"></div>
                          Escalation Trigger
                        </div>
                      )}
                      <p className={`text-[10px] font-bold uppercase tracking-wider opacity-60 mb-1 ${m.role === 'user' ? 'text-blue-100' : (isDark ? 'text-gray-400' : 'text-gray-400')}`}>
                        {m.role === 'user' ? (userInfo.display_name || 'User') : (m.metadata?.is_lawyer ? "Personal Lawyer" : "AI Agent")}
                      </p>
                      <div className={`prose prose-sm max-w-none ${m.role === 'user' || isDark ? 'prose-invert' : ''}`}>
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Response Form */}
          <div className={`rounded-3xl shadow-sm border p-6 ${isDark ? "bg-gray-900/40 border-gray-800" : "bg-white border-gray-100"
            }`}>
            <h2 className={`font-bold mb-4 flex items-center gap-2 ${isDark ? "text-white" : "text-gray-900"}`}>
              <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></div>
              Your Professional Response
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* File Preview */}
              {file && (
                <div className={`flex items-center justify-between p-3 border rounded-xl text-sm ${isDark ? "bg-blue-900/20 border-blue-800 text-blue-400" : "bg-blue-50 border-blue-100 text-blue-700"
                  }`}>
                  <span className="flex items-center gap-2">
                    <Paperclip className="h-4 w-4" />
                    {file.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => setFile(null)}
                    className={`p-1 rounded-full transition-colors ${isDark ? "hover:bg-blue-900/40" : "hover:bg-blue-100"}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}

              {uploadError && (
                <div className="p-3 bg-red-50/10 border border-red-500/20 rounded-xl text-xs text-red-500 flex items-center justify-between">
                  {uploadError}
                  <button type="button" onClick={clearUploadError}><X className="h-3 w-3" /></button>
                </div>
              )}

              <div className="relative">
                <textarea
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  placeholder="Enter your legal advice here..."
                  rows={5}
                  className={`w-full px-4 py-3 rounded-2xl border outline-none transition-all resize-none ${isDark
                      ? "bg-gray-800/50 border-gray-700 text-white focus:ring-2 focus:ring-blue-500/50"
                      : "bg-white border-gray-200 focus:ring-2 focus:ring-blue-500"
                    }`}
                  required={!file}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || submitting}
                  className={`absolute bottom-4 left-4 p-2 rounded-lg transition-all ${isDark ? "text-gray-500 hover:text-blue-400 hover:bg-gray-700" : "text-gray-400 hover:text-blue-600 hover:bg-blue-50"
                    }`}
                  title="Attach a document"
                >
                  <Paperclip className="h-5 w-5" />
                </button>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={(e) => setFile(e.target.files?.[0])}
                  className="hidden"
                  accept=".pdf,.doc,.docx"
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={submitting || isUploading || (!response.trim() && !file)}
                  className={`px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-bold rounded-2xl transition-all shadow-lg flex items-center gap-2 ${isDark ? "shadow-blue-900/20" : "shadow-blue-100"
                    }`}
                >
                  {submitting || isUploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                  <span>{isUploading ? "Uploading Document..." : "Resolve & Notify User"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
