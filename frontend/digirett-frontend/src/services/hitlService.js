import api from "./api";

const hitlService = {
  /**
   * Get the queue of open HITL tickets
   */
  getQueue: async () => {
    const response = await api.get("/hitl/queue");
    return response.data;
  },

  /**
   * Claim a ticket by assigning it to the current lawyer
   */
  claimTicket: async (ticketId) => {
    const response = await api.patch(`/hitl/tickets/${ticketId}/assign`);
    return response.data;
  },

  /**
   * Get detailed info for a specific ticket (including user info)
   */
  getTicketDetails: async (ticketId) => {
    const response = await api.get(`/hitl/tickets/${ticketId}/details`);
    return response.data;
  },

  /**
   * Submit a lawyer response and resolve the ticket
   */
  respondToTicket: async (ticketId, content) => {
    const response = await api.post(`/hitl/tickets/${ticketId}/respond`, { content });
    return response.data;
  },

  /**
   * Escalate a conversation to a lawyer (called by user)
   */
  escalateConversation: async (conversationId, triggerMessageId, userNote = "") => {
    const response = await api.post("/hitl/escalate", {
      conversation_id: conversationId,
      trigger_message_id: triggerMessageId,
      user_note: userNote,
    });
    return response.data;
  },
};

export default hitlService;
