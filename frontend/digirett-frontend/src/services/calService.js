import api from "./api";
import { API_ENDPOINTS } from "../utils/constants";

const calService = {
  /**
   * Get available booking slots for a ticket/lawyer
   * @param {string} ticketId 
   * @param {string} timezone - e.g. 'Europe/Oslo'
   */
  getAvailableSlots: async (ticketId, timezone = "Europe/Oslo") => {
    const response = await api.get(API_ENDPOINTS.CAL.SLOTS(ticketId), {
      params: { timezone }
    });
    return response.data;
  },

  /**
   * Create a booking for a specific slot
   * @param {string} ticketId 
   * @param {object} bookingData - { start_time, timezone }
   */
  createBooking: async (ticketId, bookingData) => {
    const response = await api.post(API_ENDPOINTS.CAL.BOOK(ticketId), bookingData);
    return response.data;
  },
};

export default calService;
