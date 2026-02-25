// Base URL — backend runs with /api/v1 prefix (confirmed from server logs)
export const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL;

// Default user ID for MVP (single user — replace with auth later)
export const DEFAULT_USER_ID = "2a06144d-4675-4c38-b7f8-13c02da91af5";

export const API_ENDPOINTS = {
  CONVERSATIONS: {
    CREATE: "/conversations",
    LIST: (userId) => `/conversations/user/${userId}`,
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