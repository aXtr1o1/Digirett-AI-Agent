// Base URL — backend runs with /api/v1 prefix (confirmed from server logs)
export const API_BASE_URL = import.meta.env.VITE_API_URL

// User ID is resolved from Clerk JWTs now.

export const API_ENDPOINTS = {
  CONVERSATIONS: {
    CREATE: "/conversations",
    LIST: "/conversations/me",
    GET: (conversationId) => `/conversations/${conversationId}`,
    DELETE: (conversationId) => `/conversations/${conversationId}`,
  },
  MESSAGES: {
    LIST: (conversationId) => `/messages/${conversationId}`,
  },
  CHAT: {
    WS: "/chat/ws",
  },
  DOCUMENTS: {
    UPLOAD: "/documents/upload",
    SESSION: (conversationId) => `/documents/session/${conversationId}`,
    SAVE_MESSAGE: (conversationId) => `/documents/message/${conversationId}`,
    SAVE_SUMMARY: (conversationId) => `/documents/summary-message/${conversationId}`,
    VIEW: (documentId) => `/documents/view/${documentId}`,
  },
  HITL: {
    ESCALATE: "/hitl/escalate",
    QUEUE: "/hitl/queue",
    ASSIGN: (ticketId) => `/hitl/tickets/${ticketId}/assign`,
    DETAILS: (ticketId) => `/hitl/tickets/${ticketId}/details`,
    RESPOND: (ticketId) => `/hitl/tickets/${ticketId}/respond`,
    MY_TICKETS: "/hitl/my-tickets",
    MY_RESOLVED: "/hitl/my-resolved-tickets",
    STATUS: (conversationId) => `/hitl/status/${conversationId}`,
    RATINGS: "/ratings",
    LAWYER_RATINGS: "/ratings/lawyer",
  },
  CAL: {
    SLOTS: (ticketId) => `/cal/slots/${ticketId}`,
    BOOK: (ticketId) => `/cal/bookings/${ticketId}`,
  },
  ADMIN: {
    TICKETS: "/admin/tickets",
    ASSIGN_TICKET: (ticketId, lawyerId) => `/admin/tickets/${ticketId}/assign/${lawyerId}`,
    UNASSIGN_TICKET: (ticketId) => `/admin/tickets/${ticketId}/unassign`,
    CLOSE_TICKET: (ticketId) => `/admin/tickets/${ticketId}/close`,
    LAWYERS: "/admin/lawyers",
    SET_CAL_CREDENTIALS: (lawyerId) => `/admin/lawyers/${lawyerId}/cal-credentials`,
    INVITE: "/admin/invite",
    INVITATIONS: "/admin/invitations",
    USERS: "/admin/users",
    AUDIT_LOGS: "/admin/audit-logs",
    DEMOTE_USER: (userId) => `/admin/users/${userId}/demote`,
    SUSPEND_USER: (userId) => `/admin/users/${userId}/suspend`,
    ACTIVATE_USER: (userId) => `/admin/users/${userId}/activate`,
    REVOKE_INVITATION: (inviteId) => `/admin/invitations/${inviteId}`,
    DOMAIN_ANALYTICS: "/admin/domain-analytics",
    SLA_REPORT: "/admin/sla-report",
    RATINGS: "/ratings/admin",
  },
  INVITE: {
    VERIFY: "/invite/verify",
    ACCEPT: "/auth/accept-invite",
  },
  HEALTH: "/health",
  LIBRARY: {
    LIST: "/library/documents",
    UPLOAD: "/library/documents/upload",
    DELETE: (documentId) => `/library/documents/${documentId}`,
    UPDATE_NOTE: (documentId) => `/library/documents/${documentId}`,
  },
};

export const MESSAGE_ROLES = {
  USER: "user",
  ASSISTANT: "assistant",
  SYSTEM: "system",
};

export const ERROR_MESSAGES = {
  NETWORK_ERROR: "Network error. Please check your connection.",
  AUTH_ERROR: "Authentication failed. Please sign in again.",
  GENERIC_ERROR: "Something went wrong. Please try again.",
};