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
    STREAM: "/chat/stream",
  },
  HEALTH: "/health",
};

export const MESSAGE_ROLES = {
  USER: "user",
  ASSISTANT: "assistant",
};

export const ERROR_MESSAGES = {
  NETWORK_ERROR: "Network error. Please check your connection.",
  AUTH_ERROR: "Authentication failed. Please sign in again.",
  GENERIC_ERROR: "Something went wrong. Please try again.",
};