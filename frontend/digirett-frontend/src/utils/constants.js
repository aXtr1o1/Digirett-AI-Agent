export const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api/v1';

export const API_ENDPOINTS = {
  // Auth endpoints
  AUTH: {
    LOGIN: '/auth/login',
    LOGOUT: '/auth/logout',
    USER_DETAILS: '/auth/userDetails',
  },
  
  // User endpoints
  USER: {
    PROFILE: '/users/profile',
  },
  
  // Conversation endpoints
  CONVERSATIONS: {
    CREATE: '/conversations',
    LIST: '/conversations',
    GET_MESSAGES: (conversationId) => `/conversations/${conversationId}/messages`,
  },
  
  // Chat endpoints
  CHAT: {
    MESSAGE: '/chat/message',
  },
  
  // Source endpoints
  SOURCES: {
    GET: '/sources',
  },
};

export const MESSAGE_ROLES = {
  USER: 'user',
  ASSISTANT: 'assistant',
};

export const ERROR_MESSAGES = {
  NETWORK_ERROR: 'Network error. Please check your connection.',
  AUTH_ERROR: 'Authentication failed. Please sign in again.',
  GENERIC_ERROR: 'Something went wrong. Please try again.',
};
