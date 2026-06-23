import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import LegalPanel from "../components/layout/LegalPanel";
import useConversations from "../hooks/useConversations";
import { useUser } from "@clerk/clerk-react";
import hitlService from "../services/hitlService";
import SystemNotification from "../components/chat/ResolutionNotification";
import { useTheme } from "../providers/ThemeProvider";
import { Gavel } from "lucide-react";

const isUuid = (str) => {
  if (!str) return false;
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(str);
};

const ChatPage = () => {
  const { id: urlId } = useParams();
  const navigate = useNavigate();
  const { user } = useUser();
  const [isEscalated, setIsEscalated] = useState(false);
  const [isLegalPanelOpen, setIsLegalPanelOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [dismissedEvents, setDismissedEvents] = useState(() => {
    const seen = localStorage.getItem("dismissed_system_events");
    return seen ? JSON.parse(seen) : [];
  });

  const {
    conversations,
    isLoading: convLoading,
    currentConversationId,
    selectConversation,
    deleteConversation,
    handleAutoCreatedConversation,
    moveConversationToTop,
    setCurrentConversationId,
    updateEscalationStatus
  } = useConversations();

  // Sync currentConversationId with URL parameter
  useEffect(() => {
    if (urlId && isUuid(urlId) && urlId !== currentConversationId) {
      selectConversation(urlId);
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
        onNewChat={() => {
          localStorage.removeItem("conversationId");
          navigate("/chat");
          setCurrentConversationId(null);
          setIsEscalated(false);
          setIsLegalPanelOpen(false);
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
        ) : (
          <div className="relative w-full h-full flex flex-col">
            <ChatContainer
              conversationId={currentConversationId}
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
        }}
        isDark={isDark}
      />
    </>
  );
};

export default ChatPage;
