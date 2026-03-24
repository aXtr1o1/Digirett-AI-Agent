// import React, { useState } from "react";
// import { useUser, useClerk } from "@clerk/clerk-react";
// import { LogOut, User, ChevronDown, Settings } from "lucide-react";

// const UserProfile = ({ theme = "dark" }) => {
//   const { user } = useUser();
//   const { signOut } = useClerk();
//   const [isOpen, setIsOpen] = useState(false);

//   if (!user) return null;

//   const isDark = theme === "dark";

//   // 🔥 guaranteed logout
//   const handleSignOut = async () => {
//     setIsOpen(false);
//     await signOut();              // clear session
//     window.location.href = "/sign-in"; // force redirect (100% works)
//   };

//   return (
//     <div className="relative z-50">
//       {/* Profile button */}
//       <button
//         onClick={() => setIsOpen(!isOpen)}
//         className={`flex items-center space-x-3 px-3 py-2 rounded-lg transition-colors
//         ${isDark ? "hover:bg-[#1a1a1a]" : "hover:bg-gray-100"}`}
//       >
//         {user.imageUrl ? (
//           <img
//             src={user.imageUrl}
//             alt="User"
//             className="h-10 w-10 rounded-full"
//           />
//         ) : (
//           <div
//             className={`h-10 w-10 rounded-full flex items-center justify-center
//             ${isDark ? "bg-white text-black" : "bg-gray-800 text-white"}`}
//           >
//             <User className="h-5 w-5" />
//           </div>
//         )}

//         <span className={`${isDark ? "text-white" : "text-gray-900"}`}>
//           {user.firstName || "User"}
//         </span>

//         <ChevronDown className="h-4 w-4" />
//       </button>

//       {/* Dropdown */}
//       {isOpen && (
//         <>
//           {/* background click closer */}
//           <div
//             className="fixed inset-0"
//             onClick={() => setIsOpen(false)}
//           />

//           {/* menu */}
//           <div
//             className={`absolute right-0 mt-2 w-48 rounded-lg shadow-lg border py-1
//             ${isDark ? "bg-[#1a1a1a] border-gray-800" : "bg-white border-gray-200"}`}
//           >
//             <button
//               className="w-full flex items-center px-4 py-2 text-sm hover:bg-gray-100"
//             >
//               <Settings className="h-4 w-4 mr-2" />
//               Settings
//             </button>

//             <button
//               onClick={handleSignOut}
//               className="w-full flex items-center px-4 py-2 text-sm text-red-600 hover:bg-red-50"
//             >
//               <LogOut className="h-4 w-4 mr-2" />
//               Sign out
//             </button>
//           </div>
//         </>
//       )}
//     </div>
//   );
// };

// export default UserProfile;
import React from "react";
import { useNavigate } from "react-router-dom";

export default function UserProfile({ theme = "dark" }) {
  const navigate = useNavigate();
  const isDark = theme === "dark";

  const logout = () => {
    localStorage.removeItem("user");
    navigate("/sign-in");
  };

  const user = localStorage.getItem("user");

  return (
    <div className={`flex items-center gap-3 ${isDark ? "text-white" : "text-gray-900"}`}>
      <span>{user}</span>
      <button
        onClick={logout}
        className="bg-red-500 px-3 py-1 rounded text-white"
      >
        Logout
      </button>
    </div>
  );
}