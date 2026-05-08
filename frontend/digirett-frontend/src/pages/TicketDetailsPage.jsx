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

export default function TicketDetailsPage() {
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
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="h-10 w-10 animate-spin text-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <p className="text-red-500 font-bold mb-4">{error}</p>
          <button onClick={() => navigate("/lawyer")} className="text-blue-600 hover:underline">Return to Queue</button>
        </div>
      </div>
    );
  }

  const userInfo = ticket?.user_info || {};

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 px-6 py-4 sticky top-0 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button 
              onClick={() => navigate("/lawyer")}
              className="p-2 hover:bg-gray-100 rounded-full transition-colors text-gray-500"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Review Case</h1>
              <div className="flex items-center text-xs text-gray-500 mt-0.5">
                <span className="font-medium text-blue-600">Ticket #{id.slice(0, 8)}</span>
                <span className="mx-2">•</span>
                <span className="flex items-center"><Clock className="h-3 w-3 mr-1" /> Opened {new Date(ticket.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-100 uppercase tracking-wider">
              {ticket.status}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 grid lg:grid-cols-12 gap-8 overflow-hidden">
        {/* Left Col: User Info & Case Context */}
        <div className="lg:col-span-4 space-y-6 overflow-y-auto">
          {/* User Card */}
          <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-6">User Information</h2>
            <div className="space-y-5">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-2xl bg-gray-50 flex items-center justify-center text-blue-600">
                  <User className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Full Name</p>
                  <p className="font-bold text-gray-900 text-lg">{userInfo.display_name || userInfo.user_name || "N/A"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-2xl bg-gray-50 flex items-center justify-center text-blue-600">
                  <Mail className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Email Address</p>
                  <p className="font-bold text-gray-900">{userInfo.email || "N/A"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-2xl bg-gray-50 flex items-center justify-center text-blue-600">
                  <Phone className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Phone Number</p>
                  <p className="font-bold text-gray-900">{userInfo.phone_number || "Not provided"}</p>
                </div>
              </div>
              <div className="flex items-center gap-4 pt-2">
                <div className="h-12 w-12 rounded-2xl bg-gray-50 flex items-center justify-center text-blue-600">
                  <Clock className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-medium">Assigned At</p>
                  <p className="font-bold text-gray-900">{ticket.assigned_at ? new Date(ticket.assigned_at).toLocaleString() : "Pending"}</p>
                </div>
              </div>
            </div>
            <div className="mt-8 pt-8 border-t border-gray-50">
              <button className="w-full flex items-center justify-center gap-2 py-3 border border-gray-200 rounded-xl text-sm font-bold text-gray-600 hover:bg-gray-50 transition-all">
                <ExternalLink className="h-4 w-4" />
                View Full User Profile
              </button>
            </div>
          </div>

          {/* Guidelines */}
          <div className="bg-indigo-600 rounded-3xl p-6 text-white">
            <h3 className="font-bold text-lg mb-2">Lawyer Guidelines</h3>
            <ul className="text-indigo-100 text-sm space-y-3 list-disc pl-4">
              <li>Review the conversation context carefully.</li>
              <li>Provide clear, legally-grounded advice.</li>
              <li>Always cite specific sections of the law.</li>
              <li>Closing this ticket will notify the user via email.</li>
            </ul>
          </div>
        </div>

        {/* Right Col: Conversation & Response */}
        <div className="lg:col-span-8 flex flex-col gap-6 h-[calc(100vh-12rem)] min-h-[500px]">
          {/* Conversation History */}
          <div className="bg-white rounded-3xl shadow-sm border border-gray-100 flex-1 flex flex-col overflow-hidden">
            <div className="p-4 border-b border-gray-50 flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-gray-400" />
              <h2 className="font-bold text-gray-900">Conversation Context</h2>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-gray-50/30">
              {messages.length === 0 ? (
                <p className="text-center text-gray-400 py-12">No messages in this conversation.</p>
              ) : (
                messages.map((m) => (
                  <div key={m.message_id || Math.random()} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] rounded-2xl p-4 shadow-sm ${
                      m.role === 'user' 
                      ? 'bg-blue-600 text-white rounded-tr-none' 
                      : 'bg-white border border-gray-100 text-gray-800 rounded-tl-none'
                    } ${m.message_id === ticket.trigger_message_id ? 'ring-4 ring-amber-400 ring-offset-2' : ''}`}>
                      {m.message_id === ticket.trigger_message_id && (
                        <div className="flex items-center gap-1.5 mb-2 text-amber-500 font-bold text-[10px] uppercase tracking-widest">
                          <div className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"></div>
                          Escalation Trigger
                        </div>
                      )}
                      <p className={`text-[10px] font-bold uppercase tracking-wider opacity-60 mb-1 ${m.role === 'user' ? 'text-blue-100' : 'text-gray-400'}`}>
                        {m.role === 'user' ? (userInfo.display_name || 'User') : 'AI Agent'}
                      </p>
                      <div className="prose prose-sm prose-invert max-w-none">
                        <ReactMarkdown>{m.content}</ReactMarkdown>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Response Form */}
          <div className="bg-white rounded-3xl shadow-sm border border-gray-100 p-6">
            <h2 className="font-bold text-gray-900 mb-4 flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></div>
              Your Professional Response
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* File Preview */}
              {file && (
                <div className="flex items-center justify-between p-3 bg-blue-50 border border-blue-100 rounded-xl text-sm text-blue-700">
                  <span className="flex items-center gap-2">
                    <Paperclip className="h-4 w-4" />
                    {file.name}
                  </span>
                  <button 
                    type="button" 
                    onClick={() => setFile(null)}
                    className="p-1 hover:bg-blue-100 rounded-full transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}

              {uploadError && (
                <div className="p-3 bg-red-50 border border-red-100 rounded-xl text-xs text-red-600 flex items-center justify-between">
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
                  className="w-full px-4 py-3 rounded-2xl border border-gray-200 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
                  required={!file}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || submitting}
                  className="absolute bottom-4 left-4 p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
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
                  className="px-8 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-bold rounded-2xl transition-all shadow-lg shadow-blue-100 flex items-center gap-2"
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
