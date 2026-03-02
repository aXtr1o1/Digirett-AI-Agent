import React from "react";

const GlowingOrb = ({ theme = "dark", size = 40 }) => {
  const isDark = theme === "dark";

  return (
    <div
      style={{
        position: "relative",
        width: `${size}px`,
        height: `${size}px`,
        margin: "0 auto",
      }}
    >
      {/* Main Orb */}
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: "50%",
          background: isDark
            ? `radial-gradient(circle at 30% 30%, 
                rgba(59, 130, 246, 0.7) 0%, 
                rgba(37, 99, 235, 0.5) 20%, 
                rgba(96, 165, 250, 0.35) 40%, 
                rgba(14, 165, 233, 0.25) 60%, 
                rgba(59, 130, 246, 0.15) 80%, 
                transparent 100%)`
            : `radial-gradient(circle at 30% 30%, 
                rgba(96, 165, 250, 0.8) 0%, 
                rgba(147, 197, 253, 0.6) 25%, 
                rgba(56, 189, 248, 0.5) 50%, 
                rgba(125, 211, 252, 0.4) 75%, 
                rgba(96, 165, 250, 0.3) 100%)`,
          boxShadow: isDark
            ? `0 0 40px rgba(59, 130, 246, 0.25), 
               0 0 70px rgba(37, 99, 235, 0.15), 
               0 0 100px rgba(14, 165, 233, 0.08),
               inset 0 0 30px rgba(59, 130, 246, 0.15)`
            : `0 0 60px rgba(96, 165, 250, 0.4), 
               0 0 100px rgba(147, 197, 253, 0.3), 
               0 0 140px rgba(56, 189, 248, 0.2),
               inset 0 0 40px rgba(96, 165, 250, 0.2)`,
          animation: "pulse-glow 3s ease-in-out infinite alternate",
          position: "absolute",
          zIndex: 1,
        }}
      >
        {/* Inner highlight */}
        <div
          style={{
            position: "absolute",
            top: "20%",
            left: "25%",
            width: "35%",
            height: "35%",
            borderRadius: "50%",
            background: isDark
              ? `radial-gradient(circle, 
                  rgba(255, 255, 255, 0.3) 0%, 
                  rgba(255, 255, 255, 0.08) 50%, 
                  transparent 100%)`
              : `radial-gradient(circle, 
                  rgba(255, 255, 255, 0.6) 0%, 
                  rgba(255, 255, 255, 0.2) 50%, 
                  transparent 100%)`,
            filter: "blur(8px)",
          }}
        />

        {/* Secondary highlight */}
        <div
          style={{
            position: "absolute",
            top: "10%",
            right: "20%",
            width: "25%",
            height: "25%",
            borderRadius: "50%",
            background: isDark
              ? `radial-gradient(circle, 
                  rgba(14, 165, 233, 0.35) 0%, 
                  rgba(14, 165, 233, 0.15) 50%, 
                  transparent 100%)`
              : `radial-gradient(circle, 
                  rgba(56, 189, 248, 0.4) 0%, 
                  rgba(56, 189, 248, 0.2) 50%, 
                  transparent 100%)`,
            filter: "blur(10px)",
          }}
        />
      </div>

      {/* Outer glow rings */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "120%",
          height: "120%",
          borderRadius: "50%",
          background: isDark
            ? `radial-gradient(circle, 
                transparent 40%, 
                rgba(59, 130, 246, 0.06) 50%, 
                rgba(37, 99, 235, 0.04) 60%, 
                transparent 70%)`
            : `radial-gradient(circle, 
                transparent 40%, 
                rgba(96, 165, 250, 0.15) 50%, 
                rgba(147, 197, 253, 0.1) 60%, 
                transparent 70%)`,
          animation: "rotate-slow 8s linear infinite",
          zIndex: 0,
        }}
      />

      {/* Additional outer glow */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "140%",
          height: "140%",
          borderRadius: "50%",
          background: isDark
            ? `radial-gradient(circle, 
                transparent 50%, 
                rgba(14, 165, 233, 0.05) 60%, 
                rgba(56, 189, 248, 0.03) 70%, 
                transparent 80%)`
            : `radial-gradient(circle, 
                transparent 50%, 
                rgba(56, 189, 248, 0.1) 60%, 
                rgba(125, 211, 252, 0.08) 70%, 
                transparent 80%)`,
          animation: "rotate-slow-reverse 12s linear infinite",
          zIndex: 0,
        }}
      />

      <style>{`
        @keyframes pulse-glow {
          0% {
            box-shadow: ${isDark
              ? `0 0 40px rgba(59, 130, 246, 0.25), 
                 0 0 70px rgba(37, 99, 235, 0.15), 
                 0 0 100px rgba(14, 165, 233, 0.08),
                 inset 0 0 30px rgba(59, 130, 246, 0.15)`
              : `0 0 60px rgba(96, 165, 250, 0.4), 
                 0 0 100px rgba(147, 197, 253, 0.3), 
                 0 0 140px rgba(56, 189, 248, 0.2),
                 inset 0 0 40px rgba(96, 165, 250, 0.2)`};
          }
          100% {
            box-shadow: ${isDark
              ? `0 0 50px rgba(59, 130, 246, 0.3), 
                 0 0 85px rgba(37, 99, 235, 0.18), 
                 0 0 120px rgba(14, 165, 233, 0.1),
                 inset 0 0 35px rgba(59, 130, 246, 0.18)`
              : `0 0 80px rgba(96, 165, 250, 0.6), 
                 0 0 120px rgba(147, 197, 253, 0.4), 
                 0 0 160px rgba(56, 189, 248, 0.3),
                 inset 0 0 50px rgba(96, 165, 250, 0.3)`};
          }
        }

        @keyframes rotate-slow {
          from {
            transform: translate(-50%, -50%) rotate(0deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(360deg);
          }
        }

        @keyframes rotate-slow-reverse {
          from {
            transform: translate(-50%, -50%) rotate(360deg);
          }
          to {
            transform: translate(-50%, -50%) rotate(0deg);
          }
        }
      `}</style>
    </div>
  );
};

export default GlowingOrb;

