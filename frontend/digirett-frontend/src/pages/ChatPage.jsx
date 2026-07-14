import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import LibraryDashboard from "../components/chat/LibraryDashboard";
import LegalPanel from "../components/layout/LegalPanel";
import useConversations from "../hooks/useConversations";
import { useUser } from "@clerk/clerk-react";
import hitlService from "../services/hitlService";
import SystemNotification from "../components/chat/ResolutionNotification";
import { useTheme } from "../providers/ThemeProvider";
import { Gavel, Crown, PartyPopper, Check } from "lucide-react";
import subscriptionService from "../services/subscriptionService";

const isUuid = (str) => {
  if (!str) return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(str);
};

const ChatPage = () => {
  const { id: urlId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const activeView = searchParams.get("view"); // "library" or null
  const { user } = useUser();
  const [isEscalated, setIsEscalated] = useState(false);
  const [isLegalPanelOpen, setIsLegalPanelOpen] = useState(false);
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [dismissedEvents, setDismissedEvents] = useState(() => {
    const seen = localStorage.getItem("dismissed_system_events");
    return seen ? JSON.parse(seen) : [];
  });
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [purchasedPlan, setPurchasedPlan] = useState("");

  const {
    conversations,
    isLoading: convLoading,
    currentConversationId,
    selectConversation,
    deleteConversation,
    handleAutoCreatedConversation,
    moveConversationToTop,
    setCurrentConversationId,
    updateEscalationStatus,
    archivedIds,
    archiveConversation,
    restoreConversation
  } = useConversations();

  // Handle Stripe sandbox redirect success
  useEffect(() => {
    const sessionId = searchParams.get("session_id");
    if (sessionId && user) {
      let plan = "vekst"; // Default demo plan
      if (sessionId.includes("startup")) plan = "startup";
      else if (sessionId.includes("vekst")) plan = "vekst";
      else if (sessionId.includes("smb")) plan = "smb";
      else if (sessionId.includes("enterprise")) plan = "enterprise";
      
      subscriptionService.setSubscription(user.id, plan, sessionId);
      setPurchasedPlan(plan);
      setShowSuccessModal(true);
      
      // Force Clerk to reload metadata instantly
      user.reload().catch(err => console.error("Error reloading Clerk user:", err));

      // Clean URL parameters by updating navigate
      const newParams = new URLSearchParams(searchParams);
      newParams.delete("session_id");
      const path = window.location.pathname;
      navigate({
        pathname: path,
        search: newParams.toString() ? `?${newParams.toString()}` : "",
      }, { replace: true });
    }
  }, [searchParams, user, navigate]);

  // Sync currentConversationId with URL parameter
  // Note: archived conversations should still be loadable/viewable — archivedIds only controls the sidebar filter
  useEffect(() => {
    if (urlId && isUuid(urlId)) {
      if (urlId !== currentConversationId) {
        selectConversation(urlId);
      }
    } else {
      if (currentConversationId !== null) {
        selectConversation(null);
      }
    }
  }, [urlId, selectConversation, currentConversationId]);

  const handleConversationCreated = useCallback((newId, title) => {
    handleAutoCreatedConversation(newId, title);
    navigate(`/chat/${newId}`, { replace: true });
  }, [handleAutoCreatedConversation, navigate]);

  // Persistence: Check if current conversation is already escalated on load/change
  useEffect(() => {
    const checkEscalation = async () => {
      if (currentConversationId && isUuid(currentConversationId)) {
        try {
          const status = await hitlService.getEscalationStatus(currentConversationId);
          setIsEscalated(status.is_escalated);
        } catch (err) {
          console.error("[ChatPage] Error checking escalation status:", err);
          setIsEscalated(false);
        }
      } else {
        setIsEscalated(false);
      }
    };
    checkEscalation();
  }, [currentConversationId]);

  const { isDark } = useTheme();

  useEffect(() => {
    const handleStatusChanged = (e) => {
      setIsEscalated(e.detail);
    };
    window.addEventListener("escalation_status_changed", handleStatusChanged);
    return () => {
      window.removeEventListener("escalation_status_changed", handleStatusChanged);
    };
  }, []);

  // Monitor for persistent status alerts (Accepted/Resolved)
  const checkMatterStatus = useCallback(async () => {
    if (!user?.id) return;

    try {
      // 1. Get dismissed events - Unified storage for sync
      const savedDismissed = localStorage.getItem("dismissed_system_events");
      const currentDismissed = savedDismissed ? JSON.parse(savedDismissed) : [];

      // Also check lawyer-specific dismissals if applicable
      const savedLawyerDismissed = localStorage.getItem("dismissed_lawyer_events");
      const currentLawyerDismissed = savedLawyerDismissed ? JSON.parse(savedLawyerDismissed) : [];

      const allDismissed = [...new Set([...currentDismissed, ...currentLawyerDismissed])];

      // 2. Fetch user's tickets
      const tickets = await hitlService.getMyTickets();
      const currentNotifications = [];

      if (Array.isArray(tickets)) {
        tickets.forEach(ticket => {
          const ticketId = ticket.ticket_id || ticket.id;
          if (!ticketId) return;

          const status = (ticket.status || "").toLowerCase();
          const convId = ticket.conversation_id;

          const conv = conversations.find(c => c.conversation_id === convId);
          const title = conv?.title || "Legal Matter";
          const lawyerName = ticket.lawyer_name || "A specialized lawyer";
          const caseRef = ticketId.slice(-4).toUpperCase();

          const isAccepted = status !== "open" && status !== "resolved" && status !== "closed" && status !== "completed";
          if (isAccepted) {
            const eventId = `accepted_${ticketId}`;
            if (!allDismissed.includes(eventId)) {
              currentNotifications.push({
                id: eventId,
                type: 'accepted',
                title: title,
                caseRef: caseRef,
                message: `Matter #${caseRef}: Lawyer "${lawyerName}" has accepted your matter "${title}".`,
                conversation_id: convId
              });
            }
          }

          const isResolved = status === "resolved" || status === "closed" || status === "completed";
          if (isResolved) {
            const eventId = `resolved_${ticketId}`;
            if (!allDismissed.includes(eventId)) {
              currentNotifications.push({
                id: eventId,
                type: 'resolved',
                title: title,
                caseRef: caseRef,
                message: `Matter #${caseRef}: Your legal consultation for "${title}" is now complete. View the official resolution.`,
                conversation_id: convId
              });
            }
          }
        });
      }

      // 3. If User is a Lawyer, also monitor the Matter Queue
      const userRole = user?.publicMetadata?.role || (user?.unsafeMetadata?.role);

      if (userRole === "lawyer" || userRole === "admin" || userRole === "system_admin") {
        try {
          const queueTickets = await hitlService.getQueue(); // Corrected function name
          if (Array.isArray(queueTickets)) {
            queueTickets.forEach(ticket => {
              const ticketId = ticket.ticket_id || ticket.id;
              const eventId = `new_case_${ticketId}`;

              if (!allDismissed.includes(eventId)) {
                currentNotifications.push({
                  id: eventId,
                  type: 'new_case',
                  caseRef: ticketId.slice(-4).toUpperCase(),
                  message: `New Incoming Matter: A legal consultation has been requested and is waiting in your queue.`,
                  view: 'queue'
                });
              }
            });
          }
        } catch (queueErr) {
          console.error("[ChatPage] Error checking matter queue:", queueErr);
        }
      }

      setNotifications(currentNotifications);
    } catch (err) {
      console.error("[ChatPage] Error checking matter status:", err);
    }
  }, [user?.id, user?.publicMetadata?.role, conversations, currentConversationId]);

  const checkMatterStatusRef = useRef(checkMatterStatus);
  useEffect(() => {
    checkMatterStatusRef.current = checkMatterStatus;
  }, [checkMatterStatus]);

  useEffect(() => {
    const interval = setInterval(() => {
      checkMatterStatusRef.current();
    }, 10000); // Check every 10s for faster updates
    checkMatterStatusRef.current(); // Initial check
    return () => clearInterval(interval);
  }, []);

  const handleDismissNotification = useCallback((notifId) => {
    // 1. Update General System Dismissals
    setDismissedEvents(prev => {
      const updated = [...new Set([...prev, notifId])];
      localStorage.setItem("dismissed_system_events", JSON.stringify(updated));
      return updated;
    });

    // 2. ALSO update Lawyer Dashboard Dismissals (if it's a queue notification)
    // This ensures that dismissing it in Chat also clears it from the Lawyer Dashboard
    if (notifId.startsWith('new_case_')) {
      const savedLawyerDismissed = localStorage.getItem("dismissed_lawyer_events");
      const lawyerDismissed = savedLawyerDismissed ? JSON.parse(savedLawyerDismissed) : [];
      if (!lawyerDismissed.includes(notifId)) {
        const updatedLawyer = [...lawyerDismissed, notifId];
        localStorage.setItem("dismissed_lawyer_events", JSON.stringify(updatedLawyer));
      }
    }

    setNotifications(prev => prev.filter(n => n.id !== notifId));
  }, []);

  return (
    <>
      <MainLayout
        conversations={conversations}
        currentConversationId={currentConversationId}
        archivedIds={archivedIds}
        archiveConversation={archiveConversation}
        restoreConversation={restoreConversation}
        onNewChat={() => {
          localStorage.removeItem("conversationId");
          navigate("/chat");
          setCurrentConversationId(null);
          setIsEscalated(false);
          setIsLegalPanelOpen(false);
          window.dispatchEvent(new CustomEvent("new_chat_triggered"));
        }}
        onSelectConversation={(id) => {
          navigate(`/chat/${id}`);
          setIsEscalated(false);
          setIsLegalPanelOpen(false);
        }}
        onDeleteConversation={(id) => {
          deleteConversation(id);
          // If the deleted conversation is the one currently open, redirect to new chat
          if (id === currentConversationId || id === urlId) {
            localStorage.removeItem("conversationId");
            setCurrentConversationId(null);
            setIsEscalated(false);
            setIsLegalPanelOpen(false);
            navigate("/chat", { replace: true });
          }
        }}
        isLoadingConversations={convLoading}
        error={null} // Errors handled inside components
        rightSidebar={
          isEscalated && currentConversationId && isLegalPanelOpen ? (
            <LegalPanel conversationId={currentConversationId} onClose={() => setIsLegalPanelOpen(false)} theme={isDark ? "dark" : "light"} />
          ) : null
        }
      >
        {convLoading ? (
          <div className="flex-1 flex items-center justify-center h-full text-gray-500">
            Loading...
          </div>
        ) : activeView === "library" ? (
          <LibraryDashboard
            theme={isDark ? "dark" : "light"}
            onNavigateToConversation={(convId) => {
              navigate(`/chat/${convId}`);
              setIsEscalated(false);
              setIsLegalPanelOpen(false);
            }}
          />
        ) : (
          <div className="relative w-full h-full flex flex-col">
            <ChatContainer
              conversationId={currentConversationId}
              conversations={conversations}
              onConversationCreated={handleConversationCreated}
              moveConversationToTop={moveConversationToTop}
              userId={user?.id}
              theme={isDark ? "dark" : "light"}
              onEscalated={(status) => {
                setIsEscalated(status);
                if (status && currentConversationId) {
                  updateEscalationStatus(currentConversationId, true);
                  setIsLegalPanelOpen(false);
                }
              }}
            />
            {isEscalated && !isLegalPanelOpen && (
              <button
                onClick={() => setIsLegalPanelOpen(true)}
                className={`absolute top-4 right-4 z-50 px-4 py-2.5 text-sm font-bold rounded-xl border shadow-lg transition-all animate-in zoom-in duration-300 flex items-center gap-2 ${isDark
                  ? "bg-indigo-500/20 border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/30 hover:text-white"
                  : "bg-indigo-50 border-indigo-100 text-indigo-600 hover:bg-indigo-100 hover:text-indigo-800"
                  }`}
              >
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                Human Escalation
              </button>
            )}
          </div>
        )}
      </MainLayout>

      {/* System Notifications (Global Overlay) */}
      <SystemNotification
        notifications={notifications}
        currentView={currentConversationId}
        onDismiss={handleDismissNotification}
        onNavigate={(target) => {
          if (target === 'queue') {
            navigate('/lawyer');
            return;
          }

          // If it's a conversation ID
          const id = target;
          // 1. Clear ALL notifications for this specific conversation ID immediately
          const relatedNotifs = notifications.filter(n => n.conversation_id === id);
          relatedNotifs.forEach(n => handleDismissNotification(n.id));

          // 2. Redirect to the conversation URL (Clean switch)
          navigate(`/chat/${id}`);
          setIsEscalated(false);
          setIsNotificationsOpen(false);
        }}
        isDark={isDark}
        isOpen={isNotificationsOpen}
        onToggleOpen={(open) => {
          setIsNotificationsOpen(open);
          if (open) {
            setIsLegalPanelOpen(false);
          }
        }}
      />

      {/* Stripe Payment Success Modal */}
      {showSuccessModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          {/* Confetti particles container */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            {[...Array(24)].map((_, i) => {
              const left = Math.random() * 100;
              const delay = Math.random() * 2;
              const duration = 2 + Math.random() * 2;
              const color = ["#818cf8", "#a78bfa", "#f472b6", "#38bdf8", "#34d399"][i % 5];
              return (
                <div
                  key={i}
                  className="absolute top-0 w-2 h-2 rounded-full animate-fall"
                  style={{
                    left: `${left}%`,
                    backgroundColor: color,
                    animationDelay: `${delay}s`,
                    animationDuration: `${duration}s`,
                    opacity: 0.8,
                  }}
                />
              );
            })}
          </div>

          <div
            className={`relative max-w-md w-full p-8 rounded-2xl border text-center shadow-2xl backdrop-blur-xl transition-all scale-up ${
              isDark
                ? "bg-[#12121e]/90 border-indigo-500/30 text-white shadow-indigo-500/10"
                : "bg-white border-gray-200 text-gray-900 shadow-xl"
            }`}
          >
            {/* Pulsing visual glow */}
            <div className="absolute -top-12 left-1/2 -translate-x-1/2 w-24 h-24 bg-gradient-to-tr from-indigo-500 to-purple-600 rounded-full blur-xl opacity-50 animate-pulse" />

            <div className="relative z-10 flex flex-col items-center">
              <div className="h-16 w-16 bg-gradient-to-tr from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-white mb-6 shadow-lg shadow-indigo-500/20 scale-pulse">
                <Crown className="h-8 w-8 text-white" />
              </div>

              <span className="text-[10px] uppercase font-black tracking-widest text-indigo-400 bg-indigo-500/10 px-3 py-1 rounded-full mb-3">
                Sandbox Payment Success
              </span>
              
              <h3 className="text-2xl font-black mb-2">
                Subscription Active!
              </h3>
              
              <p className={`text-sm mb-6 ${isDark ? "text-gray-400" : "text-gray-600"}`}>
                Congratulations! You are now subscribed to the <span className="font-extrabold text-indigo-400 uppercase">{purchasedPlan}</span> plan. Your premium legal assistance privileges have been activated.
              </p>

              <div className="w-full flex flex-col gap-2.5">
                <button
                  onClick={() => setShowSuccessModal(false)}
                  className="w-full py-3 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold rounded-xl text-sm transition-all hover:scale-[1.02] shadow-lg shadow-indigo-500/25"
                >
                  Start Consulting
                </button>
              </div>
            </div>
          </div>
          
          <style>{`
            @keyframes fall {
              0% { transform: translateY(-20px) rotate(0deg); opacity: 1; }
              100% { transform: translateY(105vh) rotate(360deg); opacity: 0; }
            }
            .animate-fall {
              animation-name: fall;
              animation-iteration-count: infinite;
              animation-timing-function: linear;
            }
            .scale-up {
              animation: scaleUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
            }
            @keyframes scaleUp {
              from { transform: scale(0.9); opacity: 0; }
              to { transform: scale(1); opacity: 1; }
            }
            .scale-pulse {
              animation: pulseIcon 2s infinite ease-in-out;
            }
            @keyframes pulseIcon {
              0%, 100% { transform: scale(1); }
              50% { transform: scale(1.08); }
            }
          `}</style>
        </div>
      )}
    </>
  );
};

export default ChatPage;
