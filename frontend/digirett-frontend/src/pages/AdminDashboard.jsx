import React, { useEffect, useState } from "react";
import adminService from "../services/adminService";
import {
  Users, Mail, Shield, Loader2, Search,
  UserPlus, CheckCircle, ArrowLeft, LogOut,
  LayoutDashboard, Menu, Plus, X, Calendar, User,
  ShieldCheck, Scale, Crown, Clock, AlertTriangle, Send,
  UserX, UserCheck, Trash2, Sun, Moon, RefreshCw, BarChart3
} from "lucide-react";
import { useTheme } from "../providers/ThemeProvider";
import { Link, useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { useClerk, useUser } from "@clerk/clerk-react";
import hitlService from "../services/hitlService";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';
import SystemNotification from "../components/chat/ResolutionNotification";
import CalendarView from "../components/common/CalendarView";

export default function AdminDashboard() {
  const { theme, isDark, toggleTheme } = useTheme();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("lawyer");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [enablingLawyer, setEnablingLawyer] = useState(false);
  const [message, setMessage] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth >= 1024);
  const [showProfileDropdown, setShowProfileDropdown] = useState(false);

  // Local sub-navigation state (Synced with URL for refresh persistence & back-button support)
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const activeView = searchParams.get("view") || "dashboard";
  const setActiveView = (view) => setSearchParams({ view });

  const [invitations, setInvitations] = useState([]);
  const [invitesLoading, setInvitesLoading] = useState(true);
  const [tickets, setTickets] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [healthStatus, setHealthStatus] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);

  const { user: clerkUser } = useUser();
  const userRole = clerkUser?.publicMetadata?.role || "admin";
  const isSystemAdmin = userRole === "system_admin";
  const [domainAnalytics, setDomainAnalytics] = useState(null);
  const { signOut, openUserProfile } = useClerk();
  const navigate = useNavigate();
  const [confirmModal, setConfirmModal] = useState({ show: false, user: null });
  const [viewUser, setViewUser] = useState(null);

  // Scoped Messages
  const [inviteMsg, setInviteMsg] = useState(null);
  const [queueMsg, setQueueMsg] = useState(null);
  const [usersMsg, setUsersMsg] = useState(null);
  const [globalMsg, setGlobalMsg] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [dismissedEvents, setDismissedEvents] = useState(() => {
    const seen = localStorage.getItem("dismissed_admin_events");
    return seen ? JSON.parse(seen) : [];
  });

  const handleLogout = async () => {
    await signOut();
    navigate("/sign-in");
  };

  const checkInvitationStatus = React.useCallback(async () => {
    if (!isSystemAdmin) return;
    try {
      const savedDismissed = localStorage.getItem("dismissed_admin_events");
      const currentDismissed = savedDismissed ? JSON.parse(savedDismissed) : [];

      const invitesData = await adminService.listInvitations();
      if (!Array.isArray(invitesData)) return;

      const newNotifications = [];
      invitesData.forEach(invite => {
        if (invite.status === 'accepted') {
          const inviteId = invite.invite_id || invite.id;
          const eventId = `accepted_${inviteId}`;

          if (!currentDismissed.includes(eventId)) {
            newNotifications.push({
              id: eventId,
              type: 'accepted',
              caseRef: invite.role.toUpperCase(),
              message: `Invitation accepted by ${invite.email} for role: ${invite.role.toUpperCase()}.`,
              view: 'users'
            });
          }
        }
      });

      setNotifications(newNotifications);
    } catch (err) {
      console.error("[AdminDashboard] Error checking invitation status:", err);
    }
  }, []);

  const handleDismissNotification = React.useCallback((notifId) => {
    setDismissedEvents(prev => {
      const updated = [...prev, notifId];
      localStorage.setItem("dismissed_admin_events", JSON.stringify(updated));
      return updated;
    });
    setNotifications(prev => prev.filter(n => n.id !== notifId));
  }, []);

  const fetchDashboardData = async () => {
    try {
      setDashboardLoading(true);
      const [usersData, invitesData, ticketsData, logsData, healthData, domainData] = await Promise.all([
        adminService.listUsers(),
        adminService.listInvitations(),
        adminService.getAllTickets(),
        adminService.getAuditLogs(100),
        adminService.getHealthStatus(),
        adminService.getDomainAnalytics()
      ]);

      setUsers(usersData.filter(u => u.email));
      setInvitations(invitesData);
      setTickets(ticketsData);
      setAuditLogs(logsData);
      setHealthStatus(healthData);
      setDomainAnalytics(domainData);

      // Also check for new notifications during main fetch
      checkInvitationStatus();
    } catch (err) {
      console.error("Failed to fetch dashboard data:", err);
    } finally {
      setDashboardLoading(false);
      setLoading(false);
      setInvitesLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
    const dataInterval = setInterval(fetchDashboardData, 30000);
    const notifInterval = setInterval(checkInvitationStatus, 30000);
    return () => {
      clearInterval(dataInterval);
      clearInterval(notifInterval);
    };
  }, [checkInvitationStatus]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setIsSidebarOpen(true);
      } else {
        setIsSidebarOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    setMessage(null);
  }, [activeView]);

  const roleInfo = {
    lawyer: {
      title: "Lawyer Access",
      icon: <Scale className="w-5 h-5" />,
      description:
        "Lawyers can view escalated user tickets, access the matter queue, review user details, and respond to assigned legal requests.",
      permissions: [
        "Access lawyer dashboard",
        "View matter queue",
        "Review escalated user tickets",
        "Manage own lawyer profile",
      ],
    },
    admin: {
      title: "Admin Access",
      icon: <Crown className="w-5 h-5" />,
      description:
        "Admins can manage users, lawyers, invitations, dashboard analytics, and platform-level administrative controls.",
      permissions: [
        "Access admin dashboard",
        "Manage system users",
        "Invite lawyers and admins",
        "View platform analytics",
      ],
    },
  };

  const [showConfirmInvite, setShowConfirmInvite] = useState(false);

  const handleInvite = async (e, force = false) => {
    if (e) e.preventDefault();
    if (!inviteEmail) return;

    // Check if already invited with same role
    const existingInvite = invitations.find(i => i.email.toLowerCase() === inviteEmail.toLowerCase() && i.role === inviteRole);
    if (existingInvite && !force) {
      setShowConfirmInvite(true);
      return;
    }

    setInviteLoading(true);
    setInviteMsg(null);
    setShowConfirmInvite(false);
    try {
      await adminService.inviteUser(inviteEmail, inviteRole);
      setInviteMsg({ type: "success", text: `Invitation sent to ${inviteEmail}` });
      setInviteEmail("");
      fetchDashboardData();
    } catch (err) {
      // Prioritize the extracted message from the error object
      const errorMsg = err.message || "An unexpected error occurred while sending the invitation.";
      setInviteMsg({ type: "error", text: errorMsg });
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRevokeInvite = async (inviteId) => {
    if (!window.confirm("Are you sure you want to revoke this invitation?")) return;
    try {
      await adminService.revokeInvitation(inviteId);
      setInviteMsg({ type: "success", text: "Invitation revoked successfully" });
      fetchDashboardData();
    } catch (err) {
      setInviteMsg({ type: "error", text: "Failed to revoke invitation" });
    }
  };

  const handleToggleUserStatus = async (userId) => {
    try {
      await adminService.suspendUser(userId);
      setUsersMsg({ type: "success", text: "User access suspended successfully." });
      setConfirmModal({ show: false, user: null });
      fetchDashboardData();
    } catch (err) {
      setUsersMsg({ type: "error", text: "Failed to suspend user access." });
    }
  };

  const handleUnsuspendUser = async (userId) => {
    try {
      await adminService.activateUser(userId);
      setUsersMsg({ type: "success", text: "User access restored successfully." });
      fetchDashboardData();
    } catch (err) {
      setUsersMsg({ type: "error", text: "Failed to restore user access." });
    }
  };

  const handleAssignTicket = async (ticketId, lawyerId) => {
    if (!lawyerId) return;
    try {
      const lawyer = users.find(u => u.user_id === lawyerId);
      const lawyerName = lawyer?.user_profiles?.display_name || lawyer?.email || "the professional";
      await adminService.assignTicket(ticketId, lawyerId);
      setQueueMsg({
        type: "success",
        text: `You have assigned this matter to ${lawyerName}. They are now linked to this matter.`
      });
      fetchDashboardData();
      // Auto-clear message after 8 seconds
      setTimeout(() => setQueueMsg(null), 8000);
    } catch (err) {
      setQueueMsg({ type: "error", text: "Failed to link the lawyer to this matter. Please try again." });
    }
  };

  const handleEnableLawyerFeatures = async () => {
    setEnablingLawyer(true);
    setGlobalMsg(null);
    const selfEmail = clerkUser?.primaryEmailAddress?.emailAddress;
    if (!selfEmail) {
      setGlobalMsg({ type: "error", text: "Failed to locate email address on your profile." });
      setEnablingLawyer(false);
      return;
    }
    try {
      await adminService.inviteUser(selfEmail, "lawyer");
      setGlobalMsg({
        type: "success",
        text: `Invitation initiated. Please check your inbox at ${selfEmail} to accept the lawyer role and complete activation.`
      });
      fetchDashboardData();
    } catch (err) {
      setGlobalMsg({ type: "error", text: err.message || "Failed to trigger self-invitation." });
    } finally {
      setEnablingLawyer(false);
    }
  };

  const hasLawyerDashboard = clerkUser?.publicMetadata?.has_lawyer_dashboard === true;

  const filteredUsers = users.filter(u => {
    const email = (u.email || "").toLowerCase();
    const displayName = (u.user_profiles?.display_name || "").toLowerCase();
    const query = searchQuery.toLowerCase();
    return email.includes(query) || displayName.includes(query);
  });

  // Derived Stats
  const totalUsers = users.length;
  const lawyerCount = users.filter(u => u.role === 'lawyer').length;
  const adminCount = users.filter(u => u.role === 'admin').length;
  const standardUserCount = users.filter(u => u.role === 'user' || !u.role).length;
  const pendingInvites = invitations.filter(i => i.status === 'pending').length;
  const acceptedInvites = invitations.filter(i => i.status === 'accepted').length;
  const totalInvites = invitations.length;

  // ── Chart Data Processors ──────────────────────────────────────────

  const roleData = [
    { name: 'Admins', value: adminCount, color: '#EC6B56' },
    { name: 'Lawyers', value: lawyerCount, color: '#FFC154' },
    { name: 'Users', value: standardUserCount, color: '#47B39C' },
  ];

  const statusData = [
    { name: 'Active', value: users.filter(u => u.status === 'active').length, color: '#10b981' },
    { name: 'Inactive', value: users.filter(u => u.status === 'inactive' || u.status === 'suspended').length, color: '#ef4444' },
  ];

  const getOnboardingTrend = () => {
    const counts = {};
    users.forEach(u => {
      const sortKey = new Date(u.created_at).toISOString().split('T')[0];
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

  const ticketStatusData = [
    { name: 'Open', value: tickets.filter(t => t.status === 'open' && !t.assigned_lawyer_id).length, color: '#f59e0b' },
    { name: 'Assigned', value: tickets.filter(t => t.assigned_lawyer_id && t.status !== 'closed').length, color: '#3b82f6' },
    { name: 'Closed', value: tickets.filter(t => t.status === 'closed').length, color: '#10b981' },
  ];

  const auditTrendData = () => {
    const counts = {};
    auditLogs.forEach(log => {
      const sortKey = new Date(log.created_at).toISOString().split('T')[0];
      counts[sortKey] = (counts[sortKey] || 0) + 1;
    });

    const result = [];
    for (let i = 9; i >= 0; i--) {
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

  const auditTypeData = () => {
    const counts = {};
    auditLogs.forEach(log => {
      const cleanAction = log.action.replace('admin.', '').replace('user.', '').replace('ticket.', '');
      counts[cleanAction] = (counts[cleanAction] || 0) + 1;
    });

    const predefinedEvents = [
      { key: "user_invited", label: "User Invited" },
      { key: "invite_accepted", label: "Invite Accepted" },
      { key: "user_promoted", label: "Role Promoted" },
      { key: "dual_role_enabled", label: "Dual Role" },
      { key: "signup_from_invite", label: "New Signup" }
    ];

    return predefinedEvents.map(event => ({
      action: event.label,
      count: counts[event.key] || 0
    }));
  };

  const lawyerWorkloadData = () => {
    const counts = {};
    tickets.forEach(t => {
      if (t.assigned_lawyer_id) {
        counts[t.assigned_lawyer_id] = (counts[t.assigned_lawyer_id] || 0) + 1;
      }
    });
    return Object.keys(counts).map(id => {
      const lawyer = users.find(u => u.user_id === id);
      return {
        name: lawyer?.user_profiles?.display_name || lawyer?.email || id.substring(0, 8),
        tickets: counts[id]
      };
    }).sort((a, b) => b.tickets - a.tickets);
  };

  const getThroughputData = () => {
    const intake = {};
    const output = {};
    tickets.forEach(t => {
      const cKey = new Date(t.created_at).toISOString().split('T')[0];
      intake[cKey] = (intake[cKey] || 0) + 1;
      if (t.resolved_at) {
        const rKey = new Date(t.resolved_at).toISOString().split('T')[0];
        output[rKey] = (output[rKey] || 0) + 1;
      }
    });
    const result = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const sKey = d.toISOString().split('T')[0];
      result.push({
        date: d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' }),
        intake: intake[sKey] || 0,
        resolved: output[sKey] || 0
      });
    }
    return result;
  };

  const selectedRole = roleInfo[inviteRole] || roleInfo.lawyer;

  return (
    <div className={`flex h-screen overflow-hidden ${isDark ? "bg-[#020617] text-slate-200" : "bg-[#f1f5f9] text-slate-900"}`}>

      {/* Sidebar Overlay for Mobile */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-950/60 z-40 lg:hidden backdrop-blur-sm transition-opacity duration-300"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`fixed lg:relative z-50 inset-y-0 left-0 w-64 transform transition-transform duration-300 ease-in-out border-r flex flex-col ${isDark ? "bg-slate-900 border-slate-800" : "bg-[#0f172a] border-slate-800"} ${isSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="h-16 flex items-center px-6 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center">
              <img src="/user-chat-logo.png" alt="Logo" className="w-full h-full object-contain p-0.5" />
            </div>
            <span className="font-bold text-lg tracking-tight text-white">
              {isSystemAdmin ? "System Admin Panel" : "Admin Panel"}
            </span>
          </div>
          <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden ml-auto text-slate-400">
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 px-3 py-6 space-y-1 overflow-y-auto">
          <p className="px-4 text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4 opacity-50 font-bold">Navigation</p>

          <button
            onClick={() => { setActiveView("dashboard"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "dashboard" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <LayoutDashboard size={18} />
            Dashboard
          </button>

          <button
            onClick={() => { setActiveView("invite"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "invite" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <UserPlus size={18} />
            {isSystemAdmin ? "Invite Team" : "Invitation List"}
          </button>

          <button
            onClick={() => { setActiveView("users"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "users" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <Users size={18} />
            System Users
          </button>

          <button
            onClick={() => { setActiveView("queue"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "queue" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <Mail size={18} />
            Matter Queue
          </button>

          <button
            onClick={() => { setActiveView("distribution"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "distribution" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <BarChart3 size={18} />
            Inquiry Distribution
          </button>

          {isSystemAdmin && (
            <button
              onClick={() => { setActiveView("calendar"); setIsSidebarOpen(false); }}
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "calendar" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
            >
              <Calendar size={18} />
              Calendar
            </button>
          )}

          <button
            onClick={() => { setActiveView("settings"); setIsSidebarOpen(false); }}
            className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "settings" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
          >
            <ShieldCheck size={18} />
            {isSystemAdmin ? "System Admin Settings" : "Admin Settings"}
          </button>

          {hasLawyerDashboard && (
            <Link
              to="/lawyer"
              className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-white hover:bg-white/5 mt-2 border border-indigo-500/20 bg-indigo-500/5"
            >
              <Scale size={18} className="text-indigo-400" />
              Lawyer Dashboard
            </Link>
          )}

          <div className="pt-6 mt-6 border-t border-white/5 space-y-1">
            <Link to="/chat" className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-white hover:bg-white/5 group">
              <ArrowLeft size={18} />
              Go to Chat
            </Link>
          </div>
        </nav>

        {/* Bottom Fixed Action */}
        <div className="p-4 border-t border-white/5 mt-auto">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all text-slate-400 hover:text-red-400 hover:bg-red-500/10"
          >
            <LogOut size={18} />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">

        {/* Top Bar */}
        <header className={`h-16 border-b flex items-center justify-between px-8 z-40 ${isDark ? "bg-slate-900/50 border-slate-800" : "bg-white border-slate-200"}`}>
          <div className="flex items-center gap-4 flex-1">
            <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden text-slate-500">
              <Menu size={24} />
            </button>
            <h2 className="text-lg font-bold capitalize">
              {activeView === 'dashboard'
                ? (isSystemAdmin ? 'System Admin Dashboard' : 'Admin Dashboard')
                : activeView === 'settings'
                  ? (isSystemAdmin ? 'System Admin Settings' : 'Admin Settings')
                  : activeView === 'calendar'
                    ? 'System Admin Schedule'
                    : activeView.replace('-', ' ')}
            </h2>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={toggleTheme}
              className={`p-2 rounded-xl transition-all ${isDark ? "bg-gray-800 text-blue-400 hover:bg-gray-700" : "bg-gray-50 text-gray-500 hover:bg-gray-100"}`}
            >
              {isDark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <div className="h-8 w-[1px] bg-gray-200 dark:bg-gray-800 mx-1"></div>
            <div className="relative">
              <div
                onClick={() => setShowProfileDropdown(!showProfileDropdown)}
                className="flex items-center gap-3 pl-2 cursor-pointer group"
              >
                <div className={`h-8 w-8 rounded-full flex items-center justify-center font-bold text-xs transition-transform group-hover:scale-105 ${isDark ? "bg-indigo-500/20 text-indigo-400" : "bg-indigo-100 text-indigo-700"
                  }`}>
                  {clerkUser?.firstName?.charAt(0) || "A"}
                </div>
                <div className="hidden sm:block text-left">
                  <p className="text-xs font-bold leading-none">{clerkUser?.fullName || (isSystemAdmin ? "System Admin" : "Admin")}</p>
                  <p className="text-[10px] text-slate-500 mt-1 tracking-wider uppercase font-black">
                    {isSystemAdmin ? "System Admin" : "Admin"}
                  </p>
                </div>
              </div>

              {showProfileDropdown && (
                <div className={`absolute top-full right-0 mt-2 w-48 rounded-xl border shadow-2xl z-[100] overflow-hidden animate-in fade-in zoom-in-95 duration-200 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
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

                    {hasLawyerDashboard ? (
                      <Link
                        to="/lawyer"
                        onClick={() => setShowProfileDropdown(false)}
                        className={`w-full px-3 py-2 flex items-center gap-3 rounded-lg text-xs font-bold transition-colors ${isDark ? "text-indigo-400 hover:bg-indigo-500/10" : "text-indigo-600 hover:bg-indigo-50"
                          }`}
                      >
                        <Scale size={14} />
                        Lawyer Dashboard
                      </Link>
                    ) : (
                      <button
                        onClick={() => { setActiveView("settings"); setShowProfileDropdown(false); }}
                        className={`w-full px-3 py-2 flex items-center gap-3 rounded-lg text-xs font-bold transition-colors ${isDark ? "text-indigo-400 hover:bg-indigo-500/10" : "text-indigo-600 hover:bg-indigo-50"
                          }`}
                      >
                        <Plus size={14} />
                        Enable Lawyer Features
                      </button>
                    )}
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
        </header>

        {/* Content Section */}
        <main className="flex-1 overflow-y-auto p-6 md:p-8">

          {/* VIEW: DASHBOARD */}
          {activeView === "dashboard" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-10">

              {/* KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-6">
                {[
                  { label: "Administrators", value: adminCount, color: "purple" },
                  { label: "Active Lawyers", value: lawyerCount, color: "blue" },
                  { label: "Standard Users", value: standardUserCount, color: "green" },
                  { label: "Open Tickets", value: tickets.filter(t => t.status === 'open' && !t.assigned_lawyer_id).length, color: "orange" },
                  { label: "Pending Invitations", value: pendingInvites, color: "amber" },
                  { label: "Total Platform Users", value: totalUsers, color: "indigo" },
                ].map((stat, idx) => (
                  <div key={idx} className={`p-6 rounded-2xl border shadow-sm flex flex-col gap-2 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
                    }`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">{stat.label}</span>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-black">{stat.value}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Row 1: User Role Distribution + Status Breakdown + Onboarding Trend */}
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
                {/* Role Distribution */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Role Distribution</h3>
                  <div className="h-[250px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={roleData} innerRadius={60} outerRadius={80} dataKey="value" stroke="none">
                          {roleData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip cursor={false} />
                        <Legend iconType="circle" />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Status Breakdown */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">User Status</h3>
                  <div className="h-[250px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={statusData} innerRadius={60} outerRadius={80} dataKey="value" stroke="none">
                          {statusData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip cursor={false} />
                        <Legend iconType="circle" />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Onboarding Trend */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Onboarding Trend</h3>
                  <div className="h-[250px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={getOnboardingTrend()}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip cursor={false} />
                        <Line type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={3} dot={{ r: 4 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Row 2: Ticket Assignment Status + Lawyer Workload */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {/* Ticket Assignment Status */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Ticket Assignment Status</h3>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={ticketStatusData} layout="vertical">
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip cursor={false} />
                        <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
                          {ticketStatusData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Lawyer Workload */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Lawyer Workload</h3>
                  <div className="h-[300px] w-full">
                    {lawyerWorkloadData().length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={lawyerWorkloadData()}>
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                          <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                          <Tooltip cursor={false} />
                          <Bar dataKey="tickets" fill="#3b82f6" radius={[4, 4, 0, 0]} barSize={40} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-full flex items-center justify-center text-slate-500 text-xs font-bold italic opacity-40">
                        No active assignments currently.
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Row 3: Audit Event Breakdown + Throughput */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {/* Case Throughput */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Matter Throughput Metrics</h3>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={getThroughputData()}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                        <XAxis dataKey="date" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                        <Tooltip
                          cursor={false}
                          contentStyle={{
                            backgroundColor: isDark ? '#0f172a' : '#fff',
                            border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                            borderRadius: '8px',
                            fontSize: '10px'
                          }}
                        />
                        <Legend iconType="circle" />
                        <Bar dataKey="intake" name="New Tickets" fill="#6366f1" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="resolved" name="Resolved" fill="#10b981" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Audit Event Breakdown */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Audit Event Breakdown</h3>
                  <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={auditTypeData()} layout="vertical">
                        <XAxis type="number" hide />
                        <YAxis dataKey="action" type="category" tick={{ fontSize: 9 }} width={100} axisLine={false} tickLine={false} />
                        <Tooltip
                          cursor={false}
                          contentStyle={{
                            backgroundColor: isDark ? '#0f172a' : '#fff',
                            border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                            borderRadius: '8px',
                            fontSize: '10px'
                          }}
                        />
                        <Bar dataKey="count" fill="#a855f7" radius={[0, 4, 4, 0]} barSize={25} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Row 4: Inquiry Domain Distribution */}
              <div className="grid grid-cols-1 gap-8">
                {/* Inquiry Domain Distribution Section */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">User Inquiry Domain Distribution</h3>
                  <div className="h-[300px] w-full">
                    {domainAnalytics && domainAnalytics.distribution && domainAnalytics.distribution.length > 0 ? (
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={domainAnalytics.distribution} layout="vertical">
                          <XAxis type="number" hide />
                          <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={150} axisLine={false} tickLine={false} />
                          <Tooltip
                            cursor={false}
                            contentStyle={{
                              backgroundColor: isDark ? '#0f172a' : '#fff',
                              border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                              borderRadius: '8px',
                              fontSize: '10px'
                            }}
                          />
                          <Bar dataKey="queries" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={20} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="h-full flex items-center justify-center text-slate-500 text-xs font-bold italic opacity-40">
                        No classified user queries recorded yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>

            </div>
          )}

          {/* VIEW: INVITE TEAM */}
          {activeView === "invite" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              {/* Header Card */}
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <h1 className="text-2xl font-bold">{isSystemAdmin ? "Team Invitations" : "Invitation List"}</h1>
                <p className="mt-1 text-sm text-slate-500">
                  {isSystemAdmin
                    ? "Send secure invitation links to lawyers and administrators with controlled role-based access."
                    : "View active and accepted role invitations."}
                </p>
              </div>

              {isSystemAdmin && (
                <div className="grid grid-cols-1 gap-6">
                  {/* Left Form Card */}
                  <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                    <div className={`px-7 py-6 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                      <div className="flex items-start gap-4">
                        <div className="w-11 h-11 rounded-xl bg-indigo-600/10 text-indigo-500 flex items-center justify-center">
                          <UserPlus className="w-5 h-5" />
                        </div>
                        <div>
                          <h2 className="text-xl font-bold">Send Official Invitation</h2>
                          <p className="mt-1 text-sm text-slate-500">
                            Invite a verified legal professional or administrator to join the platform.
                          </p>
                        </div>
                      </div>
                    </div>
                    <form onSubmit={handleInvite} className="px-7 py-7 space-y-6">
                      {/* Email */}
                      <div>
                        <label className="block text-xs font-bold tracking-wide text-slate-500 uppercase mb-2">
                          Email Address
                        </label>
                        <div className="relative">
                          <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                          <input
                            type="email"
                            value={inviteEmail}
                            onChange={(e) => setInviteEmail(e.target.value)}
                            placeholder="professional@company.com"
                            className={`w-full h-14 pl-12 pr-4 rounded-xl border text-sm outline-none transition-all focus:ring-2 focus:ring-indigo-500 ${isDark ? "bg-slate-950 border-slate-800 text-white" : "bg-white border-slate-300 text-slate-950"}`}
                            required
                          />
                        </div>
                      </div>
                      {/* Role */}
                      <div>
                        <label className="block text-xs font-bold tracking-wide text-slate-500 uppercase mb-2">
                          Assign Role
                        </label>
                        <select
                          value={inviteRole}
                          onChange={(e) => setInviteRole(e.target.value)}
                          className={`w-full h-14 px-4 rounded-xl border text-sm outline-none appearance-none transition-all focus:ring-2 focus:ring-indigo-500 ${isDark ? "bg-slate-950 border-slate-800 text-white" : "bg-white border-slate-300 text-slate-950"}`}
                        >
                          <option value="lawyer">Lawyer</option>
                          <option value="admin">Administrator</option>
                        </select>
                      </div>
                      {/* Security Box */}
                      <div className={`rounded-xl border px-4 py-4 flex items-start gap-3 ${isDark ? "bg-amber-900/10 border-amber-900/20" : "bg-amber-50 border-amber-200"}`}>
                        <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5" />
                        <div>
                          <p className={`text-sm font-semibold ${isDark ? "text-amber-400" : "text-amber-900"}`}>
                            Secure invitation required
                          </p>
                          <p className={`mt-1 text-sm leading-6 ${isDark ? "text-amber-500/80" : "text-amber-800"}`}>
                            Invitation links should expire within 24–72 hours and must only be accepted by the invited email address.
                          </p>
                        </div>
                      </div>
                      {/* Button */}
                      <button
                        type="submit"
                        disabled={inviteLoading}
                        className="w-full h-14 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold flex items-center justify-center gap-2 transition shadow-xl shadow-indigo-600/20"
                      >
                        {inviteLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                        Send Invitation
                      </button>

                      {showConfirmInvite && !message && (
                        <div className={`mt-4 p-5 rounded-xl border animate-in fade-in slide-in-from-top-2 duration-300 ${isDark ? "bg-amber-500/5 border-amber-500/20" : "bg-amber-50 border-amber-200"}`}>
                          <div className="flex items-start gap-4">
                            <div className={`mt-1 p-2 rounded-lg ${isDark ? "bg-amber-500/10" : "bg-amber-100"}`}>
                              <AlertTriangle className="w-5 h-5 text-amber-500" />
                            </div>
                            <div className="flex-1">
                              <h4 className="text-sm font-bold">Duplicate Invitation</h4>
                              <p className="text-xs text-slate-500 mt-1 leading-5">
                                This user already has a pending invite for <strong>{inviteRole}</strong>.
                                Are you sure you want to send another one?
                              </p>
                              <div className="mt-4 flex items-center gap-3">
                                <button
                                  onClick={() => handleInvite(null, true)}
                                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-colors"
                                >
                                  Yes, Send Again
                                </button>
                                <button
                                  onClick={() => setShowConfirmInvite(false)}
                                  className={`px-4 py-2 rounded-lg text-xs font-bold transition-colors ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}

                      {inviteMsg && (
                        <div className={`mt-4 p-4 rounded-xl flex items-center justify-between text-sm font-bold animate-in fade-in zoom-in-95 ${inviteMsg.type === 'success'
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-red-500/10 text-red-500 border border-red-500/20'
                          }`}>
                          <div className="flex items-center gap-3">
                            {inviteMsg.type === 'success' ? <CheckCircle size={18} /> : <AlertTriangle size={18} />}
                            <div>
                              <p>{inviteMsg.text}</p>
                              {inviteMsg.type === 'error' && (inviteMsg.text.toLowerCase().includes("sign in") || inviteMsg.text.toLowerCase().includes("expired")) && (
                                <button
                                  onClick={() => navigate("/sign-in")}
                                  className="mt-2 px-3 py-1 bg-white/20 hover:bg-white/30 rounded-lg text-[10px] uppercase tracking-widest font-black transition-all"
                                >
                                  Sign In Now
                                </button>
                              )}
                            </div>
                          </div>
                          <button onClick={() => setInviteMsg(null)} className="text-lg opacity-50 hover:opacity-100">&times;</button>
                        </div>
                      )}
                    </form>
                  </div>

                </div>
              )}

              {/* Pending Invitations Table */}
              <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className={`px-7 py-5 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                  <h2 className="text-lg font-bold">{isSystemAdmin ? "Pending Invitations" : "Sent Invitations"}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {isSystemAdmin ? "Track invitations that are sent but not yet accepted." : "Track invitations that have been sent."}
                  </p>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className={`${isDark ? "bg-slate-950/50" : "bg-slate-50"} border-b ${isDark ? "border-slate-800" : "border-slate-200"}`}>
                      <tr>
                        <th className="text-left px-7 py-4 font-semibold text-slate-500">Email</th>
                        <th className="text-left px-7 py-4 font-semibold text-slate-500">Role</th>
                        <th className="text-left px-7 py-4 font-semibold text-slate-500">Status</th>
                        <th className="text-left px-7 py-4 font-semibold text-slate-500">Sent On</th>
                        {isSystemAdmin && <th className="text-right px-7 py-4 font-semibold text-slate-500">Action</th>}
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-slate-800" : "divide-slate-100"}`}>
                      {invitesLoading ? (
                        <tr>
                          <td colSpan={isSystemAdmin ? "5" : "4"} className="px-7 py-12 text-center">
                            <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mx-auto opacity-20" />
                          </td>
                        </tr>
                      ) : invitations.length === 0 ? (
                        <tr>
                          <td colSpan={isSystemAdmin ? "5" : "4"} className="px-7 py-12 text-center text-slate-500">
                            No active invitations found in the system.
                          </td>
                        </tr>
                      ) : (
                        invitations.map((invite) => (
                          <tr key={invite.invite_id} className={`transition-colors ${isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50/50"}`}>
                            <td className="px-7 py-4 font-medium">{invite.email}</td>
                            <td className="px-7 py-4 capitalize">{invite.role}</td>
                            <td className="px-7 py-4">
                              <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border ${invite.status === 'pending'
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                                }`}>
                                {invite.status}
                              </span>
                            </td>
                            <td className="px-7 py-4 text-slate-500">
                              {new Date(invite.created_at).toLocaleDateString()}
                            </td>
                            {isSystemAdmin && (
                              <td className="px-7 py-4 text-right">
                                {invite.status === 'pending' ? (
                                  <div className="flex items-center justify-end gap-3">
                                    <button
                                      onClick={async () => {
                                        setInviteEmail(invite.email);
                                        setInviteRole(invite.role);
                                        window.scrollTo({ top: 0, behavior: 'smooth' });
                                      }}
                                      className="text-indigo-500 hover:text-indigo-400 font-bold"
                                    >
                                      Resend
                                    </button>
                                    <button
                                      onClick={() => handleRevokeInvite(invite.invite_id)}
                                      className="p-1 transition-all text-red-500 hover:text-red-400"
                                      title="Revoke Invitation"
                                    >
                                      <Trash2 size={16} />
                                    </button>
                                  </div>
                                ) : (
                                  <span className="text-[10px] text-slate-600 font-bold uppercase">Accepted</span>
                                )}
                              </td>
                            )}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* VIEW: SYSTEM USERS */}
          {activeView === "users" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className={`rounded-xl border shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
                }`}>
                <div className={`p-6 border-b flex flex-col md:flex-row md:items-center justify-between gap-4 ${isDark ? "border-slate-800" : "border-slate-100"
                  }`}>
                  <h3 className="font-bold text-lg flex items-center gap-3">
                    <Users size={22} className="text-slate-400" />
                    System Members Directory
                  </h3>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search by name or email..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className={`pl-9 pr-4 py-2 rounded-lg border text-sm outline-none w-full md:w-80 transition-all ${isDark ? "bg-slate-950 border-slate-800 focus:border-indigo-500" : "bg-slate-50 border-slate-200 focus:border-indigo-500"
                        }`}
                    />
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className={`text-left ${isDark ? "bg-slate-950/50" : "bg-slate-50/50"}`}>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Identity</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Access Role</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Status</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">User Details</th>
                        {isSystemAdmin && <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>}
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-slate-800" : "divide-slate-100"}`}>
                      {loading ? (
                        <tr>
                          <td colSpan={isSystemAdmin ? 5 : 4} className="px-8 py-20 text-center">
                            <Loader2 size={32} className="animate-spin text-indigo-500 mx-auto opacity-20" />
                          </td>
                        </tr>
                      ) : (
                        filteredUsers.map((user) => (
                          <tr key={user.user_id} className={`group transition-colors ${isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50/50"}`}>
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-5">
                                <div className={`h-11 w-11 rounded-xl flex items-center justify-center font-bold text-sm ${isDark ? "bg-indigo-500/10 text-indigo-400" : "bg-indigo-50 text-indigo-600"}`}>
                                  {(user.user_profiles?.display_name || user.email || "?").charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-bold truncate">{user.user_profiles?.display_name || "Active Member"}</p>
                                  <p className="text-[11px] text-slate-500 truncate font-medium">{user.email}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-8 py-6">
                              <span className={`inline-flex items-center px-4 py-1.5 rounded-full text-[10px] font-black tracking-widest uppercase border ${user.role === 'admin'
                                ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                user.role === 'lawyer'
                                  ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                  'bg-slate-800 text-slate-400 border-slate-700'
                                }`}>
                                {user.role || 'user'}
                              </span>
                            </td>
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-2">
                                <div className={`h-1.5 w-1.5 rounded-full ${(user.status !== 'inactive' && user.status !== 'suspended') ? "bg-emerald-500" : "bg-slate-400"}`} />
                                <span className={`text-[10px] font-black uppercase tracking-widest ${(user.status !== 'inactive' && user.status !== 'suspended') ? "text-emerald-500" : "text-slate-400"}`}>
                                  {user.status === 'inactive' ? 'Inactive' : (user.status || 'Active')}
                                </span>
                              </div>
                            </td>
                            <td className="px-8 py-6 text-right">
                              <button
                                onClick={() => setViewUser(user)}
                                className={`px-4 py-2 rounded-lg text-xs font-bold border transition-all ${isDark ? "border-slate-800 text-slate-400 hover:bg-slate-800" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                              >
                                View Profile
                              </button>
                            </td>
                            {isSystemAdmin && (
                              <td className="px-8 py-6 text-right">
                                <div className="flex items-center justify-end">
                                  {clerkUser?.id === user.clerk_user_id ? (
                                    <button disabled className="px-4 py-2 rounded-lg text-xs font-bold bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed">
                                      Current User
                                    </button>
                                  ) : (user.status === 'suspended' || user.status === 'inactive') ? (
                                    <button
                                      onClick={() => handleUnsuspendUser(user.user_id)}
                                      className="px-4 py-2 rounded-lg text-xs font-bold border transition-all text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/5"
                                      title="Revoke Suspension"
                                    >
                                      Revoke
                                    </button>
                                  ) : (
                                    <button
                                      onClick={() => setConfirmModal({ show: true, user: user })}
                                      className="px-4 py-2 rounded-lg text-xs font-bold border transition-all text-red-500 border-red-500/20 hover:bg-red-500/5"
                                      title="Suspend User"
                                    >
                                      Suspend
                                    </button>
                                  )}
                                </div>
                              </td>
                            )}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* VIEW: TICKETS (QUEUE) */}
          {activeView === "queue" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className={`rounded-xl border shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
                }`}>
                <div className={`p-6 border-b flex flex-col md:flex-row md:items-center justify-between gap-4 ${isDark ? "border-slate-800" : "border-slate-100"
                  }`}>
                  <div>
                    <h3 className="font-bold text-lg">Matter Queue</h3>
                    <p className="text-sm text-slate-500 mt-1">Review and manage legal matters escalated by users.</p>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className={`text-left ${isDark ? "bg-slate-950/50" : "bg-slate-50/50"}`}>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Ticket ID</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Identity Details</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Summary</th>
                        <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Assignment Status</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-slate-800" : "divide-slate-100"}`}>
                      {tickets.length === 0 ? (
                        <tr>
                          <td colSpan="4" className="px-8 py-20 text-center text-slate-500">
                            No active tickets in the queue.
                          </td>
                        </tr>
                      ) : (
                        tickets.map((ticket) => (
                          <tr key={ticket.ticket_id} className={`group transition-colors ${isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50/50"
                            }`}>
                            <td className="px-8 py-6">
                              <span className="font-mono text-xs text-slate-500">#{ticket.ticket_id.substring(0, 8)}</span>
                            </td>
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-4">
                                <div className={`h-10 w-10 rounded-xl flex items-center justify-center font-bold text-sm ${isDark ? "bg-indigo-500/10 text-indigo-400" : "bg-indigo-50 text-indigo-600"
                                  }`}>
                                  {(ticket.user_display_name || ticket.user_email || "U").charAt(0).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-bold truncate">{ticket.user_display_name || "Anonymous"}</p>
                                  <p className="text-[10px] text-slate-500 truncate font-medium">{ticket.user_email}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-8 py-6">
                              {!ticket.assigned_lawyer_id && ticket.conversation_summary ? (
                                <div className="max-w-xs">
                                  <p className="text-[11px] text-slate-600 dark:text-slate-400 italic leading-relaxed line-clamp-2">
                                    "{ticket.conversation_summary}"
                                  </p>
                                </div>
                              ) : (
                                <span className="text-[10px] text-slate-500 dark:text-slate-400 font-bold uppercase tracking-widest">
                                  {ticket.assigned_lawyer_id ? "Matter in Progress" : "No Summary"}
                                </span>
                              )}
                            </td>
                            <td className="px-8 py-6 text-right">
                              {ticket.assigned_lawyer_id ? (
                                <div className="flex items-center justify-end gap-2 text-xs font-bold text-slate-400">
                                  <User size={14} />
                                  {users.find(u => u.user_id === ticket.assigned_lawyer_id)?.user_profiles?.display_name || "Legal Team"}
                                </div>
                              ) : (
                                isSystemAdmin ? (
                                  <select
                                    onChange={(e) => handleAssignTicket(ticket.ticket_id, e.target.value)}
                                    className={`text-xs font-bold py-2 px-3 rounded-lg border outline-none ${isDark ? "bg-slate-950 border-slate-800 text-slate-300" : "bg-white border-slate-200 text-slate-600"}`}
                                  >
                                    <option value="">Assign Lawyer...</option>
                                    {users.filter(u => u.role?.toLowerCase() === 'lawyer').map(lawyer => (
                                      <option key={lawyer.user_id} value={lawyer.user_id}>
                                        {lawyer.user_profiles?.display_name || lawyer.email}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className="text-xs text-slate-500 font-semibold italic">Unassigned</span>
                                )
                              )}
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

          {/* VIEW: INQUIRY DISTRIBUTION */}
          {activeView === "distribution" && (
            <div className="space-y-6 animate-in fade-in slide-in-from-right-4 duration-300">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <h1 className="text-2xl font-bold">User Inquiry Domain Distribution</h1>
                <p className="mt-1 text-sm text-slate-500">
                  Analyze the classified domain distribution of all user queries and system interactions.
                </p>
              </div>

              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <h3 className="text-sm font-bold uppercase tracking-widest text-slate-500 mb-6">Classified Categories</h3>
                <div className="h-[400px] w-full">
                  {domainAnalytics && domainAnalytics.distribution && domainAnalytics.distribution.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={domainAnalytics.distribution} layout="vertical">
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" tick={{ fontSize: 10 }} width={150} axisLine={false} tickLine={false} />
                        <Tooltip
                          cursor={false}
                          contentStyle={{
                            backgroundColor: isDark ? '#0f172a' : '#fff',
                            border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                            borderRadius: '8px',
                            fontSize: '10px'
                          }}
                        />
                        <Bar dataKey="queries" fill="#6366f1" radius={[0, 4, 4, 0]} barSize={20} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-slate-500 text-xs font-bold italic opacity-40">
                      No classified user queries recorded yet.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* VIEW: CALENDAR */}
          {activeView === "calendar" && isSystemAdmin && (
            <CalendarView tickets={tickets} role="admin" />
          )}

          {/* VIEW: ADMIN SETTINGS */}
          {activeView === "settings" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <h1 className="text-2xl font-bold">{isSystemAdmin ? "System Admin Settings" : "Admin Settings"}</h1>
                <p className="mt-1 text-sm text-slate-500">
                  Manage your administrative profile and platform-level configuration.
                </p>
              </div>

              {globalMsg && (
                <div className={`p-4 rounded-xl flex items-center justify-between text-sm font-bold ${globalMsg.type === 'success'
                  ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                  : 'bg-red-500/10 text-red-500 border border-red-500/20'
                  }`}>
                  <div className="flex items-center gap-3">
                    {globalMsg.type === 'success' ? <CheckCircle size={18} /> : <AlertTriangle size={18} />}
                    <p>{globalMsg.text}</p>
                  </div>
                  <button onClick={() => setGlobalMsg(null)} className="text-lg opacity-50 hover:opacity-100">&times;</button>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {/* Profile Card */}
                <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <div className={`px-7 py-6 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                    <h2 className="text-lg font-bold">My Profile</h2>
                  </div>
                  <div className="p-7 space-y-6">
                    <div className="flex items-center gap-4">
                      <div className={`h-16 w-16 rounded-2xl flex items-center justify-center font-black text-2xl ${isDark ? "bg-indigo-500/10 text-indigo-400" : "bg-indigo-50 text-indigo-600"}`}>
                        {clerkUser?.firstName?.charAt(0) || "A"}
                      </div>
                      <div>
                        <p className="font-bold text-lg">{clerkUser?.fullName || "Administrator"}</p>
                        <p className="text-sm text-slate-500">{clerkUser?.primaryEmailAddress?.emailAddress}</p>
                      </div>
                    </div>
                    <div className={`p-4 rounded-xl border ${isDark ? "bg-slate-950 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                      <div className="flex justify-between items-center mb-1">
                        <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Security Access</span>
                        <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-500 font-black uppercase text-[9px] tracking-widest border border-purple-500/20">Full Admin</span>
                      </div>
                      <p className="text-xs text-slate-400 italic">Auth session managed via Clerk</p>
                    </div>
                  </div>
                </div>

                {/* Dual-Role Card */}
                <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <div className={`px-7 py-6 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                    <h2 className="text-lg font-bold">Dual-Role Management</h2>
                  </div>
                  <div className="p-7 space-y-6">
                    <p className="text-sm text-slate-500 leading-relaxed">
                      As an administrator, you can enable a parallel <strong>Lawyer Profile</strong>. This allows you to claim and manage cases while retaining full administrative authority.
                    </p>

                    {hasLawyerDashboard ? (
                      <div className={`p-6 rounded-xl border flex flex-col items-center text-center gap-4 ${isDark ? "bg-emerald-500/5 border-emerald-500/20" : "bg-emerald-50 border-emerald-200"}`}>
                        <div className="h-12 w-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center">
                          <CheckCircle size={24} />
                        </div>
                        <div>
                          <h3 className="font-bold text-emerald-500">Lawyer Mode Active</h3>
                          <p className="text-xs text-slate-500 mt-1">You are fully authorized to access the Lawyer Dashboard.</p>
                        </div>
                        <Link
                          to="/lawyer"
                          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold transition-all shadow-lg shadow-indigo-600/20"
                        >
                          Go to Lawyer Dashboard
                        </Link>
                      </div>
                    ) : (
                      <div className={`p-6 rounded-xl border flex flex-col items-center text-center gap-4 ${isDark ? "bg-indigo-500/5 border-indigo-500/20" : "bg-indigo-50 border-indigo-200"}`}>
                        <div className="h-12 w-12 rounded-full bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                          <Scale size={24} />
                        </div>
                        <div>
                          <h3 className="font-bold">Enable Lawyer Features</h3>
                          <p className="text-xs text-slate-500 mt-1">Activate your profile in the lawyer case queue.</p>
                        </div>
                        <button
                          onClick={handleEnableLawyerFeatures}
                          disabled={enablingLawyer}
                          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2"
                        >
                          {enablingLawyer ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus size={16} />}
                          Activate Lawyer Mode
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

        </main>
      </div>

      {/* CONFIRMATION MODAL */}
      {confirmModal.show && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className={`w-full max-w-md rounded-2xl border shadow-2xl overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
            <div className="p-6 border-b border-slate-800/10">
              <div className="flex items-center gap-4 text-red-500 mb-2">
                <AlertTriangle size={24} />
                <h3 className="text-xl font-bold">Suspend User Access?</h3>
              </div>
              <p className="text-sm text-slate-500 leading-relaxed">
                This will deactivate the user account and prevent access to the system immediately.
              </p>
            </div>

            <div className="p-6 bg-slate-50/50 dark:bg-slate-950/20 space-y-4">
              <div className="grid grid-cols-3 gap-2 text-xs">
                <span className="text-slate-500 font-bold uppercase tracking-wider">User:</span>
                <span className="col-span-2 font-bold">{confirmModal.user?.user_profiles?.display_name || "Active Member"}</span>

                <span className="text-slate-500 font-bold uppercase tracking-wider">Email:</span>
                <span className="col-span-2 font-bold truncate">{confirmModal.user?.email}</span>

                <span className="text-slate-500 font-bold uppercase tracking-wider">Role:</span>
                <span className="col-span-2">
                  <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-500 font-black uppercase text-[9px] tracking-widest border border-blue-500/20">
                    {confirmModal.user?.role}
                  </span>
                </span>
              </div>
            </div>

            <div className="p-6 flex items-center justify-end gap-3 border-t border-slate-800/10">
              <button
                onClick={() => setConfirmModal({ show: false, user: null })}
                className={`px-4 py-2 rounded-xl text-sm font-bold transition-colors ${isDark ? "text-slate-400 hover:bg-slate-800" : "text-slate-600 hover:bg-slate-100"}`}
              >
                Cancel
              </button>
              <button
                onClick={() => handleToggleUserStatus(confirmModal.user?.user_id)}
                className="px-6 py-2 bg-red-500 text-white rounded-xl text-sm font-bold shadow-lg shadow-red-500/20 hover:bg-red-600 transition-colors"
              >
                Suspend Access
              </button>
            </div>
          </div>
        </div>
      )}

      {/* USER DETAILS SIDE DRAWER */}
      {viewUser && (
        <>
          <div
            onClick={() => setViewUser(null)}
            className="fixed inset-0 z-[110] bg-slate-950/40 backdrop-blur-[2px] animate-in fade-in duration-300"
          />
          <div className={`fixed inset-y-0 right-0 z-[120] w-full max-w-md shadow-2xl transform transition-transform duration-500 ease-out animate-in slide-in-from-right duration-500 border-l ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-100"
            }`}>
            <div className="flex flex-col h-full">
              {/* Drawer Header */}
              <div className="p-6 border-b border-slate-800/10 flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-bold">User Details</h3>
                  <p className="text-[10px] text-slate-500 mt-1 uppercase font-black tracking-widest">Management Profile</p>
                </div>
                <button
                  onClick={() => setViewUser(null)}
                  className={`p-2 rounded-lg transition-colors ${isDark ? "hover:bg-slate-800 text-slate-400" : "hover:bg-slate-50 text-slate-500"}`}
                >
                  <X size={20} />
                </button>
              </div>

              {/* Drawer Content */}
              <div className="flex-1 overflow-y-auto p-8 space-y-10">
                {/* Profile Header */}
                <div className="flex flex-col items-center text-center">
                  <div className={`h-24 w-24 rounded-3xl flex items-center justify-center font-black text-3xl mb-4 shadow-xl ${isDark ? "bg-indigo-500/10 text-indigo-400" : "bg-indigo-50 text-indigo-600"
                    }`}>
                    {(viewUser.user_profiles?.display_name || viewUser.email || "?").charAt(0).toUpperCase()}
                  </div>
                  <h4 className="text-xl font-bold">{viewUser.user_profiles?.display_name || "Active Member"}</h4>
                  <p className="text-sm text-slate-500">{viewUser.email}</p>

                  <div className="flex gap-2 mt-4">
                    <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border ${viewUser.role === 'admin'
                      ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                      viewUser.role === 'lawyer'
                        ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                        'bg-slate-800 text-slate-400 border-slate-700'
                      }`}>
                      {viewUser.role || 'user'}
                    </span>
                    <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border ${viewUser.status !== 'suspended' && viewUser.status !== 'inactive'
                      ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                      : 'bg-slate-100 text-slate-400 border-slate-200'
                      }`}>
                      {viewUser.status === 'suspended' || viewUser.status === 'inactive' ? 'Suspended' : 'Active'}
                    </span>
                  </div>
                </div>

                {/* Identity Information */}
                <div className="space-y-6">
                  <h5 className="text-[10px] font-black uppercase tracking-widest text-slate-400 border-b pb-2">Identity Details</h5>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-slate-500">System ID</span>
                      <span className="text-xs font-mono font-bold text-indigo-500">#{viewUser.user_id.substring(0, 12)}...</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-slate-500">Joined Date</span>
                      <span className="text-xs font-bold">{new Date(viewUser.created_at).toLocaleDateString(undefined, { dateStyle: 'long' })}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-slate-500">Auth Method</span>
                      <span className="text-xs font-bold flex items-center gap-1.5">
                        <ShieldCheck size={14} className="text-emerald-500" />
                        Clerk Managed
                      </span>
                    </div>
                  </div>
                </div>

                {/* Account Security */}
                <div className="space-y-6">
                  <h5 className="text-[10px] font-black uppercase tracking-widest text-slate-400 border-b pb-2">Account Security</h5>
                  <div className={`p-4 rounded-xl border ${isDark ? "bg-slate-950/50 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                    <p className="text-xs text-slate-500 leading-relaxed italic">
                      This user's authentication and session tokens are managed via Clerk. Administrative actions here will affect platform-level access and database visibility.
                    </p>
                  </div>
                </div>
              </div>

              {/* Drawer Footer */}
              <div className="p-6 border-t border-slate-800/10 bg-slate-50/50 dark:bg-slate-950/20">
                <button
                  onClick={() => setViewUser(null)}
                  className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-lg shadow-indigo-600/20 transition-all flex items-center justify-center gap-2"
                >
                  Close Profile
                </button>
              </div>
            </div>
          </div>
        </>
      )}
      {/* Floating Notifications */}
      {queueMsg && (
        <div className="fixed bottom-8 right-8 z-[200] w-full max-w-md animate-in slide-in-from-bottom-4 duration-500">
          <div className={`p-5 rounded-2xl flex items-center justify-between text-sm font-bold shadow-2xl backdrop-blur-md border ${queueMsg.type === 'success'
            ? 'bg-emerald-600/90 text-white border-emerald-400'
            : 'bg-red-600/90 text-white border-red-400'
            }`}>
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-xl bg-white/20 flex items-center justify-center flex-shrink-0">
                {queueMsg.type === 'success' ? <CheckCircle size={20} /> : <AlertTriangle size={20} />}
              </div>
              <div>
                <p className="text-[10px] opacity-70 uppercase tracking-widest font-black mb-0.5">System Notification</p>
                <p className="leading-tight">{queueMsg.text}</p>
              </div>
            </div>
            <button
              onClick={() => setQueueMsg(null)}
              className="ml-4 p-2 hover:bg-white/10 rounded-lg transition-colors flex-shrink-0"
            >
              <X size={20} />
            </button>
          </div>
        </div>
      )}

      {/* System Notifications (Global Overlay) */}
      {isSystemAdmin && (
        <SystemNotification
          notifications={notifications}
          currentView={activeView}
          onDismiss={handleDismissNotification}
          onNavigate={(view) => {
            setActiveView(view);
            // Optional: handle dismiss on navigate if desired
          }}
          isDark={isDark}
        />
      )}
    </div>
  );
}
