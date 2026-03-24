import React from "react";
import { AlertTriangle } from "lucide-react";

const UpgradeCard = ({ theme = "dark" }) => {
  const isDark = theme === "dark";

  return (
    <div
      style={{
        margin: "12px",
        padding: "16px",
        borderRadius: "12px",
        backgroundColor: isDark
          ? "rgba(26, 26, 26, 0.85)"
          : "rgba(252, 252, 252, 0.9)",
        border: isDark
          ? "1px solid rgba(248, 250, 252, 0.08)"
          : "1px solid rgba(15, 23, 42, 0.08)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "8px",
        }}
      >
        <AlertTriangle
          size={18}
          style={{
            color: isDark ? "#f97316" : "#ea580c",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: "13px",
            fontWeight: "600",
            letterSpacing: "0.01em",
            color: isDark ? "#f9fafb" : "#111827",
            textTransform: "uppercase",
          }}
        >
          Beta version
        </span>
      </div>
      <p
        style={{
          fontSize: "12px",
          lineHeight: "1.6",
          color: isDark ? "#d1d5db" : "#4b5563",
          marginBottom: "4px",
        }}
      >
        DigiRett is currently in beta. Responses may be incomplete or inaccurate
        and should not be treated as formal legal advice.
      </p>
      {/* <p
        style={{
          fontSize: "11px",
          lineHeight: "1.5",
          color: isDark ? "#9ca3af" : "#6b7280",
          marginTop: "6px",
        }}
      >
        Please verify all important information with a qualified professional
        before making legal or business decisions.
      </p> */}
    </div>
  );
};

export default UpgradeCard;

