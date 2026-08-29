import React, { createContext, useContext, useState, useEffect } from "react";
import { useUser } from "@clerk/clerk-react";

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
  const { user, isLoaded } = useUser();
  const [theme, setTheme] = useState("light");

  // Load and apply theme when user state changes
  useEffect(() => {
    if (isLoaded) {
      if (user?.id) {
        const savedTheme = localStorage.getItem(`theme_${user.id}`) || user.unsafeMetadata?.theme || "light";
        setTheme(savedTheme);
      } else {
        const guestTheme = localStorage.getItem("theme_guest") || "light";
        setTheme(guestTheme);
      }
    }
  }, [user?.id, isLoaded]);

  const isDark = theme === "dark";

  // Persist theme choice and update document body
  useEffect(() => {
    console.log(`[ThemeProvider] Global theme set to: ${theme}`);
    // Save to legacy 'theme' key for any older static files if needed, but also update active keys
    localStorage.setItem("theme", theme);
    if (isLoaded) {
      if (user?.id) {
        localStorage.setItem(`theme_${user.id}`, theme);
      } else {
        localStorage.setItem("theme_guest", theme);
      }
    }

    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [theme, isDark, user?.id, isLoaded]);

  const toggleTheme = () => {
    const nextTheme = theme === "light" ? "dark" : "light";
    setTheme(nextTheme);

    if (isLoaded && user?.id) {
      localStorage.setItem(`theme_${user.id}`, nextTheme);
      // Persist to Clerk unsafeMetadata for multi-device syncing
      user.update({ unsafeMetadata: { theme: nextTheme } }).catch(err => {
        console.warn("Failed to persist theme to Clerk metadata:", err);
      });
    } else {
      localStorage.setItem("theme_guest", nextTheme);
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, isDark, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};
