import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

const hitlService = {
  /**
   * Get the queue of open HITL tickets
   */
  getQueue: async () => {
    const response = await api.get(API_ENDPOINTS.HITL.QUEUE);
    return response.data;
  },

  /**
   * Claim a ticket by assigning it to the current lawyer
   */
  claimTicket: async (ticketId) => {
    const response = await api.patch(API_ENDPOINTS.HITL.ASSIGN(ticketId));
    return response.data;
  },

  /**
   * Get detailed info for a specific ticket (including user info)
   */
  getTicketDetails: async (ticketId) => {
    const response = await api.get(API_ENDPOINTS.HITL.DETAILS(ticketId));
    return response.data;
  },

  /**
   * Submit a lawyer response and resolve the ticket
   */
  respondToTicket: async (ticketId, content) => {
    const response = await api.post(API_ENDPOINTS.HITL.RESPOND(ticketId), { content });
    return response.data;
  },

  /**
   * Mark a ticket as a no-show (user didn't join)
   */
  markNoShow: async (ticketId, outcomeNotes = "") => {
    const response = await api.post(`/hitl/tickets/${ticketId}/no-show`, { outcome_notes: outcomeNotes });
    return response.data;
  },

  /**
   * Escalate a conversation to a lawyer (called by user)
   */
  escalateConversation: async (conversationId, triggerMessageId, userNote = "", priority = "normal", urgentReason = null) => {
    const response = await api.post(API_ENDPOINTS.HITL.ESCALATE, {
      conversation_id: conversationId,
      trigger_message_id: triggerMessageId,
      user_note: userNote,
      priority,
      urgent_reason: urgentReason
    });
    return response.data;
  },

  /**
   * Get user's own escalation tickets
   */
  getMyTickets: async () => {
    const response = await api.get(API_ENDPOINTS.HITL.MY_TICKETS);
    return response.data;
  },

  /**
   * Get lawyer's resolved history
   */
  getResolvedHistory: async () => {
    const response = await api.get(API_ENDPOINTS.HITL.MY_RESOLVED);
    return response.data;
  },

  /**
   * Get lawyer's active (assigned/booked) tickets
   */
  getActiveTickets: async () => {
    const response = await api.get("/hitl/my-active-tickets");
    return response.data;
  },

  /**
   * Check if a conversation is already escalated
   */
  getEscalationStatus: async (conversationId) => {
    const response = await api.get(API_ENDPOINTS.HITL.STATUS(conversationId));
    return response.data;
  },

  /**
   * Publicly check if a user is suspended by email/username
   */
  checkStatus: async (identifier) => {
    const response = await api.get(`/hitl/check-status?identifier=${encodeURIComponent(identifier)}`);
    return response.data;
  },

  /**
   * Get lawyer Cal.com configuration
   */
  getCalConfig: async () => {
    const response = await api.get("/cal/lawyer/config");
    return response.data;
  },

  /**
   * Update lawyer Cal.com configuration
   */
  updateCalConfig: async (configData) => {
    const response = await api.put("/cal/lawyer/config", configData);
    return response.data;
  },

  /**
   * Update lawyer specialization domains
   */
  updateSpecialization: async (expertiseDomains, specializationLabel = null) => {
    const response = await api.patch("/hitl/lawyer/profile/specialization", {
      expertise_domains: expertiseDomains,
      specialization_label: specializationLabel
    });
    return response.data;
  },

  /**
   * Submit client rating for a ticket
   */
  submitRating: async (ticketId, rating, comment) => {
    try {
      const response = await api.post(API_ENDPOINTS.HITL.RATINGS, {
        ticket_id: ticketId,
        rating,
        comment,
      });
      return response.data;
    } catch (err) {
      console.warn("Backend rating route failed, using localStorage fallback:", err);
      const localRatings = JSON.parse(localStorage.getItem("digirett_ratings") || "[]");
      const exists = localRatings.findIndex(r => r.ticket_id === ticketId);
      const newRating = {
        rating_id: exists >= 0 ? localRatings[exists].rating_id : Math.random().toString(36).substring(2, 15),
        ticket_id: ticketId,
        rating,
        comment,
        created_at: new Date().toISOString(),
      };
      if (exists >= 0) {
        localRatings[exists] = newRating;
      } else {
        localRatings.push(newRating);
      }
      localStorage.setItem("digirett_ratings", JSON.stringify(localRatings));
      localStorage.setItem(`rated_ticket_${ticketId}`, JSON.stringify(newRating));
      return { status: "success", message: "Feedback submitted successfully (fallback)." };
    }
  },

  /**
   * Get current lawyer's ratings list
   */
  getLawyerRatings: async () => {
    try {
      const response = await api.get(API_ENDPOINTS.HITL.LAWYER_RATINGS);
      return response.data;
    } catch (err) {
      console.warn("Backend lawyer ratings route failed, using localStorage fallback:", err);
      return JSON.parse(localStorage.getItem("digirett_ratings") || "[]");
    }
  },

  /**
   * Get all pre-consultation messages for a ticket
   */
  getTicketMessages: async (ticketId) => {
    const response = await api.get(`/hitl/tickets/${ticketId}/messages`);
    return response.data;
  },

  /**
   * Send a pre-consultation message for a ticket
   */
  sendTicketMessage: async (ticketId, content, fileName = null, documentId = null) => {
    const response = await api.post(`/hitl/tickets/${ticketId}/messages`, {
      content,
      file_name: fileName,
      document_id: documentId
    });
    return response.data;
  },

  /**
   * Mark all pre-consultation messages in the thread as read
   */
  markTicketMessagesRead: async (ticketId) => {
    const response = await api.patch(`/hitl/tickets/${ticketId}/messages/read`);
    return response.data;
  },

  /**
   * Close a resolved ticket
   */
  closeTicket: async (ticketId) => {
    const response = await api.patch(`/hitl/tickets/${ticketId}/close`);
    return response.data;
  },

  /**
   * Re-escalate a resolved ticket
   */
  reEscalateTicket: async (ticketId, option) => {
    const response = await api.post(`/hitl/tickets/${ticketId}/re-escalate`, { option });
    return response.data;
  },

  /**
   * Update lawyer availability status
   */
  updateAvailability: async (status) => {
    const response = await api.patch("/hitl/lawyer/profile/availability", { availability_status: status });
    return response.data;
  },

  /**
   * Update ticket priority
   */
  updateTicketPriority: async (ticketId, priority) => {
    const response = await api.patch(`/hitl/tickets/${ticketId}/priority`, { priority });
    return response.data;
  },
  /**
   * Get current lawyer's personal analytics metrics
   */
  getPersonalAnalytics: async () => {
    const response = await api.get("/hitl/lawyer/analytics/personal");
    return response.data;
  }
};

export default hitlService;
