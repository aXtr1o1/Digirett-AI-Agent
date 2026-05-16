import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import hitlService from "../services/hitlService";
import { useUser, useClerk } from "@clerk/clerk-react";
import {
  Ticket,
  Clock,
  CheckCircle2,
  ChevronRight,
  Loader2,
  RefreshCw,
  Mail,
  ArrowLeft,
  LogOut,
  Shield,
  ArrowUpCircle,
  LayoutDashboard,
  Inbox,
  Settings,
  Menu,
  X,
  User,
  ExternalLink,
  Search,
  Bell,
  CheckCircle,
  AlertTriangle,
  Scale,
  FileText,
  Bookmark,
  Briefcase,
  Layers,
  MoreVertical,
  Activity,
  ClipboardList,
  Sun,
  Moon,
  UserX
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area
} from 'recharts';
import { useTheme } from "../providers/ThemeProvider";
import { Link } from "react-router-dom";
import SystemNotification from "../components/chat/ResolutionNotification";

export default function LawyerDashboard() {
  const { theme, isDark, toggleTheme } = useTheme();
  const [queueTickets, setQueueTickets] = useState([]);
  const [resolvedTickets, setResolvedTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeView = searchParams.get("view") || "dashboard";
  const setActiveView = (view) => setSearchParams({ view });
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [showProfileDropdown, setShowProfileDropdown] = useState(false);
  const [queueMsg, setQueueMsg] = useState(null);
  const [notes, setNotes] = useState("");

  // Intake and Pending Matters
  const [activeTickets, setActiveTickets] = useState([]);
  const [intakeTicket, setIntakeTicket] = useState(null);
  const [pendingTickets, setPendingTickets] = useState([]);
  const [showNoShowConfirm, setShowNoShowConfirm] = useState(false);
  const [noShowTicketId, setNoShowTicketId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [claimError, setClaimError] = useState(null);

  const navigate = useNavigate();
  const { user: clerkUser } = useUser();
  const { signOut, openUserProfile } = useClerk();

  const handleLogout = async () => {
    await signOut();
    navigate("/sign-in");
  };

  const [globalError, setGlobalError] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [dismissedEvents, setDismissedEvents] = useState(() => {
    const seen = localStorage.getItem("dismissed_lawyer_events");
    return seen ? JSON.parse(seen) : [];
  });

  // Monitor for new cases in the queue
  const checkQueueStatus = useCallback(async () => {
    try {
      const savedDismissed = localStorage.getItem("dismissed_lawyer_events");
      const currentDismissed = savedDismissed ? JSON.parse(savedDismissed) : [];

      console.log("[LawyerDashboard] Checking queue for notifications...");
      const queueData = await hitlService.getQueue();

      if (!Array.isArray(queueData)) {
        console.warn("[LawyerDashboard] Queue data is not an array:", queueData);
        return;
      }

      console.log(`[LawyerDashboard] Found ${queueData.length} items in queue.`);

      const newNotifications = [];
      queueData.forEach(ticket => {
        const ticketId = ticket.ticket_id || ticket.id;
        const eventId = `new_case_${ticketId}`;

        if (!currentDismissed.includes(eventId)) {
          newNotifications.push({
            id: eventId,
            type: 'new_case',
            caseRef: ticketId,
            message: `New Incoming Matter: A legal consultation has been requested and is waiting in your queue.`,
            view: 'queue'
          });
        }
      });

      console.log(`[LawyerDashboard] Showing ${newNotifications.length} new notifications.`);
      setNotifications(newNotifications);
    } catch (err) {
      console.error("[LawyerDashboard] Error checking queue:", err);
    }
  }, []);

  const handleDismissNotification = useCallback((notifId) => {
    setDismissedEvents(prev => {
      const updated = [...prev, notifId];
      localStorage.setItem("dismissed_lawyer_events", JSON.stringify(updated));
      return updated;
    });
    setNotifications(prev => prev.filter(n => n.id !== notifId));
  }, []);

  const fetchData = async (isManual = false) => {
    if (isManual) setRefreshing(true);
    setGlobalError(null);
    try {
      const [queueData, resolvedData, activeData] = await Promise.all([
        hitlService.getQueue(),
        hitlService.getResolvedHistory(),
        hitlService.getActiveTickets()
      ]);
      setQueueTickets(queueData || []);
      setResolvedTickets(resolvedData || []);
      setActiveTickets(activeData || []);

    } catch (err) {
      console.error("Dashboard fetch error:", err);
      setGlobalError(err.message || "Failed to load dashboard data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    checkQueueStatus();
    const dataInterval = setInterval(fetchData, 30000);
    const notifInterval = setInterval(checkQueueStatus, 30000);
    return () => {
      clearInterval(dataInterval);
      clearInterval(notifInterval);
    };
  }, [checkQueueStatus]);

  // Logic to determine Intake vs Pending with persistence
  useEffect(() => {
    if (activeTickets && activeTickets.length > 0) {
      const savedIntakeId = localStorage.getItem("lawyer_current_intake_id");
      let intake = activeTickets.find(t => t.ticket_id === savedIntakeId);

      if (!intake) {
        // If the saved intake is gone (resolved), pick the first one as new intake
        intake = activeTickets[0];
        localStorage.setItem("lawyer_current_intake_id", intake.ticket_id);
      }

      setIntakeTicket(intake);
      setPendingTickets(activeTickets.filter(t => t.ticket_id !== intake.ticket_id));
    } else {
      setIntakeTicket(null);
      setPendingTickets([]);
      localStorage.removeItem("lawyer_current_intake_id");
    }
  }, [activeTickets]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => fetchData(), 30000);
    return () => clearInterval(interval);
  }, []);

  const handleClaim = async (ticketId) => {
    try {
      await hitlService.claimTicket(ticketId);

      // Persistence logic: Only set as intake if nothing is currently being worked on
      const currentIntakeId = localStorage.getItem("lawyer_current_intake_id");
      if (!currentIntakeId) {
        localStorage.setItem("lawyer_current_intake_id", ticketId);
        setQueueMsg({ type: "success", text: "You claimed this matter! It is now in your Intake." });
        setActiveView("intake");
      } else {
        setQueueMsg({ type: "success", text: "You claimed this matter! It is now in your Pending list." });
        setActiveView("pending");
      }

      await fetchData();
    } catch (err) {
      console.error("[LawyerDashboard] Claim failed:", err);
      const isConflict = err.status === 409 ||
        (err.message || "").toLowerCase().includes("already claimed") ||
        (err.message || "").toLowerCase().includes("conflict");

      if (isConflict) {
        setClaimError({
          title: "Already Claimed",
          message: "Another lawyer claimed this matter just a moment ago. The queue has been updated to reflect current availability.",
          ticketId: ticketId
        });
        setQueueMsg(null);
        await fetchData();
      } else {
        setQueueMsg({ type: "error", text: err.message || "Failed to claim ticket" });
      }
    }
  };

  const handleWorkOn = (ticketId) => {
    localStorage.setItem("lawyer_current_intake_id", ticketId);
    // Recalculate view based on currently fetched activeTickets
    const intake = activeTickets.find(t => t.ticket_id === ticketId);
    if (intake) {
      setIntakeTicket(intake);
      setPendingTickets(activeTickets.filter(t => t.ticket_id !== ticketId));
      setActiveView("intake");
    }
  };

  const handleMarkNoShow = async () => {
    if (!noShowTicketId) return;
    setIsProcessing(true);
    try {
      await hitlService.markNoShow(noShowTicketId, "User did not attend the scheduled meeting.");
      setQueueMsg({ type: "success", text: "Matter marked as No-Show and archived." });
      setShowNoShowConfirm(false);
      setNoShowTicketId(null);
      await fetchData();
    } catch (err) {
      setQueueMsg({ type: "error", text: err.message || "Failed to mark as no-show" });
    } finally {
      setIsProcessing(false);
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

  const recentResolved = resolvedTickets.slice(0, 5);

  // Dynamic Data Calculations - No more fake values
  const allTickets = [...queueTickets, ...activeTickets, ...resolvedTickets];

  const allocationData = [
    { name: 'Available', value: queueTickets.length, color: '#6366f1' },
    { name: 'Resolved', value: resolvedTickets.length, color: '#10b981' }
  ];

  // Group by date for Intake Performance
  const getIntakeTrend = () => {
    const counts = {};
    allTickets.forEach(t => {
      const sortKey = new Date(t.created_at).toISOString().split('T')[0];
      counts[sortKey] = (counts[sortKey] || 0) + 1;
    });

    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const sKey = d.toISOString().split('T')[0];
      result.push({
        sortKey: sKey,
        count: counts[sKey] || 0,
        date: d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' })
      });
    }
    return result;
  };

  const resolutionTrend = getIntakeTrend();

  const activeVelocityData = resolutionTrend.map(d => ({
    ...d,
    active: activeTickets.length // Simplified for real-time overview
  })); const stats = [
    { label: "Resolved", value: resolvedTickets.length, icon: CheckCircle2, color: "emerald" },
    { label: "Active Matters", value: activeTickets.length, icon: Activity, color: "blue" },
    { label: "Queue Load", value: queueTickets.length, icon: Ticket, color: "indigo" },
    { label: "Pending Review", value: activeTickets.length, icon: Clock, color: "amber" }
  ];

  return (
    <div className={`flex h-screen overflow-hidden ${isDark ? "bg-[#020617] text-slate-200" : "bg-[#f1f5f9] text-slate-900"}`}>

      {/* SIDEBAR */}
      <aside className={`fixed lg:relative z-50 inset-y-0 left-0 w-64 transform transition-transform duration-300 ease-in-out border-r ${isDark ? "bg-slate-900 border-slate-800" : "bg-[#0f172a] border-slate-800"
        } ${isSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>

        <div className="flex flex-col h-full">
          {/* Sidebar Header */}
          <div className="h-16 flex items-center px-6 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center">
                <img src="/digirett-logo.png" alt="Logo" className="w-full h-full object-contain p-0.5" />
              </div>
              <h1 className="text-sm font-bold tracking-tight text-white uppercase italic tracking-tighter">Lawyer Panel</h1>
            </div>
            <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden ml-auto text-slate-400">
              <X size={18} />
            </button>
          </div>

          {/* Navigation Sections */}
          <div className="flex-1 px-3 py-6 space-y-8 overflow-y-auto">
            <div>
              <p className="px-4 text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4 opacity-50 font-bold">Main Console</p>
              <nav className="space-y-1">
                <button
                  onClick={() => { setActiveView("dashboard"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "dashboard" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <LayoutDashboard size={16} />
                  Dashboard
                </button>
                <button
                  onClick={() => { setActiveView("queue"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "queue" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <ClipboardList size={16} />
                  Matter Queue
                  <span className="ml-auto bg-white/10 text-white px-1.5 py-0.5 rounded text-[10px]">{queueTickets.length}</span>
                </button>
              </nav>
            </div>

            <div>
              <p className="px-4 text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4 opacity-50 font-bold">Claimed Matters</p>
              <nav className="space-y-1">
                <button
                  onClick={() => { setActiveView("intake"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "intake" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <Inbox size={16} />
                  My Intake
                  {intakeTicket && <span className="ml-auto bg-emerald-500 w-2 h-2 rounded-full"></span>}
                </button>
                <button
                  onClick={() => { setActiveView("pending"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "pending" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <Layers size={16} />
                  Pending Matters
                  {pendingTickets.length > 0 && <span className="ml-auto bg-white/10 text-white px-1.5 py-0.5 rounded text-[10px]">{pendingTickets.length}</span>}
                </button>
              </nav>
            </div>

            <div>
              <p className="px-4 text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4 opacity-50 font-bold">My Workspace</p>
              <nav className="space-y-1">
                <button
                  onClick={() => { setActiveView("resolved"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "resolved" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <CheckCircle size={16} />
                  Resolved History
                  <span className="ml-auto text-slate-500 text-[10px]">{resolvedTickets.length}</span>
                </button>
                <button
                  onClick={() => { setActiveView("notes"); setIsSidebarOpen(false); }}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold transition-all ${activeView === "notes" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                    }`}
                >
                  <Bookmark size={16} />
                  Notes
                </button>
                <Link
                  to="/chat"
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white hover:bg-white/5 transition-all"
                >
                  <ArrowLeft size={16} />
                  Go to Chat
                </Link>
                {clerkUser?.publicMetadata?.role === "admin" && (
                  <Link
                    to="/admin"
                    className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/5 transition-all border border-indigo-500/20 mt-4"
                  >
                    <Shield size={16} />
                    Admin Dashboard
                  </Link>
                )}
              </nav>
            </div>
          </div>

          {/* Sidebar Footer */}
          <div className="mt-auto border-t border-white/5 p-3">
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-bold text-slate-400 hover:text-red-400 hover:bg-red-500/5 transition-all"
            >
              <LogOut size={16} />
              Logout
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <div className="flex-1 flex flex-col min-w-0 relative h-full">
        {/* Header */}
        <header className={`px-6 py-4 sticky top-0 z-40 border-b shadow-sm backdrop-blur-md ${isDark ? "bg-gray-900/80 border-gray-800" : "bg-white/80 border-gray-100"
          }`}>
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden text-slate-500 p-2 hover:bg-slate-100 rounded-xl">
                <Menu size={24} />
              </button>
              <div className="flex items-center gap-3">
                <div className={`p-1 rounded-2xl overflow-hidden ${isDark ? "bg-white/90" : "bg-white border"}`}>
                  <img src="/digirett-logo.png" alt="Logo" className="h-9 w-9 object-contain" />
                </div>
                <div>
                  <h1 className={`text-lg font-black tracking-widest uppercase ${isDark ? "text-white" : "text-gray-900"}`}>
                    Lawyer Dashboard
                  </h1>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <button
                onClick={() => fetchData(true)}
                className={`p-2 rounded-xl transition-all ${isDark ? "bg-gray-800 text-gray-400 hover:bg-gray-700" : "bg-gray-50 text-gray-500 hover:bg-gray-100"}`}
                title="Refresh Global Data"
              >
                <RefreshCw size={18} className={refreshing ? 'animate-spin' : ''} />
              </button>
              <button
                onClick={toggleTheme}
                className={`p-2 rounded-xl transition-all ${isDark ? "bg-gray-800 text-blue-400 hover:bg-gray-700" : "bg-gray-50 text-gray-500 hover:bg-gray-100"}`}
              >
                {isDark ? <Sun size={18} /> : <Moon size={18} />}
              </button>
              <div className="h-8 w-[1px] bg-gray-200 dark:bg-gray-800 mx-1"></div>
              <div className="relative">
                <button
                  onClick={() => setShowProfileDropdown(!showProfileDropdown)}
                  className={`flex items-center gap-2 p-1.5 rounded-2xl transition-all ${isDark ? "hover:bg-gray-800" : "hover:bg-gray-50"}`}
                >
                  <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold">
                    {clerkUser?.firstName?.charAt(0) || "L"}
                  </div>
                  <div className="hidden md:block text-left">
                    <p className={`text-xs font-bold ${isDark ? "text-white" : "text-gray-900"}`}>{clerkUser?.fullName || "Lawyer"}</p>
                    <p className="text-[10px] text-gray-500">Professional ID: 8829</p>
                  </div>
                </button>

                {showProfileDropdown && (
                  <div className={`absolute top-full right-0 mt-2 w-52 rounded-xl border shadow-2xl z-[100] overflow-hidden animate-in fade-in zoom-in-95 duration-200 ${isDark ? "bg-slate-900 border-slate-800 shadow-black/40" : "bg-white border-slate-200"
                    }`}>
                    <div className="p-2 space-y-1">
                      <button
                        onClick={() => { openUserProfile(); setShowProfileDropdown(false); }}
                        className={`w-full px-3 py-2 flex items-center gap-3 rounded-lg text-xs font-bold transition-colors ${isDark ? "text-slate-300 hover:bg-slate-800" : "text-slate-600 hover:bg-slate-50"
                          }`}
                      >
                        <User size={14} />
                        Profile
                      </button>
                      <button
                        onClick={handleLogout}
                        className={`w-full px-3 py-2 flex items-center gap-3 rounded-lg text-xs font-bold transition-colors ${isDark ? "text-red-400 hover:bg-red-500/10" : "text-red-600 hover:bg-red-50"
                          }`}
                      >
                        <LogOut size={14} />
                        Log out
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {globalError && (
          <div className="max-w-7xl mx-auto px-6 mt-6">
            <div className={`p-4 rounded-2xl flex items-center justify-between border ${isDark ? "bg-red-900/20 border-red-800 text-red-400" : "bg-red-50 border-red-100 text-red-700"
              }`}>
              <div className="flex items-center gap-3">
                <AlertTriangle className="h-5 w-5" />
                <p className="font-bold">{globalError}</p>
              </div>
              {globalError.includes("login") && (
                <button
                  onClick={() => navigate("/sign-in")}
                  className="px-4 py-2 bg-red-600 text-white rounded-xl text-sm font-bold hover:bg-red-700 transition-all"
                >
                  Sign In Now
                </button>
              )}
            </div>
          </div>
        )}

        {/* Content Section */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8">

          {/* VIEW: DASHBOARD */}
          {activeView === "dashboard" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-10">

              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-black tracking-tight">Lawyer Control Panel</h1>
                  <p className="text-xs text-slate-500 mt-1 font-medium">Real-time oversight of escalated legal matters.</p>
                </div>
              </div>

              {/* KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
                {stats.map((stat, idx) => (
                  <div key={idx} className={`p-6 rounded-2xl border shadow-sm flex flex-col gap-2 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
                    }`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">{stat.label}</span>
                      <stat.icon size={14} className="text-slate-300" />
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-black tracking-tighter">{stat.value}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Row 1: Allocation + Trend */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {/* Allocation */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-6">Matter Allocation</h3>
                  <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={allocationData} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                          {allocationData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                        <Legend iconType="circle" />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Intake Trend */}
                <div className={`xl:col-span-1 p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-6">Intake Performance</h3>
                  <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={resolutionTrend}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                        <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} />
                        <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: '#64748b' }} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: isDark ? '#0f172a' : '#fff',
                            border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                            borderRadius: '8px',
                            fontSize: '10px'
                          }}
                        />
                        <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={30} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Row 2: Reserved for future metrics or activity feed */}
            </div>
          )}

          {/* VIEW: CASE QUEUE (ALL OPEN CASES) */}
          {activeView === "queue" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className={`px-8 py-5 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                  <h2 className="text-base font-bold">Matter Queue</h2>
                  <p className="text-xs text-slate-500 mt-1">Shared pool of open legal escalations waiting for assignment.</p>
                </div>

                {queueMsg && (
                  <div className={`mx-8 mt-6 p-4 rounded-xl flex items-center justify-between text-sm font-bold animate-in fade-in zoom-in-95 ${queueMsg.type === 'success'
                    ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                    : 'bg-red-500/10 text-red-500 border border-red-500/20'
                    }`}>
                    <div className="flex items-center gap-3">
                      {queueMsg.type === 'success' ? <CheckCircle size={18} /> : <AlertTriangle size={18} />}
                      {queueMsg.text}
                    </div>
                    <button onClick={() => setQueueMsg(null)} className="text-lg opacity-50 hover:opacity-100">&times;</button>
                  </div>
                )}

                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Identity Details</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Summary</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-slate-800" : "divide-slate-100"}`}>
                      {loading ? (
                        <tr><td colSpan="3" className="px-8 py-20 text-center text-xs font-bold text-slate-400">Loading Queue...</td></tr>
                      ) : queueTickets.length === 0 ? (
                        <tr><td colSpan="3" className="px-8 py-20 text-center text-xs font-bold text-slate-400 uppercase tracking-widest">No open matters found</td></tr>
                      ) : (
                        queueTickets.map((ticket) => (
                          <tr key={ticket.ticket_id} className={`group transition-colors ${isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50/50"}`}>
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-4">
                                <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold">{(ticket.user_display_name || "U").charAt(0)}</div>
                                <div>
                                  <p className="text-sm font-bold">{ticket.user_display_name || "Anonymous"}</p>
                                  <p className="text-[10px] text-slate-500">{ticket.user_email}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-8 py-6">
                              <p className="text-xs text-slate-500 truncate max-w-xs">{ticket.conversation_summary || "No summary available."}</p>
                            </td>
                            <td className="px-8 py-6 text-right">
                              <button onClick={() => handleClaim(ticket.ticket_id)} className="px-4 py-2 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-50 transition-all">Claim Matter</button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* VIEW: INTAKE (THE CURRENTLY WORKING CASE) */}
          {activeView === "intake" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              {intakeTicket ? (
                <div className={`p-10 rounded-2xl border ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200 shadow-sm"}`}>
                  <div className="flex items-center justify-between mb-10">
                    <div className="flex items-center gap-6">
                      <div className="w-16 h-16 rounded-[2rem] bg-indigo-600 text-white flex items-center justify-center text-2xl font-black">
                        {(intakeTicket.user_display_name || "U").charAt(0)}
                      </div>
                      <div>
                        <h3 className="text-2xl font-black tracking-tight">{intakeTicket.user_display_name || "Anonymous"}</h3>
                        <p className="text-sm text-slate-500 font-medium">{intakeTicket.user_email}</p>
                      </div>
                    </div>
                    <div className="px-6 py-2 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-500 text-[10px] font-black uppercase tracking-widest">Currently Working</div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                    <div className="space-y-6">
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Intelligence</h4>
                      <div className={`p-6 rounded-2xl ${isDark ? "bg-slate-950/50" : "bg-slate-50"}`}>
                        <p className="text-sm leading-relaxed text-slate-500 italic">
                          {intakeTicket.conversation_summary || "Matter summary is being synthesized by AI. Please review the raw chat logs for full legal context."}
                        </p>
                      </div>
                    </div>
                    <div className="space-y-6">
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Timeline</h4>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 dark:border-slate-800">
                          <span className="text-xs font-bold text-slate-500">Escalated On</span>
                          <span className="text-xs font-black">{formatDate(intakeTicket.created_at)}</span>
                        </div>
                        <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 dark:border-slate-800">
                          <span className="text-xs font-bold text-slate-500">Claimed On</span>
                          <span className="text-xs font-black">{formatDate(intakeTicket.assigned_at)}</span>
                        </div>
                        <div className="flex items-center justify-between p-4 rounded-xl border border-slate-100 dark:border-slate-800">
                          <span className="text-xs font-bold text-slate-500">Scheduled For</span>
                          <span className="text-xs font-black">{intakeTicket.booking_confirmed_at ? formatDate(intakeTicket.booking_confirmed_at) : "Not yet scheduled"}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="mt-12 flex flex-col sm:flex-row gap-4">
                    <button onClick={() => navigate(`/lawyer/tickets/${intakeTicket.ticket_id}`)} className="flex-1 py-5 bg-indigo-600 text-white rounded-[2rem] text-sm font-black uppercase tracking-widest shadow-2xl shadow-indigo-600/30 hover:bg-indigo-700 transition-all flex items-center justify-center gap-3">
                      Enter Working Chamber
                      <ChevronRight size={20} />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="py-32 text-center">
                  <div className="w-20 h-20 rounded-[2.5rem] bg-slate-100 dark:bg-slate-800 flex items-center justify-center mx-auto mb-6 text-slate-300 dark:text-slate-600">
                    <Inbox size={40} />
                  </div>
                  <h3 className="text-xl font-bold">No Active Intake</h3>
                  <p className="text-sm text-slate-500 mt-2">Go to the Case Queue to claim a matter and start working.</p>
                </div>
              )}
            </div>
          )}

          {/* VIEW: PENDING MATTERS */}
          {activeView === "pending" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              {pendingTickets.length > 0 ? (
                <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">Claimed At</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">Scheduled For</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {pendingTickets.map((t) => (
                        <tr key={t.ticket_id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-8 py-6">
                            <div className="flex items-center gap-4">
                              <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold">{(t.user_display_name || "U").charAt(0)}</div>
                              <div>
                                <p className="text-sm font-bold">{t.user_display_name || "Anonymous"}</p>
                                <p className="text-[10px] text-slate-500">{t.user_email}</p>
                                {(t.outcome_notes?.includes("[USER-NO-SHOW]") || t.outcome_notes?.includes("[BOTH-NO-SHOW]")) && (
                                  <div className="mt-1 flex items-center gap-1 text-[9px] font-black text-red-500 uppercase tracking-tighter">
                                    <AlertTriangle size={10} />
                                    <span>Missed Appointment</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                          <td className="px-8 py-6 text-xs font-medium text-slate-500 text-center">
                            {formatDate(t.assigned_at)}
                          </td>
                          <td className="px-8 py-6 text-xs font-medium text-center">
                            {t.booking_confirmed_at ? (
                              <span className="text-slate-900 dark:text-slate-200 font-bold">{formatDate(t.booking_confirmed_at)}</span>
                            ) : (
                              <span className="text-slate-400 opacity-50">Not Scheduled</span>
                            )}
                          </td>
                          <td className="px-8 py-6 text-right">
                            <button
                              onClick={() => handleWorkOn(t.ticket_id)}
                              className="px-3 py-1.5 bg-indigo-500/10 text-indigo-500 rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-indigo-500 hover:text-white transition-all"
                            >
                              Work on this
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-32 text-center text-slate-400">
                  <Layers size={40} className="mx-auto mb-6 opacity-20" />
                  <p className="text-xs font-bold uppercase tracking-widest">No pending matters found</p>
                </div>
              )}
            </div>
          )}

          {/* VIEW: RESOLVED HISTORY */}
          {activeView === "resolved" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              {resolvedTickets.length > 0 ? (
                <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <div className="px-8 py-5 border-b border-slate-100 dark:border-slate-800">
                    <h2 className="text-base font-bold">Resolved Case History</h2>
                    <p className="text-xs text-slate-500 mt-1">Matters you have successfully addressed and resolved.</p>
                  </div>
                  <table className="w-full">
                    <thead>
                      <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Resolved At</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {resolvedTickets.map((t) => (
                        <tr key={t.ticket_id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="px-8 py-6">
                            <div className="flex items-center gap-4">
                              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center font-bold">{(t.user_display_name || "U").charAt(0)}</div>
                              <div>
                                <p className="text-sm font-bold">{t.user_display_name || "Anonymous"}</p>
                                <p className="text-[10px] text-slate-500">{t.user_email}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-8 py-6 text-xs font-medium text-slate-500">{formatDate(t.resolved_at)}</td>
                          <td className="px-8 py-6 text-right">
                            <button onClick={() => navigate(`/lawyer/tickets/${t.ticket_id}`)} className="text-indigo-500 text-xs font-bold hover:underline">View Details</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-32 text-center text-slate-400">
                  <CheckCircle2 size={40} className="mx-auto mb-6 opacity-20" />
                  <p className="text-xs font-bold uppercase tracking-widest">No resolved matters found</p>
                </div>
              )}
            </div>
          )}

          {/* VIEW: NOTES */}
          {activeView === "notes" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className="flex items-center gap-4 mb-8">
                  <div className="w-12 h-12 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center">
                    <Bookmark size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold">Legal Notes & Reminders</h2>
                    <p className="text-xs text-slate-500 mt-1">Personal workspace for drafting thoughts and case references.</p>
                  </div>
                </div>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Type your first note here..."
                  className={`w-full h-[400px] p-6 rounded-2xl border border-dashed text-sm bg-transparent focus:ring-0 resize-none font-medium leading-relaxed ${isDark ? "bg-slate-950/50 border-slate-800 text-slate-300" : "bg-slate-50 border-slate-200 text-slate-600"}`}
                />
                <div className="flex justify-end mt-6">
                  <button className="px-10 py-4 bg-indigo-600 text-white rounded-2xl text-sm font-bold shadow-xl shadow-indigo-600/20 hover:bg-indigo-700 transition-all">Save Legal Note</button>
                </div>
              </div>
            </div>
          )}

        </main>
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
              This will archive the case and mark it as unresolved because the user did not attend the scheduled consultation.
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setShowNoShowConfirm(false)}
                className={`flex-1 h-12 rounded-xl text-xs font-bold transition-all ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              >
                Cancel
              </button>
              <button
                onClick={handleMarkNoShow}
                disabled={isProcessing}
                className="flex-1 h-12 rounded-xl bg-red-600 text-white text-xs font-bold shadow-lg shadow-red-600/20 hover:bg-red-700 transition-all disabled:opacity-50"
              >
                {isProcessing ? "Processing..." : "Confirm No-Show"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Notifications Overlay */}
      <SystemNotification
        notifications={notifications}
        onDismiss={handleDismissNotification}
        onNavigate={(view) => {
          if (view === 'queue') {
            setActiveView('queue');
            setIsSidebarOpen(false);
          }
        }}
        isDark={isDark}
      />

      {/* CLAIM CONFLICT MODAL */}
      {claimError && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-300">
          <div className={`w-full max-w-md p-8 rounded-3xl border shadow-2xl animate-in zoom-in-95 duration-300 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
            }`}>
            <div className="flex flex-col items-center text-center">
              <div className="h-16 w-16 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center mb-6">
                <AlertTriangle size={32} />
              </div>
              <h3 className="text-xl font-black tracking-tight mb-2">{claimError.title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed mb-8">{claimError.message}</p>

              <button
                onClick={() => setClaimError(null)}
                className="w-full py-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-black uppercase tracking-widest shadow-lg shadow-indigo-600/20 transition-all"
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
