import api from "./api";

const adminService = {
  /**
   * List all users in the system
   */
  listUsers: async () => {
    const response = await api.get("/admin/users");
    return response.data;
  },

  /**
   * Send an invitation email to a new user
   * @param {string} email 
   * @param {string} role - 'lawyer' | 'admin'
   */
  inviteUser: async (email, role) => {
    const response = await api.post("/admin/invite", { email, role });
    return response.data;
  },

  /**
   * Promote a user to Lawyer
   */
  promoteToLawyer: async (userId, barLicense = "", barCouncil = "") => {
    const response = await api.post("/admin/promote/lawyer", {
      user_id: userId,
      bar_license: barLicense,
      bar_council: barCouncil,
    });
    return response.data;
  },

  /**
   * Promote a user to Admin
   */
  promoteToAdmin: async (userId, fullName = "") => {
    const response = await api.post("/admin/promote/admin", {
      user_id: userId,
      full_name: fullName,
    });
    return response.data;
  },
};

export default adminService;
