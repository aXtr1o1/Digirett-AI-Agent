import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import MainLayout from "../components/layout/MainLayout";
import ChatContainer from "../components/chat/ChatContainer";
import LegalPanel from "../components/layout/LegalPanel";
import useConversations from "../hooks/useConversations";
import { useUser } from "@clerk/clerk-react";
import hitlService from "../services/hitlService";
import SystemNotification from "../components/chat/ResolutionNotification";
import { useTheme } from "../providers/ThemeProvider";

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

          if (convId === currentConversationId) return;

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
      
      if (userRole === "lawyer" || userRole === "admin") {
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

  useEffect(() => {
    const interval = setInterval(checkMatterStatus, 10000); // Check every 10s for faster updates
    checkMatterStatus(); // Initial check
    return () => clearInterval(interval);
  }, [checkMatterStatus]);

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
        }}
        onSelectConversation={(id) => {
          navigate(`/chat/${id}`);
          setIsEscalated(false);
        }}
        onDeleteConversation={deleteConversation}
        isLoadingConversations={convLoading}
        error={null} // Errors handled inside components
        rightSidebar={
          isEscalated && currentConversationId ? (
            <LegalPanel conversationId={currentConversationId} />
          ) : null
        }
      >
        {convLoading ? (
          <div className="flex-1 flex items-center justify-center h-full text-gray-500">
            Loading...
          </div>
        ) : (
          <ChatContainer
            conversationId={currentConversationId}
            onConversationCreated={handleAutoCreatedConversation}
            moveConversationToTop={moveConversationToTop}
            userId={user?.id}
            onEscalated={(status) => {
              setIsEscalated(status);
              if (status && currentConversationId) {
                updateEscalationStatus(currentConversationId, true);
              }
            }}
          />
        )}
      </MainLayout>

      {/* System Notifications (Global Overlay) */}
      <SystemNotification
        notifications={notifications}
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
