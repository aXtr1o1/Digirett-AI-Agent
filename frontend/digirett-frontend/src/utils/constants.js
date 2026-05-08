// Base URL — backend runs with /api/v1 prefix (confirmed from server logs)
export const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL;

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
  },
  ADMIN: {
    INVITE: "/admin/invite",
    PROMOTE_LAWYER: "/admin/promote/lawyer",
    PROMOTE_ADMIN: "/admin/promote/admin",
    USERS: "/admin/users",
    AUDIT_LOGS: "/admin/audit-logs",
    ASSIGN_TICKET: (ticketId, lawyerId) => `/admin/tickets/${ticketId}/assign/${lawyerId}`,
    CLOSE_TICKET: (ticketId) => `/admin/tickets/${ticketId}/close`,
    DEMOTE_USER: (userId) => `/admin/users/${userId}/demote`,
    SUSPEND_USER: (userId) => `/admin/users/${userId}/suspend`,
  },
  INVITE: {
    VERIFY: "/invite/verify",
    ACCEPT: "/auth/accept-invite",
  },
  HEALTH: "/health",
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