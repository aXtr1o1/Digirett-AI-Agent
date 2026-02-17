import api from './api';
import { API_ENDPOINTS } from '../utils/constants';

/**
 * Source Service
 * Handles source citation and legal reference API calls
 */
const sourceService = {
  /**
   * Get source citations for a message
   * GET /sources
   */
  getSources: async (messageId) => {
    try {
      const response = await api.get(API_ENDPOINTS.SOURCES.GET, {
        params: { message_id: messageId },
      });
      return response.data;
    } catch (error) {
      console.error('Error fetching sources:', error);
      throw error;
    }
  },

  /**
   * Format source URL for display
   */
  formatSourceUrl: (url) => {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname + urlObj.pathname;
    } catch {
      return url;
    }
  },

  /**
   * Get domain from URL
   */
  getDomain: (url) => {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname;
    } catch {
      return '';
    }
  },
};

export default sourceService;
