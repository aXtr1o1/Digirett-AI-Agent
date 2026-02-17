import React from "react";
import UserProfile from "../auth/UserProfile";
import { Sun, Moon } from "lucide-react";

const Header = ({ theme, onToggleTheme }) => {
  const isDark = theme === "dark";

  return (
    <header
      className={`relative h-14 border-b flex items-center ${
        isDark
          ? "border-gray-900 bg-black text-white"
          : "border-gray-200 bg-white text-gray-900"
      }`}
    >
      {/* Theme toggle */}
      <div className="ml-4">
        <button
          onClick={onToggleTheme}
          aria-label="Toggle theme"
          className={`
            flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold
            border transition-all duration-300
            ${
              isDark
                ? "border-gray-700 bg-[#1a1a1a] text-gray-300 hover:bg-[#2a2a2a] hover:text-white"
                : "border-gray-300 bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900"
            }
          `}
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
      </div>

      {/* Right side profile — theme passed down so username is visible in both modes */}
      <div className="ml-auto pr-6">
        <UserProfile theme={theme} />
      </div>
    </header>
  );
};

export default Header;