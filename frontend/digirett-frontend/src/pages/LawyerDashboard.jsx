import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import hitlService from "../services/hitlService";
import notesService from "../services/notesService";
import { useUser, useClerk } from "@clerk/clerk-react";
import CalendarView from "../components/common/CalendarView";
import {
  Calendar,
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
  UserX,
  Star,
  ChevronDown,
  BarChart3
} from "lucide-react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis
} from 'recharts';
import { useTheme } from "../providers/ThemeProvider";
import { Link } from "react-router-dom";
import SystemNotification from "../components/chat/ResolutionNotification";
import { useResponsive } from "../hooks/useResponsive";

const DOMAIN_DISPLAY_NAMES = {
  "arbeidsrett": "Employment Law (Arbeidsrett)",
  "arsregnskap_og_selskapsrapportering": "Financial Statements & Reporting (Årsregnskap og Selskapsrapportering)",
  "avtalerett": "Contract Law (Avtalerett)",
  "inkasso_og_tvangsfullbyrdelse": "Debt Collection & Enforcement (Inkasso og Tvangsfullbyrdelse)",
  "konkursrett_og_insolvens": "Bankruptcy & Insolvency (Konkursrett og Insolvens)",
  "manda_fusjon_fisjon": "M&A, Mergers & Acquisitions (M&A, Fusjon, Fisjon)",
  "obligasjonsrett": "Law of Obligations (Obligasjonsrett)",
  "panterett_og_sikkerhetsrett": "Liens & Security Rights (Panterett og Sikkerhetsrett)",
  "pengekravsrett_fordringer": "Monetary Claims & Debt (Pengekravsrett og Fordringer)",
  "personvern_gdpr_business_compliance": "Privacy & GDPR Compliance (Personvern, GDPR & Compliance)",
  "selskapsrett": "Company Law (Selskapsrett)",
  "tvistelosning_smb": "Dispute Resolution for SMBs (Tvisteløsning, SMB)"
};

const LEGAL_DOMAINS = [
  { key: "arbeidsrett", en: "Employment Law", no: "Arbeidsrett" },
  { key: "arsregnskap_og_selskapsrapportering", en: "Financial Statements & Reporting", no: "Årsregnskap og Selskapsrapportering" },
  { key: "avtalerett", en: "Contract Law", no: "Avtalerett" },
  { key: "inkasso_og_tvangsfullbyrdelse", en: "Debt Collection & Enforcement", no: "Inkasso og Tvangsfullbyrdelse" },
  { key: "konkursrett_og_insolvens", en: "Bankruptcy & Insolvency", no: "Konkursrett og Insolvens" },
  { key: "manda_fusjon_fisjon", en: "M&A, Mergers & Acquisitions", no: "M&A, Fusjon, Fisjon" },
  { key: "obligasjonsrett", en: "Law of Obligations", no: "Obligasjonsrett" },
  { key: "panterett_og_sikkerhetsrett", en: "Liens & Security Rights", no: "Panterett og Sikkerhetsrett" },
  { key: "pengekravsrett_fordringer", en: "Monetary Claims & Debt", no: "Pengekravsrett og Fordringer" },
  { key: "personvern_gdpr_business_compliance", en: "Privacy & GDPR Compliance", no: "Personvern, GDPR & Compliance" },
  { key: "selskapsrett", en: "Company Law", no: "Selskapsrett" },
  { key: "tvistelosning_smb", en: "Dispute Resolution for SMBs", no: "Tvisteløsning, SMB" }
];

export default function LawyerDashboard() {
  const { theme, isDark, toggleTheme } = useTheme();
  const { isMobile } = useResponsive();
  const [queueTickets, setQueueTickets] = useState([]);
  const [resolvedTickets, setResolvedTickets] = useState([]);
  const [activeSummaryModal, setActiveSummaryModal] = useState(null);
  const [ratings, setRatings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const activeView = searchParams.get("view") || "dashboard";
  const setActiveView = (view) => setSearchParams({ view });
  const [isSidebarOpen, setIsSidebarOpen] = useState(window.innerWidth >= 1024);
  const [showProfileDropdown, setShowProfileDropdown] = useState(false);
  const [queueMsg, setQueueMsg] = useState(null);
  const [notes, setNotes] = useState("");
  const [notesList, setNotesList] = useState([]);
  const [currentNoteId, setCurrentNoteId] = useState(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [calEventTypeId, setCalEventTypeId] = useState("");
  const [calApiKey, setCalApiKey] = useState("");
  const [isCalSaving, setIsCalSaving] = useState(false);
  const [isCalConfigured, setIsCalConfigured] = useState(true);
  const [expertiseDomains, setExpertiseDomains] = useState([]);
  const [specializationLabel, setSpecializationLabel] = useState("");
  const [isSpecializationSaving, setIsSpecializationSaving] = useState(false);
  const [isEditingSpecialization, setIsEditingSpecialization] = useState(false);
  const [isBriefExpanded, setIsBriefExpanded] = useState(true);
  const [hasInitializedConfig, setHasInitializedConfig] = useState(false);
  const [personalAnalytics, setPersonalAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [isWorkspaceExpanded, setIsWorkspaceExpanded] = useState(() => {
    const saved = localStorage.getItem("lawyer_workspace_expanded");
    return saved !== null ? JSON.parse(saved) : true;
  });

  useEffect(() => {
    if (activeView === "notes" || activeView === "calendar") {
      setIsWorkspaceExpanded(true);
      localStorage.setItem("lawyer_workspace_expanded", JSON.stringify(true));
    }
  }, [activeView]);

  const notesRef = useRef(null);

  useEffect(() => {
    if (notesRef.current && activeView === "notes") {
      notesRef.current.style.height = "auto";
      notesRef.current.style.height = `${notesRef.current.scrollHeight}px`;
    }
  }, [notes, activeView]);

  const fetchNotes = useCallback(async () => {
    try {
      const data = await notesService.getNotes();
      setNotesList(data || []);
    } catch (err) {
      console.error("Failed to fetch notes:", err);
    }
  }, []);

  useEffect(() => {
    if (activeView === "notes") {
      fetchNotes();
    }
  }, [activeView, fetchNotes]);

  const handleSaveCalConfig = async () => {
    setIsCalSaving(true);
    try {
      await hitlService.updateCalConfig({
        cal_event_type_id: calEventTypeId,
        cal_api_key: calApiKey
      });
      setQueueMsg({ type: "success", text: "Cal.com configuration saved successfully." });
      setIsCalConfigured(true);

      setHasInitializedConfig(false);
    } catch (err) {
      console.error("Failed to save Cal.com config:", err);
      setQueueMsg({ type: "error", text: err.message || "Failed to save configuration." });
    } finally {
      setIsCalSaving(false);
    }
  };

  const handleSaveSpecialization = async () => {
    setIsSpecializationSaving(true);
    try {
      await hitlService.updateSpecialization(expertiseDomains, specializationLabel);
      setQueueMsg({ type: "success", text: "Specialization profile updated successfully." });
      setHasInitializedConfig(false);
      setIsEditingSpecialization(false);
    } catch (err) {
      console.error("Failed to save specialization:", err);
      setQueueMsg({ type: "error", text: err.message || "Failed to update specialization profile." });
    } finally {
      setIsSpecializationSaving(false);
    }
  };

  const handleCancelSpecializationEdit = () => {
    setIsEditingSpecialization(false);
    setHasInitializedConfig(false);
    fetchData();
  };

  const handleSaveNote = async () => {
    if (!noteTitle.trim()) {
      alert("Please enter a title for the note.");
      return;
    }
    if (!notes.trim()) {
      alert("Please enter content for the note.");
      return;
    }
    setIsProcessing(true);
    try {
      if (currentNoteId) {
        await notesService.updateNote(currentNoteId, noteTitle, notes);
        setQueueMsg({ type: "success", text: "Legal note updated successfully." });
      } else {
        await notesService.createNote(noteTitle, notes);
        setQueueMsg({ type: "success", text: "Legal note saved successfully." });
      }
      setNotes("");
      setNoteTitle("");
      setCurrentNoteId(null);
      await fetchNotes();
    } catch (err) {
      console.error("Failed to save note:", err);
      setQueueMsg({ type: "error", text: err.message || "Failed to save note." });
    } finally {
      setIsProcessing(false);
    }
  };

  const handleEditNote = (note) => {
    setCurrentNoteId(note.id);
    setNoteTitle(note.title);
    setNotes(note.content);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDeleteNote = async (noteId) => {
    if (!window.confirm("Are you sure you want to delete this note?")) return;
    try {
      await notesService.deleteNote(noteId);
      setQueueMsg({ type: "success", text: "Legal note deleted successfully." });
      if (currentNoteId === noteId) {
        setNotes("");
        setNoteTitle("");
        setCurrentNoteId(null);
      }
      await fetchNotes();
    } catch (err) {
      console.error("Failed to delete note:", err);
      setQueueMsg({ type: "error", text: err.message || "Failed to delete note." });
    }
  };

  const handleCreateNewNote = () => {
    setCurrentNoteId(null);
    setNoteTitle("");
    setNotes("");
  };

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
      const [queueData, activeData] = await Promise.all([
        hitlService.getQueue(),
        hitlService.getActiveTickets()
      ]);

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

      if (Array.isArray(activeData)) {
        activeData.forEach(ticket => {
          const ticketId = ticket.ticket_id || ticket.id;

          if (ticket.status === "booked" && ticket.booking_confirmed_at) {
            const eventId = `booked_${ticketId}`;

            if (!currentDismissed.includes(eventId)) {
              const userName = ticket.user_name || ticket.user_email || ticket.user_identifier || "A client";
              const meetingTime = new Date(ticket.booking_confirmed_at).toLocaleString();
              newNotifications.push({
                id: eventId,
                type: 'meeting_booked',
                caseRef: ticketId,
                message: `Meeting Scheduled: ${userName} has booked a consultation for ${meetingTime}.`,
                view: 'intake'
              });
            }
          }

          if (ticket.has_unread_messages) {
            const eventId = `unread_msg_${ticketId}_${ticket.latest_unread_message_id || 'default'}`;

            if (!currentDismissed.includes(eventId)) {
              const userName = ticket.user_display_name || ticket.user_name || ticket.user_email || "A client";
              newNotifications.push({
                id: eventId,
                type: 'new_message',
                caseRef: ticketId,
                message: `New Message: ${userName} has sent a new message in pre-consultation.`,
                view: 'intake',
                ticketId: ticketId
              });
            }
          }
        });
      }

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
      const [queueData, resolvedData, activeData, calConfig, ratingsData, personalAnalyticsData] = await Promise.all([
        hitlService.getQueue(),
        hitlService.getResolvedHistory(),
        hitlService.getActiveTickets(),
        hitlService.getCalConfig().catch(() => null),
        hitlService.getLawyerRatings().catch(() => []),
        hitlService.getPersonalAnalytics().catch(() => null)
      ]);
      setQueueTickets(queueData || []);
      setResolvedTickets(resolvedData || []);
      setActiveTickets(activeData || []);
      setRatings(ratingsData || []);
      if (personalAnalyticsData) {
        setPersonalAnalytics(personalAnalyticsData);
      }

      if (calConfig) {
        setIsCalConfigured(!!calConfig.cal_event_type_id && !!calConfig.cal_api_key);

        // Only set the editable form fields if they have not been initialized yet
        if (!hasInitializedConfig) {
          setCalEventTypeId(calConfig.cal_event_type_id || "");
          setCalApiKey(calConfig.cal_api_key || "");
          setExpertiseDomains(calConfig.expertise_domains || []);
          setSpecializationLabel(calConfig.specialization_label || "");
          setHasInitializedConfig(true);
        }
      }

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
    const dataInterval = setInterval(fetchData, 4000);
    const notifInterval = setInterval(checkQueueStatus, 4000);
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

  const handleClaim = async (ticketId) => {
    try {
      await hitlService.claimTicket(ticketId);

      setQueueMsg({ type: "success", text: "You claimed this matter! It is now in your My Intake list." });
      setActiveView("intake");

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
    navigate(`/lawyer/tickets/${ticketId}`);
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

  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return "0m";
    if (seconds < 3600) {
      const mins = Math.round(seconds / 60);
      return `${mins}m`;
    }
    if (seconds < 86400) {
      const hours = Math.round(seconds / 3600);
      return `${hours}h`;
    }
    const days = Math.floor(seconds / 86400);
    const remainingHours = Math.round((seconds % 86400) / 3600);
    if (remainingHours === 0) {
      return `${days}d`;
    }
    return `${days}d ${remainingHours}h`;
  };

  const renderStars = (rating) => {
    const fullStars = Math.floor(rating);
    const hasHalf = rating % 1 !== 0;
    const stars = [];
    for (let i = 1; i <= 5; i++) {
      if (i <= fullStars) {
        stars.push(<Star key={i} size={14} className="fill-amber-400 text-amber-400" />);
      } else if (i === fullStars + 1 && hasHalf) {
        stars.push(<Star key={i} size={14} className="fill-amber-400/50 text-amber-400" />);
      } else {
        stars.push(<Star key={i} size={15} className="text-slate-300 dark:text-slate-600" />);
      }
    }
    return <div className="flex items-center gap-0.5">{stars}</div>;
  };

  const recentResolved = resolvedTickets.slice(0, 5);

  // Dynamic Data Calculations - No more fake values
  const allTickets = [...queueTickets, ...activeTickets, ...resolvedTickets];

  const getSystemLifecycleData = () => {
    if (!personalAnalytics) return [];
    const totalConvs = personalAnalytics.total_conversations || 0;
    const escalated = personalAnalytics.total_escalations || 0;
    
    const botResolved = Math.max(0, totalConvs - escalated);
    const resolvedCount = resolvedTickets.length;
    const activeCount = activeTickets.length;
    const unclaimed = Math.max(0, escalated - (resolvedCount + activeCount));

    return [
      {
        name: "Resolved by AI Bot",
        value: botResolved,
        color: "#10b981" // Emerald green
      },
      {
        name: "Resolved by Lawyer",
        value: resolvedCount,
        color: "#6366f1" // Indigo
      },
      {
        name: "Active with Lawyer",
        value: activeCount,
        color: "#3b82f6" // Blue
      },
      {
        name: "Unclaimed in Queue",
        value: unclaimed,
        color: "#f59e0b" // Amber
      }
    ];
  };

  const systemLifecycleData = getSystemLifecycleData();
  const totalConvsCount = personalAnalytics ? (personalAnalytics.total_conversations || 0) : 0;

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
  }));

  const getIntakeVsResolvedData = () => {
    const dailyStats = {};

    // Initialize past 7 days
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const sKey = d.toISOString().split('T')[0];
      dailyStats[sKey] = {
        date: d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' }),
        claimed: 0,
        resolved: 0
      };
    }

    // Process claimed tickets (assigned_at)
    const myTickets = [...activeTickets, ...resolvedTickets];
    myTickets.forEach(t => {
      if (t.assigned_at) {
        const claimDate = new Date(t.assigned_at).toISOString().split('T')[0];
        if (dailyStats[claimDate]) {
          dailyStats[claimDate].claimed += 1;
        }
      }
    });

    // Process resolved tickets (resolved_at)
    resolvedTickets.forEach(t => {
      if (t.resolved_at) {
        const resDate = new Date(t.resolved_at).toISOString().split('T')[0];
        if (dailyStats[resDate]) {
          dailyStats[resDate].resolved += 1;
        }
      }
    });

    return Object.entries(dailyStats).map(([sortKey, data]) => ({
      date: data.date,
      "Claimed": data.claimed,
      "Resolved": data.resolved
    }));
  };

  const intakeVsResolvedData = getIntakeVsResolvedData();

  const totalRating = ratings.reduce((sum, r) => sum + r.rating, 0);
  const avgRating = ratings.length > 0 ? (totalRating / ratings.length).toFixed(1) : "N/A";

  const stats = [
    { label: "Matter Queue", value: queueTickets.length, icon: Ticket, color: "indigo" },
    { label: "My Intake", value: activeTickets.length, icon: Activity, color: "blue" },
    { label: "Resolved", value: resolvedTickets.length, icon: CheckCircle2, color: "emerald" }
  ];

  const personalStats = personalAnalytics ? [
    {
      label: "MATTERS THIS WEEK",
      value: personalAnalytics.cases_this_week,
      subtext: "Total matters resolved during the current week",
      icon: Calendar,
      color: "text-emerald-500",
      bgColor: "bg-emerald-500/10"
    },
    {
      label: "AVG RESPONSE TIME",
      value: formatDuration(personalAnalytics.avg_response_time_seconds),
      subtext: "Average claim speed (time to claim from queue)",
      icon: Clock,
      color: "text-amber-500",
      bgColor: "bg-amber-500/10"
    },
    {
      label: "AVG RESOLUTION TIME",
      value: formatDuration(personalAnalytics.avg_resolution_time_seconds),
      subtext: "Average solve duration after claiming matter",
      icon: CheckCircle2,
      color: "text-blue-500",
      bgColor: "bg-blue-500/10"
    },
    {
      label: "ACCEPTANCE RATE",
      value: `${personalAnalytics.acceptance_rate_percentage}%`,
      subtext: "Percentage of total queue matters claimed by you",
      icon: Scale,
      color: "text-pink-500",
      bgColor: "bg-pink-500/10"
    },
    {
      label: "CUSTOMER RATING",
      value: personalAnalytics.average_rating || "N/A",
      subtext: "Average score of post-consultation feedback",
      icon: Star,
      color: "text-amber-500",
      bgColor: "bg-amber-500/10"
    }
  ] : [];

  return (
    <div className={`flex flex-col lg:flex-row h-dynamic-screen lg:h-screen overflow-hidden ${isDark ? "bg-[#020617] text-slate-200" : "bg-[#f1f5f9] text-slate-900"}`}>

      {/* Sidebar Overlay for Mobile */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-950/60 z-40 lg:hidden backdrop-blur-sm transition-opacity duration-300"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* SIDEBAR */}
      <aside className={`fixed lg:relative z-50 inset-y-0 left-0 w-64 transform transition-transform duration-300 ease-in-out border-r ${isDark ? "bg-slate-900 border-slate-800" : "bg-[#0f172a] border-slate-800"
        } ${isSidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>

        <div className="flex flex-col h-full">
          {/* Sidebar Header */}
          <div className="h-16 flex items-center px-6 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg overflow-hidden flex items-center justify-center">
                <img src="/user-chat-logo.png" alt="Logo" className="w-full h-full object-contain p-0.5" />
              </div>
              <span className="font-bold text-lg tracking-tight text-white">Lawyer Panel</span>
            </div>
            <button onClick={() => setIsSidebarOpen(false)} className="lg:hidden ml-auto text-slate-400">
              <X size={18} />
            </button>
          </div>

          {/* Navigation Sections */}
          <div className="flex-1 px-3 py-6 overflow-y-auto">
            <nav className="space-y-1">
              {/* Dashboard */}
              <button
                onClick={() => { setActiveView("dashboard"); setIsSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "dashboard" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                  }`}
              >
                <LayoutDashboard size={18} />
                Dashboard
              </button>

              {/* Matter Queue */}
              <button
                onClick={() => { setActiveView("queue"); setIsSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "queue" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                  }`}
              >
                <ClipboardList size={18} />
                Matter Queue
                <span className="ml-auto bg-white/10 text-white px-1.5 py-0.5 rounded text-[10px]">{queueTickets.length}</span>
              </button>

              {/* My Intake */}
              <button
                onClick={() => { setActiveView("intake"); setIsSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "intake" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                  }`}
              >
                <Inbox size={18} />
                My Intake
                {activeTickets.length > 0 && (
                  <span className="ml-auto bg-white/10 text-white px-1.5 py-0.5 rounded text-[10px]">{activeTickets.length}</span>
                )}
              </button>

              {/* Resolved Matters */}
              <button
                onClick={() => { setActiveView("resolved"); setIsSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "resolved" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                  }`}
              >
                <CheckCircle size={18} />
                Resolved Matters
                <span className="ml-auto text-slate-500 text-[10px]">{resolvedTickets.length}</span>
              </button>

              {/* Specialization */}
              <button
                onClick={() => { setActiveView("specialization"); setIsSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${activeView === "specialization" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                  }`}
              >
                <Scale size={18} />
                Specialization
              </button>

              {/* Workspace Collapsible Section */}
              <div className="pt-1">
                <button
                  onClick={() => {
                    const nextVal = !isWorkspaceExpanded;
                    setIsWorkspaceExpanded(nextVal);
                    localStorage.setItem("lawyer_workspace_expanded", JSON.stringify(nextVal));
                  }}
                  className="w-full flex items-center justify-between px-4 py-2.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-all text-left"
                >
                  <div className="flex items-center gap-3">
                    <Briefcase size={18} />
                    <span className="text-sm font-semibold tracking-wide">Workspace</span>
                  </div>
                  <ChevronDown
                    size={16}
                    className={`transform transition-transform duration-200 ${isWorkspaceExpanded ? "rotate-180" : ""}`}
                  />
                </button>

                {isWorkspaceExpanded && (
                  <div className="space-y-1 mt-1 pl-4 border-l border-white/10 ml-6">
                    {/* Notes */}
                    <button
                      onClick={() => { setActiveView("notes"); setIsSidebarOpen(false); }}
                      className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeView === "notes" ? "bg-indigo-600/90 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"
                        }`}
                    >
                      <Bookmark size={16} />
                      Notes
                    </button>

                    {/* Schedules */}
                    <button
                      onClick={() => { setActiveView("calendar"); setIsSidebarOpen(false); }}
                      className={`w-full flex items-center gap-3 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${activeView === "calendar" ? "bg-indigo-600/90 text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
                    >
                      <Calendar size={16} />
                      Schedules
                    </button>
                  </div>
                )}
              </div>

              {/* Go to Chat */}
              <div className="pt-1">
                <Link
                  to="/chat"
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold text-slate-400 hover:text-white hover:bg-white/5 transition-all"
                >
                  <ArrowLeft size={18} />
                  Go to Chat
                </Link>

                {/* Admin Dashboard */}
                {(clerkUser?.publicMetadata?.role === "admin" || clerkUser?.publicMetadata?.role === "system_admin") && (
                  <Link
                    to="/admin"
                    className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-semibold text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/5 transition-all border border-indigo-500/20 mt-4"
                  >
                    <Shield size={18} />
                    Admin Dashboard
                  </Link>
                )}
              </div>
            </nav>
          </div>

          {/* Bottom Fixed Action */}
          <div className="p-4 border-t border-white/5 mt-auto">
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-bold text-slate-400 hover:text-red-400 hover:bg-red-500/5 transition-all"
            >
              <LogOut size={18} />
              Logout
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT AREA */}
      <div className="flex-1 flex flex-col min-w-0 relative h-full">
        {/* Header */}
        <header className={`sticky top-0 z-40 border-b shadow-sm backdrop-blur-md ${isMobile ? "px-4 py-3" : "px-6 py-4"} ${isDark ? "bg-gray-900/80 border-gray-800" : "bg-white/80 border-gray-100"
          }`}>
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <div className={`flex items-center ${isMobile ? "gap-2" : "gap-4"}`}>
              <button onClick={() => setIsSidebarOpen(true)} className="lg:hidden text-slate-500 p-2 hover:bg-slate-100 rounded-xl">
                <Menu size={24} />
              </button>
              <div className={`flex items-center ${isMobile ? "gap-1.5" : "gap-3"}`}>
                <div>
                  <h1 className={`font-bold capitalize ${isMobile ? "text-sm" : "text-lg"} ${isDark ? "text-white" : "text-gray-900"}`}>
                    Lawyer Dashboard
                  </h1>
                </div>
              </div>
            </div>

            <div className={`flex items-center ${isMobile ? "gap-2" : "gap-4"}`}>
              <button
                onClick={toggleTheme}
                className={`p-2 rounded-xl transition-all ${isDark ? "bg-gray-800 text-blue-400 hover:bg-gray-700" : "bg-gray-50 text-gray-500 hover:bg-gray-100"}`}
              >
                {isDark ? <Sun size={18} /> : <Moon size={18} />}
              </button>
              <div className="h-6 w-[1px] bg-gray-200 dark:bg-gray-800 mx-1"></div>
              <div className="relative">
                <button
                  onClick={() => setShowProfileDropdown(!showProfileDropdown)}
                  className={`flex items-center gap-2 p-1 rounded-2xl transition-all ${isDark ? "hover:bg-gray-800" : "hover:bg-gray-50"}`}
                >
                  <div className="h-8 w-8 sm:h-9 sm:w-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold text-sm sm:text-base shrink-0">
                    {clerkUser?.firstName?.charAt(0) || "L"}
                  </div>
                  <div className="hidden md:block text-left">
                    <p className={`text-xs font-bold ${isDark ? "text-white" : "text-gray-900"}`}>{clerkUser?.fullName || "Lawyer"}</p>
                    <p className="text-[10px] text-gray-500">Professional ID: {clerkUser?.id?.slice(-4).toUpperCase() || "8829"}</p>
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
                        onClick={() => { setActiveView("settings"); setShowProfileDropdown(false); }}
                        className={`w-full px-3 py-2 flex items-center gap-3 rounded-lg text-xs font-bold transition-colors ${isDark ? "text-slate-300 hover:bg-slate-800" : "text-slate-600 hover:bg-slate-50"
                          }`}
                      >
                        <Settings size={14} />
                        Settings
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

          {/* Cal.com Configuration Warning Banner */}
          {!isCalConfigured && activeView !== "settings" && (
            <div className={`mb-8 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border animate-in fade-in slide-in-from-top-4 duration-300 ${isDark ? "bg-amber-500/10 border-amber-500/20" : "bg-amber-50 border-amber-200"}`}>
              <div className="flex items-center gap-3">
                <div className={`h-10 w-10 rounded-xl flex items-center justify-center shrink-0 ${isDark ? "bg-amber-500/20 text-amber-500" : "bg-amber-100 text-amber-600"}`}>
                  <AlertTriangle size={20} />
                </div>
                <div>
                  <h3 className={`font-bold text-sm ${isDark ? "text-amber-400" : "text-amber-800"}`}>Action Required: Calendar Configuration Missing</h3>
                  <p className={`text-xs mt-0.5 ${isDark ? "text-amber-500/80" : "text-amber-700/80"}`}>
                    Your Cal.com scheduling integration is incomplete. Please configure it so users can book consultations.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setActiveView("settings")}
                className={`px-4 py-2 text-xs font-bold rounded-lg whitespace-nowrap transition-all shadow-sm ${isDark ? "bg-amber-500 text-amber-950 hover:bg-amber-400" : "bg-amber-500 text-white hover:bg-amber-600"}`}
              >
                Configure Now
              </button>
            </div>
          )}

          {/* VIEW: DASHBOARD */}
          {activeView === "dashboard" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-10">

              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-2xl font-black tracking-tight">Lawyer Control Panel</h1>
                  <p className="text-xs text-slate-500 mt-1 font-medium">Real-time oversight of escalated legal matters.</p>
                </div>
              </div>

              {/* Ticket Queue & Intake KPI Cards */}
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 font-bold">Matters Queue & Active Intake</span>
                </div>
                <div className={`grid grid-cols-1 sm:grid-cols-3 ${isMobile ? "gap-3" : "gap-4"}`}>
                  {stats.map((stat, idx) => (
                    <div key={idx} className={`${isMobile ? "p-3.5 gap-1.5" : "p-4 gap-1.5"} rounded-xl border shadow-sm flex flex-col ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"
                      }`}>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">{stat.label}</span>
                      </div>
                      <div className="flex items-baseline gap-1.5">
                        <span className="text-2xl font-black tracking-tighter">{stat.value}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Personal Performance Analytics KPI Cards */}
              {personalAnalytics && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 font-bold">Personal Performance Analytics</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {personalStats.map((stat, idx) => (
                      <div
                        key={idx}
                        className={`${isMobile ? "p-3.5 gap-1.5" : "p-4 gap-1.5"} rounded-xl border shadow-sm flex flex-col justify-between ${
                          isDark ? "bg-slate-900 border-slate-800 text-white" : "bg-white border-slate-200 text-slate-800"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">
                            {stat.label}
                          </span>
                        </div>
                        
                        <div className="flex flex-col gap-0.5">
                          <span className="text-2xl font-black">{stat.value}</span>
                          <span className="text-[10px] text-slate-500 font-medium mt-1">
                            {stat.subtext}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Row 1: Allocation + Trend */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {/* Intake Trend */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-6">Intake Performance</h3>
                  <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={resolutionTrend} margin={{ top: 10, right: 10, left: 15, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                        <XAxis
                          dataKey="date"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          label={{
                            value: "Date (DD/MM)",
                            position: "insideBottom",
                            offset: -15,
                            fill: "#64748b",
                            fontSize: 10,
                            fontWeight: "bold"
                          }}
                        />
                        <YAxis
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          label={{
                            value: "Number of Cases",
                            angle: -90,
                            position: "insideLeft",
                            offset: 0,
                            fill: "#64748b",
                            fontSize: 10,
                            fontWeight: "bold",
                            style: { textAnchor: 'middle' }
                          }}
                        />
                        <Tooltip
                          cursor={false}
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

                {/* Intake vs Resolved Bar Chart */}
                <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-6">Matter Intake vs. Resolved</h3>
                  <div className="h-[200px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={intakeVsResolvedData} margin={{ top: 10, right: 10, left: 15, bottom: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                        <XAxis
                          dataKey="date"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          label={{
                            value: "Date (DD/MM)",
                            position: "insideBottom",
                            offset: -15,
                            fill: "#64748b",
                            fontSize: 10,
                            fontWeight: "bold"
                          }}
                        />
                        <YAxis
                          axisLine={false}
                          tickLine={false}
                          tick={{ fontSize: 10, fill: '#64748b' }}
                          label={{
                            value: "Number of Matters",
                            angle: -90,
                            position: "insideLeft",
                            offset: 0,
                            fill: "#64748b",
                            fontSize: 10,
                            fontWeight: "bold",
                            style: { textAnchor: 'middle' }
                          }}
                        />
                        <Tooltip
                          cursor={false}
                          contentStyle={{
                            backgroundColor: isDark ? '#0f172a' : '#fff',
                            border: `1px solid ${isDark ? '#1e293b' : '#e2e8f0'}`,
                            borderRadius: '8px',
                            fontSize: '10px'
                          }}
                        />
                        <Legend
                          iconType="circle"
                          verticalAlign="top"
                          align="right"
                          wrapperStyle={{
                            paddingBottom: "12px",
                            fontSize: "10px"
                          }}
                        />
                        <Bar dataKey="Claimed" fill="#6366f1" radius={[4, 4, 0, 0]} barSize={12} />
                        <Bar dataKey="Resolved" fill="#10b981" radius={[4, 4, 0, 0]} barSize={12} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>


            </div>
          )}

          {/* VIEW: MATTER QUEUE (ALL OPEN MATTERS) */}
          {activeView === "queue" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className={`px-8 py-5 border-b ${isDark ? "border-slate-800" : "border-slate-100"}`}>
                  <h3 className="font-bold text-lg">Matter Queue</h3>
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

                {isMobile ? (
                  loading ? (
                    <div className="p-8 text-center text-xs font-bold text-slate-400">Loading Queue...</div>
                  ) : queueTickets.length === 0 ? (
                    <div className="p-8 text-center text-xs font-bold text-slate-400 uppercase tracking-widest">No open matters found</div>
                  ) : (
                    <div className="p-4 space-y-4">
                      {queueTickets.map((ticket) => {
                        const isDomainMatch = ticket.detected_domain && expertiseDomains.some(d => d.toLowerCase() === ticket.detected_domain.toLowerCase());
                        return (
                          <div key={ticket.ticket_id} className={`p-4 rounded-xl border flex flex-col gap-3.5 ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                            <div className="flex items-center justify-between gap-3">
                              <div className="flex items-center gap-3 min-w-0">
                                <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold shrink-0">
                                  {(ticket.user_display_name || "U").charAt(0)}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-sm font-bold truncate">{ticket.user_display_name || "Anonymous"}</p>
                                  <p className="text-[10px] text-slate-500 truncate">{ticket.user_email}</p>
                                </div>
                              </div>
                              <span className="font-mono text-xs text-slate-500 shrink-0">#{ticket.ticket_id.substring(0, 8)}</span>
                            </div>
                            {ticket.detected_domain && (
                              <div>
                                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider border ${isDomainMatch
                                  ? (isDark ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-emerald-50 text-emerald-700 border-emerald-200")
                                  : (isDark ? "bg-slate-900 text-slate-400 border-slate-850" : "bg-slate-100 text-slate-600 border-slate-200")
                                  }`}>
                                  {isDomainMatch && <span className="text-emerald-500 font-black">✓</span>}
                                  {DOMAIN_DISPLAY_NAMES[ticket.detected_domain.toLowerCase()] || ticket.detected_domain}
                                </span>
                              </div>
                            )}
                            <p
                              onClick={() => {
                                if (ticket.conversation_summary) {
                                  setActiveSummaryModal(ticket.conversation_summary);
                                }
                              }}
                              className="text-xs text-slate-500 italic leading-relaxed line-clamp-3 cursor-pointer"
                              title={ticket.conversation_summary ? "Click to view full summary" : ""}
                            >
                              {ticket.conversation_summary || "No summary available."}
                            </p>
                            <div className="pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex justify-end">
                              <button onClick={() => handleClaim(ticket.ticket_id)} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 transition-all">
                                Claim Matter
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Ticket ID</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Identity Details</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Summary</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className={`divide-y ${isDark ? "divide-slate-800" : "divide-slate-100"}`}>
                        {loading ? (
                          <tr><td colSpan="4" className="px-8 py-20 text-center text-xs font-bold text-slate-400">Loading Queue...</td></tr>
                        ) : queueTickets.length === 0 ? (
                          <tr><td colSpan="4" className="px-8 py-20 text-center text-xs font-bold text-slate-400 uppercase tracking-widest">No open matters found</td></tr>
                        ) : (
                          queueTickets.map((ticket) => {
                            const isDomainMatch = ticket.detected_domain && expertiseDomains.some(d => d.toLowerCase() === ticket.detected_domain.toLowerCase());
                            return (
                              <tr key={ticket.ticket_id} className={`group transition-colors ${isDark ? "hover:bg-slate-800/30" : "hover:bg-slate-50/50"}`}>
                                <td className="px-8 py-6">
                                  <span className="font-mono text-xs text-slate-500">#{ticket.ticket_id.substring(0, 8)}</span>
                                </td>
                                <td className="px-8 py-6">
                                  <div className="flex items-center gap-4">
                                    <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold">{(ticket.user_display_name || "U").charAt(0)}</div>
                                    <div>
                                      <p className="text-sm font-bold flex items-center gap-2">
                                        {ticket.user_display_name || "Anonymous"}
                                      </p>
                                      <p className="text-[10px] text-slate-500">{ticket.user_email}</p>
                                      {ticket.detected_domain && (
                                        <p className="mt-1.5">
                                          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg text-[9px] font-black uppercase tracking-wider border ${isDomainMatch
                                            ? (isDark ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-emerald-50 text-emerald-700 border-emerald-200")
                                            : (isDark ? "bg-slate-900 text-slate-400 border-slate-800" : "bg-slate-100 text-slate-600 border-slate-200")
                                            }`}>
                                            {isDomainMatch && <span className="text-emerald-500 font-black">✓</span>}
                                            {DOMAIN_DISPLAY_NAMES[ticket.detected_domain.toLowerCase()] || ticket.detected_domain}
                                          </span>
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                </td>
                                <td className="px-8 py-6">
                                  <p
                                    onClick={() => {
                                      if (ticket.conversation_summary) {
                                        setActiveSummaryModal(ticket.conversation_summary);
                                      }
                                    }}
                                    className="text-xs text-slate-500 italic leading-relaxed line-clamp-2 max-w-xs cursor-pointer transition-all"
                                    title={ticket.conversation_summary ? "Click to view full summary" : ""}
                                  >
                                    {ticket.conversation_summary || "No summary available."}
                                  </p>
                                </td>
                                <td className="px-8 py-6 text-right">
                                  <button onClick={() => handleClaim(ticket.ticket_id)} className="px-4 py-2 border border-slate-200 rounded-lg text-xs font-bold hover:bg-slate-50 transition-all">Claim Matter</button>
                                </td>
                              </tr>
                            )
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeView === "intake" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              {activeTickets.length > 0 ? (
                <div className={`border rounded-2xl shadow-sm overflow-hidden ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  {isMobile ? (
                    <div className="p-4 space-y-4">
                      {activeTickets.map((t) => (
                        <div key={t.ticket_id} className={`p-4 rounded-xl border flex flex-col gap-3.5 ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                          <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold shrink-0">
                              {(t.user_display_name || "U").charAt(0)}
                            </div>
                            <div className="min-w-0">
                              <p className="text-sm font-bold truncate flex items-center gap-2">
                                {t.user_display_name || "Anonymous"}
                              </p>
                              <p className="text-[10px] text-slate-500 truncate">{t.user_email}</p>
                              {(t.outcome_notes?.includes("[USER-NO-SHOW]") || t.outcome_notes?.includes("[BOTH-NO-SHOW]")) && (
                                <div className="mt-1 flex items-center gap-1 text-[9px] font-black text-red-500 uppercase tracking-tighter">
                                  <AlertTriangle size={10} />
                                  <span>Missed Appointment</span>
                                </div>
                              )}
                            </div>
                          </div>

                          <p
                            onClick={() => {
                              const displaySummary = t.conversation_summary || t.user_note;
                              if (displaySummary) {
                                setActiveSummaryModal(displaySummary);
                              }
                            }}
                            className="text-xs text-slate-500 italic leading-relaxed line-clamp-3 cursor-pointer"
                            title={t.conversation_summary || t.user_note ? "Click to view full summary" : ""}
                          >
                            {t.conversation_summary || t.user_note || "No summary available."}
                          </p>

                          <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100 dark:border-slate-850">
                            <div className="flex flex-col gap-0.5">
                              <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Claimed At</span>
                              <span className="font-semibold text-slate-450 dark:text-slate-400">{formatDate(t.assigned_at)}</span>
                            </div>
                            <div className="flex flex-col items-end gap-0.5">
                              <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Scheduled For</span>
                              {t.booking_confirmed_at ? (
                                <span className="font-bold text-slate-900 dark:text-slate-200">{formatDate(t.booking_confirmed_at)}</span>
                              ) : (
                                <span className="font-medium text-slate-400">Not Scheduled</span>
                              )}
                            </div>
                          </div>

                          <div className="pt-1 flex justify-end">
                            <button
                              onClick={() => handleWorkOn(t.ticket_id)}
                              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition-all"
                            >
                              Work on this
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Summary</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">Claimed At</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">Scheduled For</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {activeTickets.map((t) => (
                          <tr key={t.ticket_id} className="hover:bg-slate-50/50 transition-colors">
                            <td className="px-8 py-6">
                              <div className="flex items-center gap-4">
                                <div className="h-10 w-10 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center font-bold">{(t.user_display_name || "U").charAt(0)}</div>
                                <div>
                                  <p className="text-sm font-bold flex items-center gap-2">
                                    {t.user_display_name || "Anonymous"}
                                  </p>
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
                            <td className="px-8 py-6">
                              <p
                                onClick={() => {
                                  const displaySummary = t.conversation_summary || t.user_note;
                                  if (displaySummary) {
                                    setActiveSummaryModal(displaySummary);
                                  }
                                }}
                                className="text-xs text-slate-500 italic leading-relaxed line-clamp-2 max-w-xs cursor-pointer transition-all"
                                title={t.conversation_summary || t.user_note ? "Click to view full summary" : ""}
                              >
                                {t.conversation_summary || t.user_note || "No summary available."}
                              </p>
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
                  )}
                </div>
              ) : (
                <div className="py-32 text-center text-slate-400">
                  <Inbox size={40} className="mx-auto mb-6 opacity-20" />
                  <p className="text-xs font-bold uppercase tracking-widest">No active intake found</p>
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
                    <h2 className="text-base font-bold">Resolved Matter History</h2>
                    <p className="text-xs text-slate-500 mt-1">Matters you have successfully addressed and resolved.</p>
                  </div>
                  {isMobile ? (
                    <div className="p-4 space-y-4">
                      {resolvedTickets.map((t) => {
                        const ticketRating = ratings.find(r => r.ticket_id === t.ticket_id);
                        return (
                          <div key={t.ticket_id} className={`p-4 rounded-xl border flex flex-col gap-3.5 ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50 border-slate-200"}`}>
                            <div className="flex items-center gap-3">
                              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center font-bold shrink-0">
                                {(t.user_display_name || "U").charAt(0)}
                              </div>
                              <div className="min-w-0">
                                <p className="text-sm font-bold truncate">{t.user_display_name || "Anonymous"}</p>
                                <p className="text-[10px] text-slate-500 truncate">{t.user_email}</p>
                              </div>
                            </div>

                            <p
                              onClick={() => {
                                const displaySummary = t.conversation_summary || t.user_note;
                                if (displaySummary) {
                                  setActiveSummaryModal(displaySummary);
                                }
                              }}
                              className="text-xs text-slate-500 italic leading-relaxed line-clamp-3 cursor-pointer"
                              title={t.conversation_summary || t.user_note ? "Click to view full summary" : ""}
                            >
                              {t.conversation_summary || t.user_note || "No summary available."}
                            </p>

                            <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100 dark:border-slate-850">
                              <div className="flex flex-col gap-0.5">
                                <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Resolved At</span>
                                <span className="font-semibold text-slate-450 dark:text-slate-400">{formatDate(t.resolved_at)}</span>
                              </div>
                              <div className="flex flex-col items-end gap-0.5">
                                <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">Rating</span>
                                {ticketRating ? (
                                  <div className="inline-flex items-center gap-1 bg-amber-500/10 text-amber-500 px-2 py-0.5 rounded-lg text-[10px] font-bold border border-amber-500/20">
                                    <span>★ {ticketRating.rating}</span>
                                  </div>
                                ) : (
                                  <span className="font-semibold text-slate-400">—</span>
                                )}
                              </div>
                            </div>
                            <div className="flex justify-end pt-1">
                              <button onClick={() => navigate(`/lawyer/tickets/${t.ticket_id}`)} className="text-indigo-500 text-xs font-bold hover:underline">
                                View Details
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="text-left border-b border-slate-100 dark:border-slate-800">
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Matter Summary</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500">Resolved At</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-center">Rating</th>
                          <th className="px-8 py-5 text-[10px] font-black uppercase tracking-widest text-slate-500 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {resolvedTickets.map((t) => {
                          const ticketRating = ratings.find(r => r.ticket_id === t.ticket_id);
                          return (
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
                              <td className="px-8 py-6">
                                <p
                                  onClick={() => {
                                    const displaySummary = t.conversation_summary || t.user_note;
                                    if (displaySummary) {
                                      setActiveSummaryModal(displaySummary);
                                    }
                                  }}
                                  className="text-xs text-slate-500 italic leading-relaxed line-clamp-2 max-w-xs cursor-pointer transition-all"
                                  title={t.conversation_summary || t.user_note ? "Click to view full summary" : ""}
                                >
                                  {t.conversation_summary || t.user_note || "No summary available."}
                                </p>
                              </td>
                              <td className="px-8 py-6 text-xs font-medium text-slate-500">{formatDate(t.resolved_at)}</td>
                              <td className="px-8 py-6 text-center">
                                {ticketRating ? (
                                  <div className="inline-flex items-center gap-1 bg-amber-500/10 text-amber-500 px-2.5 py-0.5 rounded-lg text-xs font-bold border border-amber-500/20">
                                    <span>{ticketRating.rating}</span>
                                  </div>
                                ) : (
                                  <span className="text-xs text-slate-400 font-medium">—</span>
                                )}
                              </td>
                              <td className="px-8 py-6 text-right">
                                <button onClick={() => navigate(`/lawyer/tickets/${t.ticket_id}`)} className="text-indigo-500 text-xs font-bold hover:underline">View Details</button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
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
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-10">
              <div className="flex flex-col md:flex-row gap-8">

                {/* NOTE EDITOR (Left Column / Main Section) */}
                <div className={`flex-1 p-8 rounded-2xl border shadow-sm h-fit ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                  <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-2xl bg-amber-500/10 text-amber-500 flex items-center justify-center">
                        <Bookmark size={24} />
                      </div>
                      <div>
                        <h2 className="text-xl font-bold">{currentNoteId ? "Edit Legal Note" : "Create Legal Note"}</h2>
                        <p className="text-xs text-slate-500 mt-1">Personal workspace for drafting thoughts and case references.</p>
                      </div>
                    </div>
                    {currentNoteId && (
                      <button
                        onClick={handleCreateNewNote}
                        className={`px-4 py-2 text-xs font-bold rounded-xl border transition-all ${isDark ? "border-slate-700 text-slate-300 hover:bg-slate-800" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                      >
                        Create New Note
                      </button>
                    )}
                  </div>

                  {queueMsg && (
                    <div className={`mb-6 p-4 rounded-xl flex items-center justify-between text-sm font-bold animate-in fade-in zoom-in-95 ${queueMsg.type === 'success'
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

                  <div className="space-y-6">
                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Note Title</label>
                      <input
                        type="text"
                        value={noteTitle}
                        onChange={(e) => setNoteTitle(e.target.value)}
                        placeholder="Enter note title..."
                        className={`w-full px-5 py-3.5 rounded-xl border text-sm font-medium focus:ring-0 focus:outline-none transition-all ${isDark ? "bg-slate-950/50 border-slate-800 text-white focus:border-indigo-500" : "bg-slate-50 border-slate-200 text-slate-800 focus:border-indigo-500"}`}
                      />
                    </div>

                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Note Content</label>
                      <textarea
                        ref={notesRef}
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Type your note details here..."
                        style={{ height: 'auto', minHeight: '120px' }}
                        className={`w-full p-6 rounded-2xl border text-sm bg-transparent focus:ring-0 resize-none overflow-hidden font-medium leading-relaxed focus:outline-none focus:border-indigo-500 ${isDark ? "bg-slate-950/50 border-slate-800 text-slate-300" : "bg-slate-50 border-slate-200 text-slate-600"}`}
                      />
                    </div>

                    <div className="flex justify-end gap-3 mt-6">
                      <button
                        onClick={handleSaveNote}
                        disabled={isProcessing}
                        className="px-8 py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl text-xs font-black uppercase tracking-widest shadow-xl shadow-indigo-600/20 transition-all disabled:opacity-50"
                      >
                        {isProcessing ? "Saving..." : currentNoteId ? "Update Note" : "Save Legal Note"}
                      </button>
                    </div>
                  </div>
                </div>

                {/* PAST NOTES HISTORY (Right Column / Sidebar) */}
                <div className="w-full md:w-[380px] space-y-6">
                  <div className={`p-6 rounded-2xl border shadow-sm max-h-[640px] flex flex-col ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                    <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4">Past Notes</h3>

                    <div className="overflow-y-auto space-y-4 pr-1 flex-1">
                      {notesList.length === 0 ? (
                        <div className="py-20 text-center text-slate-400">
                          <Bookmark size={28} className="mx-auto mb-4 opacity-20" />
                          <p className="text-[10px] font-black uppercase tracking-widest">No saved notes found</p>
                        </div>
                      ) : (
                        notesList.map((note) => (
                          <div
                            key={note.id}
                            onClick={() => handleEditNote(note)}
                            className={`p-4 rounded-xl border transition-all flex flex-col justify-between gap-3 cursor-pointer ${currentNoteId === note.id
                              ? (isDark ? "bg-indigo-500/10 border-indigo-500/50" : "bg-indigo-50 border-indigo-300")
                              : (isDark ? "bg-slate-950/40 border-slate-800/80 hover:border-slate-700" : "bg-slate-50/50 border-slate-100 hover:border-slate-200")
                              }`}
                          >
                            <div>
                              <div className="flex items-start justify-between gap-2">
                                <h4 className="text-xs font-bold truncate max-w-[180px]">{note.title}</h4>
                                <span className="text-[9px] text-slate-400 font-medium whitespace-nowrap">{formatDate(note.updated_at)}</span>
                              </div>
                              <p className="text-[11px] text-slate-500 mt-2 line-clamp-3 leading-relaxed">
                                {note.content}
                              </p>
                            </div>
                            <div className="flex items-center justify-end gap-2 border-t pt-3 border-slate-100 dark:border-slate-800/80">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleEditNote(note);
                                }}
                                className={`px-2.5 py-1 rounded text-[9px] font-black uppercase tracking-widest transition-all ${isDark ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                  }`}
                              >
                                Edit
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteNote(note.id);
                                }}
                                className="px-2.5 py-1 rounded text-[9px] font-black uppercase tracking-widest bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-all"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

              </div>
            </div>
          )}

          {/* VIEW: SETTINGS */}
          {activeView === "settings" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className="flex items-center gap-4 mb-8">
                  <div className="h-12 w-12 rounded-2xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                    <Settings size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight">Integration Settings</h2>
                    <p className="text-sm text-slate-500 mt-1">Configure your personal calendar via Cal.com</p>
                  </div>
                </div>

                {queueMsg && activeView === "settings" && (
                  <div className={`mb-6 p-4 rounded-xl flex items-center justify-between text-sm font-bold animate-in fade-in zoom-in-95 ${queueMsg.type === 'success'
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

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                  <div className="space-y-6">
                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Event Type ID</label>
                      <input
                        type="text"
                        value={calEventTypeId}
                        onChange={(e) => setCalEventTypeId(e.target.value)}
                        placeholder="Enter your Event Type ID"
                        autoComplete="off"
                        className={`w-full px-4 py-3 rounded-xl border text-sm transition-all focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 ${isDark ? "bg-slate-950 border-slate-800 text-white placeholder-slate-600" : "bg-slate-50 border-slate-200 text-slate-900 placeholder-slate-400"}`}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Cal.com API Key</label>
                      <input
                        type="password"
                        value={calApiKey}
                        onChange={(e) => setCalApiKey(e.target.value)}
                        placeholder="Enter your API Key"
                        autoComplete="new-password"
                        className={`w-full px-4 py-3 rounded-xl border text-sm transition-all focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 ${isDark ? "bg-slate-950 border-slate-800 text-white placeholder-slate-600" : "bg-slate-50 border-slate-200 text-slate-900 placeholder-slate-400"}`}
                      />
                    </div>
                    <button
                      onClick={handleSaveCalConfig}
                      disabled={isCalSaving}
                      className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
                    >
                      {isCalSaving ? "Saving..." : "Save Configuration"}
                    </button>
                  </div>

                  <div className={`p-6 rounded-2xl border ${isDark ? "bg-indigo-500/5 border-indigo-500/10 text-indigo-200" : "bg-indigo-50 border-indigo-100 text-indigo-900"}`}>
                    <h3 className="font-bold flex items-center gap-2 mb-4">
                      <ExternalLink size={18} />
                      How to configure your Cal.com schedule
                    </h3>
                    <ol className="list-decimal list-inside space-y-3 text-sm font-medium opacity-80 leading-relaxed">
                      <li>Sign up for a free personal account at <a href="https://cal.com" target="_blank" rel="noreferrer" className="underline font-bold">Cal.com</a>.</li>
                      <li>Connect your preferred calendar (Google/Outlook) in Cal.com Settings.</li>
                      <li>Create a new Event Type (e.g., "Legal Consultation").</li>
                      <li>Go to <b>Settings &gt; Security &gt; API Keys</b> and generate an API key. Paste it in the API Key field here.</li>
                      <li>Find your <b>Event Type ID</b> (the number at the end of the URL when editing the event type in Cal.com) and paste it here.</li>
                    </ol>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* VIEW: SPECIALIZATION */}
          {activeView === "specialization" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className="flex items-center gap-4 mb-8">
                  <div className="h-12 w-12 rounded-2xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                    <Scale size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight">Legal Expertise & Specialization</h2>
                    <p className="text-sm text-slate-500 mt-1">Select the legal domains you specialize in to get prioritized in the queue</p>
                  </div>
                </div>

                {queueMsg && activeView === "specialization" && (
                  <div className={`mb-6 p-4 rounded-xl flex items-center justify-between text-sm font-bold animate-in fade-in zoom-in-95 ${queueMsg.type === 'success'
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

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
                  <div className="lg:col-span-2 space-y-6">

                    <div>
                      <label className="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">
                        {isEditingSpecialization ? "Expertise Areas (Select all that apply)" : "Your Specializations"}
                      </label>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {isEditingSpecialization ? (
                          <>
                            {/* Common (Generalist) Checkbox */}
                            <label
                              key="common"
                              className={`p-4 rounded-xl border flex items-start gap-3 select-none transition-all cursor-pointer ${
                                expertiseDomains.some(d => d.toLowerCase() === "common")
                                  ? (isDark ? "bg-indigo-500/10 border-indigo-500/40 text-white" : "bg-indigo-50 border-indigo-200 text-indigo-900")
                                  : (isDark ? "bg-slate-950/40 border-slate-800/50 hover:border-slate-750 text-slate-400" : "bg-white border-slate-200 hover:border-slate-300 text-slate-600")
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={expertiseDomains.some(d => d.toLowerCase() === "common")}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setExpertiseDomains(prev => [...prev, "Common"]);
                                  } else {
                                    setExpertiseDomains(prev => prev.filter(d => d.toLowerCase() !== "common"));
                                  }
                                }}
                                className="mt-1 rounded text-indigo-600 focus:ring-indigo-500"
                              />
                              <div>
                                <span className="text-xs font-bold block">Generalist (Common)</span>
                                <span className="text-[10px] opacity-60 block mt-0.5">Receives matches for all case domains</span>
                              </div>
                            </label>

                            {LEGAL_DOMAINS.map((domain) => {
                              const isChecked = expertiseDomains.some(d => d.toLowerCase() === domain.key.toLowerCase());
                              return (
                                <label
                                  key={domain.key}
                                  className={`p-4 rounded-xl border flex items-start gap-3 select-none transition-all cursor-pointer ${
                                    isChecked
                                      ? (isDark ? "bg-indigo-500/10 border-indigo-500/40 text-white" : "bg-indigo-50 border-indigo-200 text-indigo-900")
                                      : (isDark ? "bg-slate-950/40 border-slate-800/50 hover:border-slate-750 text-slate-400" : "bg-white border-slate-200 hover:border-slate-300 text-slate-600")
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={(e) => {
                                      if (e.target.checked) {
                                        setExpertiseDomains(prev => [...prev, domain.key]);
                                      } else {
                                        setExpertiseDomains(prev => prev.filter(d => d.toLowerCase() !== domain.key.toLowerCase()));
                                      }
                                    }}
                                    className="mt-1 rounded text-indigo-600 focus:ring-indigo-500"
                                  />
                                  <div>
                                    <span className="text-xs font-bold block">{domain.en}</span>
                                    <span className="text-[10px] opacity-60 block mt-0.5">{domain.no}</span>
                                  </div>
                                </label>
                              );
                            })}
                          </>
                        ) : (
                          // Read-only chosen domains view
                          (() => {
                            const selectedDomains = LEGAL_DOMAINS.filter(domain => 
                              expertiseDomains.some(d => d.toLowerCase() === domain.key.toLowerCase())
                            );
                            const hasCommon = expertiseDomains.some(d => d.toLowerCase() === "common");

                            if (!hasCommon && selectedDomains.length === 0) {
                              return (
                                <div className={`col-span-2 p-8 text-center rounded-2xl border border-dashed ${
                                  isDark ? "border-slate-800 text-slate-500" : "border-slate-200 text-slate-450"
                                }`}>
                                  <p className="text-xs font-bold uppercase tracking-wider">No specializations chosen yet</p>
                                  <p className="text-[11px] mt-1 font-medium text-slate-400 dark:text-slate-500">Click the edit button below to configure your profile.</p>
                                </div>
                              );
                            }

                            return (
                              <>
                                {hasCommon && (
                                  <div
                                    className={`p-4 rounded-xl border flex items-start gap-3 select-none ${
                                      isDark ? "bg-indigo-500/10 border-indigo-500/30 text-white" : "bg-indigo-50 border-indigo-150 text-indigo-900"
                                    }`}
                                  >
                                    <div>
                                      <span className="text-xs font-bold block">Generalist (Common)</span>
                                      <span className="text-[10px] opacity-60 block mt-0.5">Receives matches for all case domains</span>
                                    </div>
                                  </div>
                                )}
                                {selectedDomains.map((domain) => (
                                  <div
                                    key={domain.key}
                                    className={`p-4 rounded-xl border flex items-start gap-3 select-none ${
                                      isDark ? "bg-indigo-500/10 border-indigo-500/30 text-white" : "bg-indigo-50 border-indigo-150 text-indigo-900"
                                    }`}
                                  >
                                    <div>
                                      <span className="text-xs font-bold block">{domain.en}</span>
                                      <span className="text-[10px] opacity-60 block mt-0.5">{domain.no}</span>
                                    </div>
                                  </div>
                                ))}
                              </>
                            );
                          })()
                        )}
                      </div>
                    </div>

                    {!isEditingSpecialization ? (
                      <button
                        onClick={() => setIsEditingSpecialization(true)}
                        className="w-full sm:w-auto px-8 py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-600/20 transition-all"
                      >
                        Edit Specialization Profile
                      </button>
                    ) : (
                      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full sm:w-auto">
                        <button
                          onClick={handleSaveSpecialization}
                          disabled={isSpecializationSaving}
                          className="w-full sm:w-auto px-8 py-3.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-600/20 transition-all disabled:opacity-50"
                        >
                          {isSpecializationSaving ? "Saving..." : "Save Specialization Profile"}
                        </button>
                        <button
                          onClick={handleCancelSpecializationEdit}
                          className={`w-full sm:w-auto px-8 py-3.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${isDark
                            ? "bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700"
                            : "bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-200"
                            }`}
                        >
                          Cancel
                        </button>
                      </div>
                    )}
                  </div>

                  <div className={`p-6 rounded-2xl border h-fit ${isDark ? "bg-indigo-500/5 border-indigo-500/10 text-indigo-200" : "bg-indigo-50 border-indigo-100 text-indigo-900"}`}>
                    <h3 className="font-bold flex items-center gap-2 mb-4">
                      <Scale size={18} />
                      Queue Prioritization
                    </h3>
                    <p className="text-xs font-medium opacity-80 leading-relaxed">
                      By selecting your areas of expertise, the system will automatically match you with relevant incoming client matters.
                      These matters will be sorted to the top of your queue and highlighted with a <b>Domain Match</b> badge.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* VIEW: PERSONAL ANALYTICS */}
          {activeView === "analytics" && (
            <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-300 pb-10">
              <div className={`p-8 rounded-2xl border shadow-sm ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-slate-200"}`}>
                <div className="flex items-center gap-4 mb-8">
                  <div className="h-12 w-12 rounded-2xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center">
                    <BarChart3 size={24} />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold tracking-tight">Personal Analytics</h2>
                    <p className="text-sm text-slate-500 mt-1">Track your performance history and metrics at a glance</p>
                  </div>
                </div>

                {analyticsLoading ? (
                  <div className="flex flex-col items-center justify-center py-24 gap-4">
                    <Loader2 className="animate-spin text-indigo-600" size={32} />
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-widest">Loading Analytics...</span>
                  </div>
                ) : !personalAnalytics ? (
                  <div className="py-20 text-center text-slate-400 uppercase tracking-widest text-xs font-bold">
                    Failed to load personal metrics
                  </div>
                ) : (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Left 2 Columns: Stats Cards */}
                    <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6 h-fit">
                      {/* Total Cases Handled */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Total Cases Handled</span>
                          <CheckCircle className="text-indigo-500" size={16} />
                        </div>
                        <h3 className="text-3xl font-black tracking-tight">{personalAnalytics.total_cases_handled}</h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2">All resolved and closed cases</p>
                      </div>

                      {/* Cases This Week */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Cases This Week</span>
                          <Calendar className="text-emerald-500" size={16} />
                        </div>
                        <h3 className="text-3xl font-black tracking-tight">{personalAnalytics.cases_this_week}</h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2">Closed since Monday this week</p>
                      </div>

                      {/* Avg Response Time */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Avg Response Time</span>
                          <Clock className="text-amber-500" size={16} />
                        </div>
                        <h3 className="text-2xl font-black tracking-tight">
                          {formatDuration(personalAnalytics.avg_response_time_seconds)}
                        </h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2.5">All-time average first reply speed</p>
                      </div>

                      {/* Avg Resolution Time */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Avg Resolution Time</span>
                          <CheckCircle2 className="text-blue-500" size={16} />
                        </div>
                        <h3 className="text-2xl font-black tracking-tight">
                          {formatDuration(personalAnalytics.avg_resolution_time_seconds)}
                        </h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2.5">All-time average claim to resolve time</p>
                      </div>

                      {/* Acceptance Rate */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Acceptance Rate</span>
                          <Scale className="text-pink-500" size={16} />
                        </div>
                        <h3 className="text-3xl font-black tracking-tight">{personalAnalytics.acceptance_rate_percentage}%</h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2">Percentage of cases claimed from queue</p>
                      </div>

                      {/* Customer Rating */}
                      <div className={`p-6 rounded-2xl border shadow-sm ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Customer Rating</span>
                          {renderStars(personalAnalytics.average_rating)}
                        </div>
                        <h3 className="text-3xl font-black tracking-tight">{personalAnalytics.average_rating || "N/A"}<span className="text-sm font-bold text-slate-400"> / 5.0</span></h3>
                        <p className="text-[10px] text-slate-400 font-medium mt-2">Average score of client reviews</p>
                      </div>
                    </div>

                    {/* Right Column: Performance Bar Chart */}
                    <div className={`p-6 rounded-2xl border shadow-sm flex flex-col justify-between ${isDark ? "bg-slate-950/40 border-slate-800" : "bg-slate-50/50 border-slate-200"}`}>
                      <div>
                        <h3 className="text-xs font-black uppercase tracking-widest text-slate-500 mb-2">Performance Summary</h3>
                        <p className="text-[10px] text-slate-400 font-medium mb-6">Visual comparison of normalized performance metrics</p>
                      </div>
                      
                      <div className="h-[280px] w-full flex items-center justify-center">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            data={[
                              { name: "Cases Handled", score: Math.min((personalAnalytics.total_cases_handled / 150) * 100, 100), raw: personalAnalytics.total_cases_handled },
                              { name: "Cases Week", score: Math.min((personalAnalytics.cases_this_week / 15) * 100, 100), raw: personalAnalytics.cases_this_week },
                              { name: "Response Time", score: Math.max(100 - (personalAnalytics.avg_response_time_seconds / 3600) * 4, 0), raw: formatDuration(personalAnalytics.avg_response_time_seconds) },
                              { name: "Resolution Time", score: Math.max(100 - (personalAnalytics.avg_resolution_time_seconds / 86400) * 10, 0), raw: formatDuration(personalAnalytics.avg_resolution_time_seconds) },
                              { name: "Acceptance", score: personalAnalytics.acceptance_rate_percentage, raw: `${personalAnalytics.acceptance_rate_percentage}%` },
                              { name: "Rating", score: (personalAnalytics.average_rating / 5.0) * 100, raw: `${personalAnalytics.average_rating} / 5.0` }
                            ]}
                            layout="vertical"
                            margin={{ top: 0, right: 10, left: -15, bottom: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" horizontal={false} vertical={true} stroke={isDark ? "#1e293b" : "#f1f5f9"} />
                            <XAxis type="number" domain={[0, 100]} hide />
                            <YAxis 
                              dataKey="name" 
                              type="category" 
                              axisLine={false} 
                              tickLine={false} 
                              tick={{ fontSize: 9, fill: isDark ? "#94a3b8" : "#64748b", fontWeight: 700 }}
                              width={95}
                            />
                            <Tooltip
                              cursor={{ fill: isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.02)" }}
                              content={({ active, payload }) => {
                                if (active && payload && payload.length) {
                                  const data = payload[0].payload;
                                  return (
                                    <div className={`p-3 rounded-xl border shadow-xl text-xs font-bold ${isDark ? "bg-slate-900 border-slate-800 text-white" : "bg-white border-slate-100 text-slate-800"}`}>
                                      <p className="text-slate-400 font-medium uppercase tracking-wider text-[9px] mb-1">{data.name}</p>
                                      <p className="text-sm font-black">{data.raw}</p>
                                    </div>
                                  );
                                }
                                return null;
                              }}
                            />
                            <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={12}>
                              {[
                                "#6366f1", "#10b981", "#f59e0b", "#3b82f6", "#ec4899", "#f43f5e"
                              ].map((color, index) => (
                                <Cell key={`cell-${index}`} fill={color} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* VIEW: CALENDAR */}
          {activeView === "calendar" && (
            <CalendarView tickets={[...activeTickets, ...resolvedTickets]} role="lawyer" />
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

      {/* FULL SUMMARY MODAL */}
      {activeSummaryModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className={`w-full max-w-lg rounded-3xl border p-8 shadow-2xl animate-in zoom-in-95 duration-200 ${isDark ? "bg-slate-900 border-slate-800" : "bg-white border-gray-100"}`}>
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xl font-bold">Full Matter Summary</h3>
              <button
                onClick={() => setActiveSummaryModal(null)}
                className={`p-1.5 rounded-xl transition-colors ${isDark ? "hover:bg-slate-800 text-slate-400" : "hover:bg-slate-100 text-slate-500"}`}
              >
                <X size={18} />
              </button>
            </div>
            <div className={`p-6 rounded-2xl border text-sm leading-relaxed max-h-[60vh] overflow-y-auto ${isDark ? "bg-slate-950/50 border-slate-800 text-slate-300" : "bg-slate-50 border-slate-200 text-slate-700"}`}>
              {activeSummaryModal}
            </div>
            <div className="mt-8 flex justify-end">
              <button
                onClick={() => setActiveSummaryModal(null)}
                className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-xs font-black uppercase tracking-widest shadow-lg shadow-indigo-600/20 transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Notifications Overlay */}
      <SystemNotification
        notifications={notifications}
        currentView={activeView}
        onDismiss={handleDismissNotification}
        onNavigate={(view, notif) => {
          if (view) {
            if (notif && notif.type === "new_message" && notif.ticketId) {
              handleWorkOn(notif.ticketId);
              navigate(`/lawyer/tickets/${notif.ticketId}?view=messages`);
            } else {
              setActiveView((view === "pending" || view === "intake") ? "intake" : view);
              setIsSidebarOpen(false);
            }
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
