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
   * Escalate a conversation to a lawyer (called by user)
   */
  escalateConversation: async (conversationId, triggerMessageId, userNote = "") => {
    const response = await api.post(API_ENDPOINTS.HITL.ESCALATE, {
      conversation_id: conversationId,
      trigger_message_id: triggerMessageId,
      user_note: userNote,
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
};

export default hitlService;
