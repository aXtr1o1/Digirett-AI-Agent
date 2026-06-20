import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

/**
 * adminService.js
 * Strictly follows the HITL specification for Administrative oversight.
 */
const adminService = {
  /**
   * #11 Get All Tickets
   * GET /api/v1/admin/tickets
   */
  getAllTickets: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.TICKETS);
    return response.data;
  },

  /**
   * List all system users
   */
  listUsers: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.USERS);
    return response.data;
  },

  /**
   * List all pending invitations
   */
  listInvitations: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.INVITATIONS);
    return response.data;
  },

  /**
   * Send a new invitation
   */
  inviteUser: async (email, role) => {
    const response = await api.post(API_ENDPOINTS.ADMIN.INVITE, { email, role });
    return response.data;
  },

  /**
   * Revoke an invitation
   */
  revokeInvitation: async (inviteId) => {
    const response = await api.delete(API_ENDPOINTS.ADMIN.REVOKE_INVITATION(inviteId));
    return response.data;
  },

  /**
   * Suspend a user
   */
  suspendUser: async (userId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.SUSPEND_USER(userId));
    return response.data;
  },

  /**
   * Unsuspend / Activate a user
   */
  activateUser: async (userId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.ACTIVATE_USER(userId));
    return response.data;
  },

  /**
   * Get Audit Logs
   */
  getAuditLogs: async (limit = 100) => {
    const response = await api.get(API_ENDPOINTS.ADMIN.AUDIT_LOGS, { params: { limit } });
    return response.data;
  },

  /**
   * #12 Assign Ticket to Lawyer
   * PATCH /api/v1/admin/tickets/{ticket_id}/assign/{lawyer_id}
   */
  assignTicket: async (ticketId, lawyerId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.ASSIGN_TICKET(ticketId, lawyerId));
    return response.data;
  },

  /**
   * #13 Unassign Ticket
   * PATCH /api/v1/admin/tickets/{ticket_id}/unassign
   */
  unassignTicket: async (ticketId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.UNASSIGN_TICKET(ticketId));
    return response.data;
  },

  /**
   * #14 Close Ticket
   * PATCH /api/v1/admin/tickets/{ticket_id}/close
   */
  closeTicket: async (ticketId, outcomeNotes = "") => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.CLOSE_TICKET(ticketId), {
      outcome_notes: outcomeNotes
    });
    return response.data;
  },

  /**
   * #15 Get Lawyers List
   * GET /api/v1/admin/lawyers
   */
  listLawyers: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.LAWYERS);
    return response.data;
  },

  /**
   * #16 Set Lawyer Cal.com Credentials
   * PATCH /api/v1/admin/lawyers/{lawyer_id}/cal-credentials
   */
  setLawyerCalCredentials: async (lawyerId, calApiKey, calEventTypeId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.SET_CAL_CREDENTIALS(lawyerId), null, {
      params: {
        cal_api_key: calApiKey,
        cal_event_type_id: calEventTypeId
      }
    });
    return response.data;
  },

  /**
   * #17 Get System Health Status
   * GET /api/v1/health
   */
  getHealthStatus: async () => {
    const response = await api.get(API_ENDPOINTS.HEALTH);
    return response.data;
  },

  /**
   * Get User Query Domain Distribution Analytics
   * GET /api/v1/admin/domain-analytics
   */
  getDomainAnalytics: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.DOMAIN_ANALYTICS);
    return response.data;
  },
};

export default adminService;
