import React, { useEffect, useState } from "react";
import adminService from "../services/adminService";
import { Users, Mail, Shield, ArrowUpCircle, Loader2, Search, UserPlus } from "lucide-react";

export default function AdminDashboard() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("lawyer");
  const [inviteLoading, setInviteLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchUsers = async () => {
    try {
      const data = await adminService.listUsers();
      setUsers(data);
    } catch (err) {
      console.error("Failed to fetch users:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!inviteEmail) return;
    setInviteLoading(true);
    setMessage(null);
    try {
      await adminService.inviteUser(inviteEmail, inviteRole);
      setMessage({ type: "success", text: `Invitation sent to ${inviteEmail}` });
      setInviteEmail("");
    } catch (err) {
      setMessage({ type: "error", text: err.message || "Failed to send invitation" });
    } finally {
      setInviteLoading(false);
    }
  };

  const handlePromote = async (userId, role) => {
    try {
      if (role === "lawyer") {
        await adminService.promoteToLawyer(userId);
      } else if (role === "admin") {
        await adminService.promoteToAdmin(userId);
      }
      setMessage({ type: "success", text: `User promoted to ${role} successfully` });
      fetchUsers();
    } catch (err) {
      setMessage({ type: "error", text: err.message || "Promotion failed" });
    }
  };

  const filteredUsers = users.filter(u => 
    u.email?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.user_profiles?.display_name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-gray-50 p-6 md:p-10">
      <div className="max-w-7xl mx-auto">
        <header className="mb-10 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-gray-900 tracking-tight">Admin Dashboard</h1>
            <p className="text-gray-500 mt-1">Manage system users and professional invitations.</p>
          </div>
          <div className="flex items-center space-x-3 bg-white px-4 py-2 rounded-2xl shadow-sm border border-gray-100">
            <Shield className="h-5 w-5 text-indigo-600" />
            <span className="font-semibold text-gray-700">Administrator Access</span>
          </div>
        </header>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Invite Form */}
          <section className="lg:col-span-1">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
              <div className="flex items-center space-x-2 mb-6">
                <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                  <UserPlus className="h-5 w-5" />
                </div>
                <h2 className="text-xl font-bold text-gray-900">Invite Member</h2>
              </div>
              
              <form onSubmit={handleInvite} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="name@example.com"
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Assigned Role</label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all appearance-none bg-no-repeat bg-[right_1rem_center]"
                  >
                    <option value="lawyer">Lawyer</option>
                    <option value="admin">Administrator</option>
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={inviteLoading}
                  className="w-full py-3 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-semibold rounded-xl transition-all shadow-md shadow-indigo-100 flex items-center justify-center space-x-2"
                >
                  {inviteLoading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Mail className="h-5 w-5" />}
                  <span>Send Invitation</span>
                </button>
              </form>

              {message && (
                <div className={`mt-6 p-4 rounded-xl text-sm font-medium ${message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                  {message.text}
                </div>
              )}
            </div>
          </section>

          {/* User Table */}
          <section className="lg:col-span-2">
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
              <div className="p-6 border-b border-gray-50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center space-x-2">
                  <div className="p-2 bg-gray-50 rounded-lg text-gray-600">
                    <Users className="h-5 w-5" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900">System Users</h2>
                </div>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search users..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10 pr-4 py-2 bg-gray-50 border-none rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none w-full md:w-64"
                  />
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-gray-50/50 text-gray-500 text-xs uppercase tracking-wider font-semibold">
                      <th className="px-6 py-4">User</th>
                      <th className="px-6 py-4">Role</th>
                      <th className="px-6 py-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {loading ? (
                      <tr>
                        <td colSpan="3" className="px-6 py-12 text-center">
                          <Loader2 className="h-8 w-8 animate-spin text-indigo-500 mx-auto" />
                        </td>
                      </tr>
                    ) : filteredUsers.length === 0 ? (
                      <tr>
                        <td colSpan="3" className="px-6 py-12 text-center text-gray-400">No users found.</td>
                      </tr>
                    ) : (
                      filteredUsers.map((user) => (
                        <tr key={user.user_id} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center space-x-3">
                              <div className="h-10 w-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold">
                                {user.user_profiles?.display_name?.charAt(0) || user.email?.charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <p className="font-semibold text-gray-900">{user.user_profiles?.display_name || "New User"}</p>
                                <p className="text-sm text-gray-500">{user.email}</p>
                              </div>
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                              user.role === 'admin' ? 'bg-purple-100 text-purple-700' :
                              user.role === 'lawyer' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'
                            }`}>
                              {user.role.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end space-x-2">
                              {user.role !== 'lawyer' && user.role !== 'admin' && (
                                <button
                                  onClick={() => handlePromote(user.user_id, 'lawyer')}
                                  className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors title='Promote to Lawyer'"
                                >
                                  <ArrowUpCircle className="h-5 w-5" />
                                </button>
                              )}
                              {user.role !== 'admin' && (
                                <button
                                  onClick={() => handlePromote(user.user_id, 'admin')}
                                  className="p-2 text-purple-600 hover:bg-purple-50 rounded-lg transition-colors title='Promote to Admin'"
                                >
                                  <Shield className="h-5 w-5" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
