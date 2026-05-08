import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import hitlService from "../services/hitlService";
import { Ticket, Clock, CheckCircle2, ChevronRight, Loader2, RefreshCw, Filter, User as UserIcon, Mail, Shield, Phone, ArrowLeft } from "lucide-react";
import { useUser } from "@clerk/clerk-react";
import { useTheme } from "../providers/ThemeProvider";
import BackgroundLayer from "../components/common/BackgroundLayer";
import { Link } from "react-router-dom";

export default function LawyerDashboard() {
  const { theme, isDark } = useTheme();
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();
  const { user: lawyer } = useUser();
  const [showProfileDetails, setShowProfileDetails] = useState(false);

  const fetchQueue = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const data = await hitlService.getQueue();
      setTickets(data);
    } catch (err) {
      console.error("Failed to fetch queue:", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(() => fetchQueue(), 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, []);

  const handleClaim = async (ticketId) => {
    try {
      await hitlService.claimTicket(ticketId);
      navigate(`/lawyer/tickets/${ticketId}`);
    } catch (err) {
      alert(err.message || "Failed to claim ticket");
    }
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-GB', {
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  return (
    <div className={`min-h-screen relative overflow-hidden ${isDark ? "text-white" : "text-gray-900"}`}>
      <BackgroundLayer theme={theme} />
      
      <div className="relative z-10 p-6 md:p-10">
        <div className="max-w-6xl mx-auto">
          {/* Navigation Header */}
          <div className="mb-8">
            <Link 
              to="/chat" 
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
                isDark ? "bg-gray-800/50 hover:bg-gray-700 text-gray-300" : "bg-white hover:bg-gray-50 text-gray-600 shadow-sm"
              }`}
            >
              <ArrowLeft size={18} />
              <span className="font-medium">Back to Chat</span>
            </Link>
          </div>

          <header className={`mb-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6 p-6 rounded-3xl shadow-sm border ${
            isDark ? "bg-gray-800/40 border-gray-700" : "bg-white border-gray-100"
          }`}>
            <div className="flex items-center gap-4">
              <div className={`p-3 rounded-2xl shadow-lg ${isDark ? "bg-blue-600 text-white shadow-blue-900/20" : "bg-blue-600 text-white shadow-blue-100"}`}>
                <Ticket className="h-7 w-7" />
              </div>
              <div>
                <h1 className={`text-3xl font-extrabold tracking-tight ${isDark ? "text-white" : "text-gray-900"}`}>Case Queue</h1>
                <p className={isDark ? "text-gray-400" : "text-gray-500"}>Manage legal escalations</p>
              </div>
            </div>

            <div className="flex items-center gap-6">
              <button
                onClick={() => fetchQueue(true)}
                className={`p-2.5 rounded-xl transition-all ${isDark ? "text-gray-500 hover:text-blue-400 hover:bg-gray-700" : "text-gray-400 hover:text-blue-600 hover:bg-blue-50"}`}
                disabled={refreshing}
                title="Refresh Queue"
              >
                <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
              </button>

              <div className={`h-10 w-[1px] mx-2 hidden md:block ${isDark ? "bg-gray-700" : "bg-gray-100"}`}></div>

              <div className="relative">
                <button
                  onClick={() => setShowProfileDetails(!showProfileDetails)}
                  className={`flex items-center gap-3 p-1.5 rounded-2xl transition-all border border-transparent ${
                    isDark ? "hover:bg-gray-700/50 hover:border-gray-700" : "hover:bg-gray-50 hover:border-gray-100"
                  }`}
                >
                  <div className="text-right hidden sm:block">
                    <p className={`text-sm font-bold leading-tight ${isDark ? "text-white" : "text-gray-900"}`}>
                      {lawyer?.fullName || lawyer?.firstName || "Lawyer"}
                    </p>
                  </div>
                  <div className={`h-10 w-10 rounded-full border-2 shadow-sm overflow-hidden flex items-center justify-center font-bold ${
                    isDark ? "bg-gray-700 border-gray-600 text-blue-400" : "bg-blue-50 border-white text-blue-600"
                  }`}>
                    {lawyer?.imageUrl ? (
                      <img src={lawyer.imageUrl} alt="Profile" className="h-full w-full object-cover" />
                    ) : (
                      (lawyer?.firstName || "L").charAt(0)
                    )}
                  </div>
                </button>

                {showProfileDetails && (
                  <>
                    <div className="fixed inset-0 z-20" onClick={() => setShowProfileDetails(false)}></div>
                    <div className={`absolute right-0 mt-3 w-64 rounded-3xl shadow-2xl border p-5 z-30 animate-in fade-in zoom-in duration-200 ${
                      isDark ? "bg-gray-800 border-gray-700" : "bg-white border-gray-100"
                    }`}>
                      <div className={`flex items-center gap-4 mb-4 pb-4 border-b ${isDark ? "border-gray-700" : "border-gray-50"}`}>
                        <div className={`h-12 w-12 rounded-2xl flex items-center justify-center font-bold text-lg ${
                          isDark ? "bg-gray-700 text-blue-400" : "bg-blue-50 text-blue-600"
                        }`}>
                          {(lawyer?.firstName || "L").charAt(0)}
                        </div>
                        <div className="overflow-hidden">
                          <p className={`font-bold truncate ${isDark ? "text-white" : "text-gray-900"}`}>{lawyer?.fullName || "Lawyer"}</p>
                          <p className="text-xs text-gray-400 truncate">{lawyer?.primaryEmailAddress?.emailAddress}</p>
                        </div>
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-500">Professional Role</span>
                          <span className={`font-bold px-2 py-0.5 rounded-lg text-[10px] uppercase ${
                            isDark ? "bg-blue-900/40 text-blue-400" : "bg-blue-50 text-blue-600"
                          }`}>
                            {lawyer?.publicMetadata?.role || "Lawyer"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </header>

          {loading ? (
            <div className="flex flex-col items-center justify-center py-24 text-gray-500">
              <Loader2 className="h-10 w-10 animate-spin mb-4 text-blue-500" />
              <p className="font-medium">Loading ticket queue...</p>
            </div>
          ) : (
            <div className="grid gap-6">
              <div className="flex items-center justify-between mb-2">
                <h2 className={`text-lg font-bold px-1 ${isDark ? "text-white" : "text-gray-900"}`}>Open Escalations ({tickets.length})</h2>
              </div>

              {tickets.length === 0 ? (
                <div className={`rounded-3xl p-20 text-center border-2 border-dashed ${
                  isDark ? "bg-gray-800/20 border-gray-700" : "bg-white border-gray-100"
                }`}>
                  <div className={`inline-flex items-center justify-center w-20 h-20 rounded-full mb-6 ${
                    isDark ? "bg-green-900/20 text-green-400" : "bg-green-50 text-green-500"
                  }`}>
                    <CheckCircle2 className="h-10 w-10" />
                  </div>
                  <h3 className={`text-xl font-bold mb-2 ${isDark ? "text-white" : "text-gray-900"}`}>Queue is Empty</h3>
                  <p className="text-gray-500 text-sm">All cases have been addressed. Enjoy the quiet!</p>
                </div>
              ) : (
                tickets.map((ticket) => (
                  <div
                    key={ticket.ticket_id}
                    className={`rounded-2xl border p-6 shadow-sm hover:shadow-md transition-all group flex flex-col md:flex-row md:items-center justify-between gap-6 ${
                      isDark ? "bg-gray-800/40 border-gray-700" : "bg-white border-gray-100"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      <div className={`h-12 w-12 rounded-2xl flex items-center justify-center font-bold text-xl flex-shrink-0 ${
                        isDark ? "bg-gray-700 text-blue-400" : "bg-gray-50 text-blue-600"
                      }`}>
                        {(ticket.user_info?.display_name || ticket.user_info?.user_name || ticket.user_profiles?.display_name || "U").charAt(0)}
                      </div>
                      <div>
                        <h3 className={`font-bold text-lg ${isDark ? "text-white" : "text-gray-900"}`}>{ticket.user_info?.display_name || ticket.user_info?.user_name || "Anonymous User"}</h3>
                        <div className="flex flex-wrap items-center text-sm mt-1 gap-x-4 gap-y-1">
                          <span className={`flex items-center font-medium ${isDark ? "text-blue-400" : "text-blue-600"}`}>
                            <Mail className="h-3.5 w-3.5 mr-1.5" />
                            {ticket.user_info?.email || "No email provided"}
                          </span>
                          <span className={`flex items-center ${isDark ? "text-gray-400" : "text-gray-500"}`}>
                            <Clock className="h-3.5 w-3.5 mr-1.5" />
                            {formatDate(ticket.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <div className="hidden md:block text-right mr-4">
                        <p className={`text-[10px] uppercase tracking-wider font-bold mb-1 ${isDark ? "text-gray-500" : "text-gray-400"}`}>Status</p>
                        <span className={`inline-flex items-center px-3 py-1 rounded-full text-[10px] font-bold border ${
                          isDark ? "bg-amber-900/30 text-amber-400 border-amber-800" : "bg-amber-50 text-amber-600 border-amber-100"
                        }`}>
                          {ticket.status.toUpperCase()}
                        </span>
                      </div>
                      <button
                        onClick={() => handleClaim(ticket.ticket_id)}
                        className={`px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl transition-all shadow-lg flex items-center gap-2 group-hover:scale-105 ${
                          isDark ? "shadow-blue-900/20" : "shadow-blue-100"
                        }`}
                      >
                        <span>Claim Ticket</span>
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
