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

  const { isDark } = useTheme();

  // Monitor for persistent status alerts (Accepted/Resolved)
  const checkMatterStatus = useCallback(async () => {
    if (!user?.id) return;

    try {
      // 1. Always get the LATEST dismissed events directly from storage to prevent race conditions
      const savedDismissed = localStorage.getItem("dismissed_system_events");
      const currentDismissed = savedDismissed ? JSON.parse(savedDismissed) : [];

      // 2. Fetch user's tickets
      const tickets = await hitlService.getMyTickets();
      if (!Array.isArray(tickets)) return;

      const currentNotifications = [];

      tickets.forEach(ticket => {
        const ticketId = ticket.ticket_id || ticket.id;
        if (!ticketId) return;

        const status = (ticket.status || "").toLowerCase();
        const convId = ticket.conversation_id;

        // Smart Filter: Skip notification if user is ALREADY inside this conversation
        if (convId === currentConversationId) return;

        // Find the conversation title
        const conv = conversations.find(c => c.conversation_id === convId);
        const title = conv?.title || "Legal Matter";

        // Find the lawyer name if assigned
        const lawyerName = ticket.lawyer_name || "A specialized lawyer";
        const caseRef = ticketId.slice(-4).toUpperCase(); // Short unique ID

        // Check A: Lawyer Accepted (Milestone 1)
        const isAccepted = status !== "open" && status !== "resolved" && status !== "closed" && status !== "completed";
        if (isAccepted) {
          const eventId = `accepted_${ticketId}`;
          if (!currentDismissed.includes(eventId)) {
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

        // Check B: Lawyer Resolved (Milestone 2)
        const isResolved = status === "resolved" || status === "closed" || status === "completed";
        if (isResolved) {
          const eventId = `resolved_${ticketId}`;
          if (!currentDismissed.includes(eventId)) {
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

      setNotifications(currentNotifications);
    } catch (err) {
      console.error("[ChatPage] Error checking matter status:", err);
    }
  }, [user?.id, conversations, currentConversationId]);

  useEffect(() => {
    const interval = setInterval(checkMatterStatus, 30000); // Check every 30s
    checkMatterStatus(); // Initial check
    return () => clearInterval(interval);
  }, [checkMatterStatus]);

  const handleDismissNotification = useCallback((notifId) => {
    setDismissedEvents(prev => {
      const updated = [...prev, notifId];
      localStorage.setItem("dismissed_system_events", JSON.stringify(updated));
      return updated;
    });
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
        onNavigate={(id) => {
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
