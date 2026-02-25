import React, { useState } from "react";
import { Sun, Moon, User } from "lucide-react";

const Header = ({ theme, onToggleTheme }) => {
  const isDark = theme === "dark";
  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    localStorage.removeItem("token");
    window.location.href = "/sign-in";
  };

  return (
    <header
      style={{
        height: "56px",
        borderBottom: isDark 
          ? "1px solid rgba(42, 42, 42, 0.4)" 
          : "1px solid rgba(229, 231, 235, 0.4)",
        backgroundColor: isDark 
          ? "rgba(17, 17, 17, 0.5)" 
          : "rgba(250, 250, 250, 0.6)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        display: "flex",
        alignItems: "center",
        color: isDark ? "#ffffff" : "#111827",
        borderTopLeftRadius: "16px",
        borderTopRightRadius: "16px",
        borderBottomLeftRadius: "16px",
        borderBottomRightRadius: "16px",
        marginBottom: "8px",
      }}
      className="relative"
    >
      {/* RIGHT SIDE CONTROLS */}
      <div className="ml-auto pr-6 relative flex items-center gap-3">

        {/* THEME TOGGLE (NOW RIGHT) */}
        <button
          onClick={onToggleTheme}
          aria-label="Toggle theme"
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all duration-300 ${
            isDark
              ? "border-gray-700 bg-[#1a1a1a] text-gray-300 hover:bg-[#2a2a2a] hover:text-white"
              : "border-gray-300 bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900"
          }`}
        >
          {isDark ? (
            <>
              <Sun className="h-3.5 w-3.5 text-yellow-400" />
              <span>Light</span>
            </>
          ) : (
            <>
              <Moon className="h-3.5 w-3.5 text-indigo-500" />
              <span>Dark</span>
            </>
          )}
        </button>

        {/* USER MENU */}
        <div className="relative">
          <button
            onClick={() => setOpen(!open)}
            className={`p-2 rounded-full transition ${
              isDark
                ? "hover:bg-gray-800 text-white"
                : "hover:bg-gray-200 text-gray-900"
            }`}
          >
            <User size={20} />
          </button>

          {open && (
            <div
              className={`absolute right-0 mt-2 w-44 rounded-lg shadow-lg border z-50 ${
                isDark
                  ? "bg-[#1a1a1a] border-gray-700 text-white"
                  : "bg-white border-gray-200 text-gray-900"
              }`}
            >
              <div
                className={`px-4 py-2 text-sm border-b ${
                  isDark ? "border-gray-700" : "border-gray-200"
                }`}
              >
                admin1
              </div>

              <button
                onClick={handleLogout}
                className="w-full text-left px-4 py-2 rounded-lg transition text-red-600 hover:bg-red-50"
              >
                Logout
              </button>
            </div>
          )}
        </div>

      </div>
    </header>
  );
};

export default Header;