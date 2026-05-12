import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

const adminService = {
  /**
   * List all users in the system
   */
  listUsers: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.USERS);
    return response.data;
  },

  /**
   * Send an invitation email to a new user
   * @param {string} email 
   * @param {string} role - 'lawyer' | 'admin'
   */
  inviteUser: async (email, role) => {
    const response = await api.post(API_ENDPOINTS.ADMIN.INVITE, { email, role });
    return response.data;
  },

  /**
   * List all pending and accepted invitations
   */
  listInvitations: async () => {
    const response = await api.get(API_ENDPOINTS.ADMIN.INVITATIONS);
    return response.data;
  },

  /**
   * Revoke a pending invitation
   */
  revokeInvitation: async (inviteId) => {
    const response = await api.delete(API_ENDPOINTS.ADMIN.REVOKE_INVITATION(inviteId));
    return response.data;
  },


  /**
   * Force-assign a ticket to a lawyer (Admin only)
   */
  assignTicket: async (ticketId, lawyerId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.ASSIGN_TICKET(ticketId, lawyerId));
    return response.data;
  },

  /**
   * Close a ticket forcefully (Admin only)
   */
  closeTicket: async (ticketId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.CLOSE_TICKET(ticketId));
    return response.data;
  },

  /**
   * Demote a user back to 'user' role
   */
  demoteUser: async (userId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.DEMOTE_USER(userId));
    return response.data;
  },

  /**
   * Suspend a user account (status = inactive)
   */
  suspendUser: async (userId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.SUSPEND_USER(userId));
    return response.data;
  },

  /**
   * Activate a suspended user
   */
  activateUser: async (userId) => {
    const response = await api.patch(API_ENDPOINTS.ADMIN.ACTIVATE_USER(userId));
    return response.data;
  },

  /**
   * Get system audit logs
   */
  getAuditLogs: async (limit = 50, offset = 0) => {
    const response = await api.get(API_ENDPOINTS.ADMIN.AUDIT_LOGS, {
      params: { limit, offset }
    });
    return response.data;
  },
  /**
   * Get system health status
   */
  getHealthStatus: async () => {
    const response = await api.get(API_ENDPOINTS.HEALTH);
    return response.data;
  },
};

export default adminService;
