import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import hitlService from "../services/hitlService";
import { Ticket, Clock, CheckCircle2, ChevronRight, Loader2, RefreshCw, Filter, User as UserIcon, Mail, Shield } from "lucide-react";
import { useUser } from "@clerk/clerk-react";

export default function LawyerDashboard() {
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
    <div className="min-h-screen bg-gray-50 p-6 md:p-10">
      <div className="max-w-6xl mx-auto">
        <header className="mb-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6 bg-white p-6 rounded-3xl shadow-sm border border-gray-100">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-600 rounded-2xl text-white shadow-lg shadow-blue-100">
              <Ticket className="h-7 w-7" />
            </div>
            <div>
              <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Case Queue</h1>
              <p className="text-gray-500 text-sm mt-0.5">Manage legal escalations</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <button 
              onClick={() => fetchQueue(true)}
              className="p-2.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-xl transition-all"
              disabled={refreshing}
              title="Refresh Queue"
            >
              <RefreshCw className={`h-5 w-5 ${refreshing ? 'animate-spin' : ''}`} />
            </button>

            <div className="h-10 w-[1px] bg-gray-100 mx-2 hidden md:block"></div>

            {/* Top-Right Profile Section */}
            <div className="relative">
              <button 
                onClick={() => setShowProfileDetails(!showProfileDetails)}
                className="flex items-center gap-3 hover:bg-gray-50 p-1.5 rounded-2xl transition-all border border-transparent hover:border-gray-100"
              >
                <div className="text-right hidden sm:block">
                  <p className="text-sm font-bold text-gray-900 leading-tight">
                    {lawyer?.fullName || lawyer?.firstName || "Lawyer"}
                  </p>
                </div>
                <div className="h-10 w-10 rounded-full bg-blue-50 border-2 border-white shadow-sm overflow-hidden flex items-center justify-center text-blue-600 font-bold">
                  {lawyer?.imageUrl ? (
                    <img src={lawyer.imageUrl} alt="Profile" className="h-full w-full object-cover" />
                  ) : (
                    (lawyer?.firstName || "L").charAt(0)
                  )}
                </div>
              </button>

              {/* Profile Dropdown */}
              {showProfileDetails && (
                <>
                  <div 
                    className="fixed inset-0 z-20" 
                    onClick={() => setShowProfileDetails(false)}
                  ></div>
                  <div className="absolute right-0 mt-3 w-64 bg-white rounded-3xl shadow-2xl border border-gray-100 p-5 z-30 animate-in fade-in zoom-in duration-200">
                    <div className="flex items-center gap-4 mb-4 pb-4 border-b border-gray-50">
                      <div className="h-12 w-12 rounded-2xl bg-blue-50 flex items-center justify-center text-blue-600 font-bold text-lg">
                        {(lawyer?.firstName || "L").charAt(0)}
                      </div>
                      <div className="overflow-hidden">
                        <p className="font-bold text-gray-900 truncate">{lawyer?.fullName || "Lawyer"}</p>
                        <p className="text-xs text-gray-400 truncate">{lawyer?.primaryEmailAddress?.emailAddress}</p>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-400">Professional Role</span>
                        <span className="font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded-lg text-[10px] uppercase">
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
          <div className="flex flex-col items-center justify-center py-24 text-gray-400">
            <Loader2 className="h-10 w-10 animate-spin mb-4" />
            <p className="font-medium">Loading ticket queue...</p>
          </div>
        ) : (
          <div className="grid gap-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-bold text-gray-900 px-1">Open Escalations ({tickets.length})</h2>
            </div>

            {tickets.length === 0 ? (
              <div className="bg-white rounded-3xl p-20 text-center border-2 border-dashed border-gray-100">
                <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-green-50 mb-6">
                  <CheckCircle2 className="h-10 w-10 text-green-500" />
                </div>
                <h3 className="text-xl font-bold text-gray-900 mb-2">Queue is Empty</h3>
                <p className="text-gray-500">All cases have been addressed. Enjoy the quiet!</p>
              </div>
            ) : (
              tickets.map((ticket) => (
                <div 
                  key={ticket.ticket_id}
                  className="bg-white rounded-2xl border border-gray-100 p-6 shadow-sm hover:shadow-md transition-all group flex flex-col md:flex-row md:items-center justify-between gap-6"
                >
                  <div className="flex items-start gap-4">
                    <div className="h-12 w-12 rounded-2xl bg-gray-50 flex items-center justify-center text-blue-600 font-bold text-xl flex-shrink-0">
                      {(ticket.user_info?.display_name || ticket.user_info?.user_name || ticket.user_profiles?.display_name || "U").charAt(0)}
                    </div>
                    <div>
                      <h3 className="font-bold text-gray-900 text-lg">{ticket.user_info?.display_name || ticket.user_info?.user_name || ticket.user_profiles?.display_name || "Anonymous User"}</h3>
                      <div className="flex items-center text-sm text-gray-500 mt-1 space-x-3">
                        <span className="flex items-center">
                          <Clock className="h-3.5 w-3.5 mr-1" />
                          {formatDate(ticket.created_at)}
                        </span>
                        <span className="w-1 h-1 rounded-full bg-gray-300"></span>
                        <span className="font-medium text-blue-600">ID: ...{ticket.ticket_id.slice(-6)}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div className="hidden md:block text-right mr-4">
                      <p className="text-xs uppercase tracking-wider font-bold text-gray-400 mb-1">Status</p>
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-600 border border-amber-100">
                        {ticket.status.toUpperCase()}
                      </span>
                    </div>
                    <button
                      onClick={() => handleClaim(ticket.ticket_id)}
                      className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-xl transition-all shadow-lg shadow-blue-100 flex items-center gap-2 group-hover:scale-105"
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
  );
}
