import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

const inviteService = {
  /**
   * Verify an invitation token (public endpoint)
   */
  verifyToken: async (token) => {
    // This is a public endpoint, but we use the 'api' instance for base URL and interceptors
    // though it might not have a token yet.
    const response = await api.get(API_ENDPOINTS.INVITE.VERIFY, {
      params: { token }
    });
    return response.data;
  },
  /**
   * Accept an invitation (authenticated)
   */
  acceptInvitation: async (token) => {
    const response = await api.post(API_ENDPOINTS.INVITE.ACCEPT, { token });
    return response.data;
  },
};

export default inviteService;
