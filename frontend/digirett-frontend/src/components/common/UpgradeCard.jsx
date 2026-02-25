import React from "react";
import { Crown } from "lucide-react";

const UpgradeCard = ({ theme = "dark" }) => {
  const isDark = theme === "dark";

  return (
    <div
      style={{
        margin: "12px",
        padding: "16px",
        borderRadius: "12px",
        backgroundColor: isDark 
          ? "rgba(26, 26, 26, 0.8)" 
          : "rgba(245, 245, 245, 0.8)",
        border: isDark 
          ? "1px solid rgba(42, 42, 42, 0.5)" 
          : "1px solid rgba(229, 231, 235, 0.5)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px" }}>
        <Crown 
          size={18} 
          style={{ 
            color: isDark ? "#3B82F6" : "#2563EB",
            flexShrink: 0,
          }} 
        />
        <span
          style={{
            fontSize: "13px",
            fontWeight: "600",
            color: isDark ? "#ffffff" : "#111827",
          }}
        >
          Upgrade to premium
        </span>
      </div>
      <p
        style={{
          fontSize: "12px",
          lineHeight: "1.5",
          color: isDark ? "#9ca3af" : "#6b7280",
          marginBottom: "12px",
        }}
      >
        Boost productivity with seamless automation and responsive AI, built to adapt to your needs.
      </p>
      <button
        onClick={() => {
          // Handle upgrade click
          console.log("Upgrade clicked");
        }}
        style={{
          width: "100%",
          padding: "8px 12px",
          borderRadius: "8px",
          fontSize: "12px",
          fontWeight: "600",
          backgroundColor: isDark ? "#3B82F6" : "#2563EB",
          color: "#ffffff",
          border: "none",
          cursor: "pointer",
          transition: "all 0.2s",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = isDark ? "#2563EB" : "#1D4ED8";
          e.currentTarget.style.transform = "translateY(-1px)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = isDark ? "#3B82F6" : "#2563EB";
          e.currentTarget.style.transform = "translateY(0)";
        }}
      >
        Upgrade
      </button>
    </div>
  );
};

export default UpgradeCard;

