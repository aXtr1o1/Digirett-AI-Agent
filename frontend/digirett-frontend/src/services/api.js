import axios from 'axios';
import { API_BASE_URL } from '../utils/constants';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add Clerk token
api.interceptors.request.use(
  async (config) => {
    try {
      // Get Clerk session token
      const clerkToken = await window.Clerk?.session?.getToken();
      
      if (clerkToken) {
        config.headers.Authorization = `Bearer ${clerkToken}`;
      }
      
      return config;
    } catch (error) {
      console.error('Error adding auth token:', error);
      return config;
    }
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error
      const { status, data } = error.response;
      
      if (status === 401) {
        // Unauthorized - redirect to sign in
        window.location.href = '/sign-in';
      } else if (status === 403) {
        console.error('Access forbidden:', data);
      } else if (status === 500) {
        console.error('Server error:', data);
      }
    } else if (error.request) {
      // Request made but no response
      console.error('Network error:', error.message);
    } else {
      // Something else happened
      console.error('Error:', error.message);
    }
    
    return Promise.reject(error);
  }
);

export default api;
