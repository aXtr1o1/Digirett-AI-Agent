import React, { useEffect, useState } from "react";
import adminService from "../services/adminService";
import { Users, Mail, Shield, ArrowUpCircle, Loader2, Search, UserPlus, CheckCircle, ArrowLeft } from "lucide-react";
import { useTheme } from "../providers/ThemeProvider";
import BackgroundLayer from "../components/common/BackgroundLayer";
import { Link } from "react-router-dom";

export default function AdminDashboard() {
  const { theme, isDark } = useTheme();
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
      const validUsers = data.filter(u => u.email);
      setUsers(validUsers);
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
      console.error("Promotion failed:", err);
      setMessage({ type: "error", text: err.message || "Promotion failed" });
    }
  };

  const filteredUsers = users.filter(u => {
    const email = (u.email || "").toLowerCase();
    const displayName = (u.user_profiles?.display_name || "").toLowerCase();
    const query = searchQuery.toLowerCase();
    return email.includes(query) || displayName.includes(query);
  });

  return (
    <div className={`min-h-screen relative overflow-hidden ${isDark ? "text-white" : "text-gray-900"}`}>
      <BackgroundLayer theme={theme} />
      
      <div className="relative z-10 p-6 md:p-10">
        <div className="max-w-7xl mx-auto">
          {/* Navigation Header */}
          <div className="mb-8">
            <Link 
              to="/chat" 
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
                isDark ? "bg-gray-800/50 hover:bg-gray-700 text-gray-300" : "bg-white hover:bg-gray-50 text-gray-600 shadow-sm"
              }`}
            >
              <ArrowLeft size={18} />
              <span className="font-medium">Back to Chat</span>
            </Link>
          </div>

          {/* Notifications */}
          {message && (
            <div className={`mb-6 p-4 rounded-2xl flex items-center justify-between ${
              message.type === 'success' 
                ? isDark ? 'bg-green-900/30 text-green-400 border border-green-800' : 'bg-green-50 text-green-800 border border-green-100'
                : isDark ? 'bg-red-900/30 text-red-400 border border-red-800' : 'bg-red-50 text-red-800 border border-red-100'
            }`}>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-5 w-5" />
                <span className="font-semibold">{message.text}</span>
              </div>
              <button onClick={() => setMessage(null)} className="text-current opacity-50 hover:opacity-100">
                &times;
              </button>
            </div>
          )}

          <header className="mb-10 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1 className={`text-4xl font-black tracking-tight ${isDark ? "text-white" : "text-gray-900"}`}>Admin Dashboard</h1>
              <p className={isDark ? "text-gray-400" : "text-gray-500"}>Manage system users and professional invitations.</p>
            </div>
            <div className={`flex items-center space-x-3 px-6 py-3 rounded-2xl shadow-sm border ${
              isDark ? "bg-gray-800/50 border-gray-700 text-gray-300" : "bg-white border-gray-100 text-gray-700"
            }`}>
              <Shield className="h-5 w-5 text-indigo-500" />
              <span className="font-bold tracking-wide">ADMINISTRATOR ACCESS</span>
            </div>
          </header>

          {/* Stats Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-10">
            {[
              { label: "Total Users", value: users.length, icon: Users, color: "blue" },
              { label: "Lawyers", value: users.filter(u => u.role === 'lawyer').length, icon: ArrowUpCircle, color: "indigo" },
              { label: "Admins", value: users.filter(u => u.role === 'admin').length, icon: Shield, color: "purple" },
              { label: "Users", value: users.filter(u => u.role === 'user' || !u.role).length, icon: Users, color: "gray" }
            ].map((stat, idx) => (
              <div key={idx} className={`p-6 rounded-3xl shadow-sm border flex items-center gap-5 transition-transform hover:scale-[1.02] ${
                isDark ? "bg-gray-800/40 border-gray-700" : "bg-white border-gray-100"
              }`}>
                <div className={`h-14 w-14 rounded-2xl flex items-center justify-center ${
                  isDark ? `bg-${stat.color}-900/30 text-${stat.color}-400` : `bg-${stat.color}-50 text-${stat.color}-600`
                }`}>
                  <stat.icon className="h-7 w-7" />
                </div>
                <div>
                  <p className={`text-sm font-bold uppercase tracking-widest ${isDark ? "text-gray-500" : "text-gray-400"}`}>{stat.label}</p>
                  <h3 className={`text-2xl font-black ${isDark ? "text-white" : "text-gray-900"}`}>{stat.value}</h3>
                </div>
              </div>
            ))}
          </div>

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Invite Form */}
            <section className="lg:col-span-1">
              <div className={`rounded-3xl shadow-sm border p-8 ${
                isDark ? "bg-gray-800/40 border-gray-700" : "bg-white border-gray-100"
              }`}>
                <div className="flex items-center space-x-3 mb-8">
                  <div className={`p-3 rounded-2xl ${isDark ? "bg-indigo-900/30 text-indigo-400" : "bg-indigo-50 text-indigo-600"}`}>
                    <UserPlus className="h-6 w-6" />
                  </div>
                  <h2 className={`text-2xl font-bold ${isDark ? "text-white" : "text-gray-900"}`}>Invite Member</h2>
                </div>

                <form onSubmit={handleInvite} className="space-y-6">
                  <div>
                    <label className={`block text-sm font-bold mb-2 ${isDark ? "text-gray-400" : "text-gray-700"}`}>Email Address</label>
                    <input
                      type="email"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      placeholder="name@example.com"
                      className={`w-full px-5 py-4 rounded-2xl border outline-none transition-all ${
                        isDark ? "bg-gray-900/50 border-gray-700 text-white focus:ring-2 focus:ring-indigo-900" : "bg-gray-50 border-gray-200 focus:ring-2 focus:ring-indigo-500"
                      }`}
                      required
                    />
                  </div>
                  <div>
                    <label className={`block text-sm font-bold mb-2 ${isDark ? "text-gray-400" : "text-gray-700"}`}>Assigned Role</label>
                    <select
                      value={inviteRole}
                      onChange={(e) => setInviteRole(e.target.value)}
                      className={`w-full px-5 py-4 rounded-2xl border outline-none transition-all appearance-none bg-no-repeat bg-[right_1.25rem_center] ${
                        isDark ? "bg-gray-900/50 border-gray-700 text-white focus:ring-2 focus:ring-indigo-900" : "bg-gray-50 border-gray-200 focus:ring-2 focus:ring-indigo-500"
                      }`}
                    >
                      <option value="lawyer">Lawyer</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </div>
                  <button
                    type="submit"
                    disabled={inviteLoading}
                    className="w-full py-4 px-6 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white font-bold rounded-2xl transition-all shadow-lg shadow-indigo-900/20 flex items-center justify-center space-x-3"
                  >
                    {inviteLoading ? <Loader2 className="h-6 w-6 animate-spin" /> : <Mail className="h-6 w-6" />}
                    <span>Send Professional Invitation</span>
                  </button>
                </form>
              </div>
            </section>

            {/* User Table */}
            <section className="lg:col-span-2">
              <div className={`rounded-3xl shadow-sm border overflow-hidden ${
                isDark ? "bg-gray-800/40 border-gray-700" : "bg-white border-gray-100"
              }`}>
                <div className={`p-8 border-b flex flex-col md:flex-row md:items-center justify-between gap-6 ${isDark ? "border-gray-700" : "border-gray-50"}`}>
                  <div className="flex items-center space-x-3">
                    <div className={`p-3 rounded-2xl ${isDark ? "bg-gray-700 text-gray-300" : "bg-gray-50 text-gray-600"}`}>
                      <Users className="h-6 w-6" />
                    </div>
                    <h2 className={`text-2xl font-bold ${isDark ? "text-white" : "text-gray-900"}`}>System Users</h2>
                  </div>
                  <div className="relative">
                    <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search users..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className={`pl-12 pr-6 py-3 border-none rounded-2xl text-sm outline-none w-full md:w-80 ${
                        isDark ? "bg-gray-900/50 text-white focus:ring-2 focus:ring-indigo-900" : "bg-gray-50 focus:ring-2 focus:ring-indigo-500"
                      }`}
                    />
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className={`text-xs uppercase tracking-widest font-black ${isDark ? "bg-gray-900/30 text-gray-500" : "bg-gray-50/50 text-gray-400"}`}>
                        <th className="px-8 py-5">User</th>
                        <th className="px-8 py-5">Role</th>
                        <th className="px-8 py-5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className={`divide-y ${isDark ? "divide-gray-700" : "divide-gray-50"}`}>
                      {loading ? (
                        <tr>
                          <td colSpan="3" className="px-8 py-20 text-center">
                            <Loader2 className="h-10 w-10 animate-spin text-indigo-500 mx-auto" />
                          </td>
                        </tr>
                      ) : filteredUsers.length === 0 ? (
                        <tr>
                          <td colSpan="3" className={`px-8 py-20 text-center text-lg ${isDark ? "text-gray-600" : "text-gray-400"}`}>No users found matching your search.</td>
                        </tr>
                      ) : (
                        filteredUsers.map((user) => (
                          <tr key={user.user_id} className={`transition-colors ${isDark ? "hover:bg-gray-700/30" : "hover:bg-gray-50/50"}`}>
                            <td className="px-8 py-6">
                              <div className="flex items-center space-x-4">
                                <div className={`h-12 w-12 rounded-2xl flex items-center justify-center font-black text-lg ${
                                  isDark ? "bg-indigo-900/40 text-indigo-300" : "bg-indigo-100 text-indigo-700"
                                }`}>
                                  {(user.user_profiles?.display_name || user.email || "?").charAt(0).toUpperCase()}
                                </div>
                                <div>
                                  <p className={`font-bold text-lg ${isDark ? "text-white" : "text-gray-900"}`}>{user.user_profiles?.display_name || "New User"}</p>
                                  <p className={`text-sm ${isDark ? "text-gray-500" : "text-gray-500"}`}>{user.email}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-8 py-6">
                              <span className={`inline-flex items-center px-4 py-1 rounded-full text-[10px] font-black tracking-widest uppercase ${
                                user.role === 'admin' ? isDark ? 'bg-purple-900/40 text-purple-300' : 'bg-purple-100 text-purple-700' :
                                user.role === 'lawyer' ? isDark ? 'bg-blue-900/40 text-blue-300' : 'bg-blue-100 text-blue-700' : 
                                isDark ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-700'
                                }`}>
                                {user.role || 'user'}
                              </span>
                            </td>
                            <td className="px-8 py-6 text-right">
                              <div className="flex flex-col sm:flex-row items-center justify-end gap-3">
                                {user.role !== 'lawyer' && (
                                  <button
                                    onClick={() => handlePromote(user.user_id, 'lawyer')}
                                    className={`whitespace-nowrap px-4 py-2 rounded-xl transition-all text-xs font-black border flex items-center gap-2 ${
                                      isDark 
                                        ? "bg-blue-900/20 text-blue-400 border-blue-800 hover:bg-blue-800 hover:text-white" 
                                        : "bg-blue-50 text-blue-600 border-blue-100 hover:bg-blue-600 hover:text-white"
                                    }`}
                                  >
                                    <ArrowUpCircle className="h-4 w-4" />
                                    <span>Promote to Lawyer</span>
                                  </button>
                                )}
                                {user.role !== 'admin' && (
                                  <button
                                    onClick={() => handlePromote(user.user_id, 'admin')}
                                    className={`whitespace-nowrap px-4 py-2 rounded-xl transition-all text-xs font-black border flex items-center gap-2 ${
                                      isDark 
                                        ? "bg-purple-900/20 text-purple-400 border-purple-800 hover:bg-purple-800 hover:text-white" 
                                        : "bg-purple-50 text-purple-600 border-purple-100 hover:bg-purple-600 hover:text-white"
                                    }`}
                                  >
                                    <Shield className="h-4 w-4" />
                                    <span>Promote to Admin</span>
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
    </div>
  );
}
