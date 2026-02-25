import React from "react";

const BackgroundLayer = ({ theme = "dark" }) => {
  const isDark = theme === "dark";

  // Dark theme background (blue/light blue on dark base)
  if (isDark) {
    return (
      <div
        className="fixed inset-0 -z-10 overflow-hidden"
        style={{
          background: `
            radial-gradient(ellipse at top left, rgba(59, 130, 246, 0.3) 0%, transparent 50%),
            radial-gradient(ellipse at top right, rgba(14, 165, 233, 0.3) 0%, transparent 50%),
            radial-gradient(ellipse at bottom left, rgba(37, 99, 235, 0.2) 0%, transparent 50%),
            radial-gradient(ellipse at bottom right, rgba(56, 189, 248, 0.2) 0%, transparent 50%),
            linear-gradient(135deg, #0A0A0A 0%, #111111 50%, #0A0A0A 100%)
          `,
        }}
      >
        {/* Blurred overlay for depth */}
        <div
          className="absolute inset-0"
          style={{
            background: `
              radial-gradient(circle at 20% 30%, rgba(59, 130, 246, 0.15) 0%, transparent 40%),
              radial-gradient(circle at 80% 70%, rgba(14, 165, 233, 0.15) 0%, transparent 40%),
              radial-gradient(circle at 50% 50%, rgba(37, 99, 235, 0.1) 0%, transparent 60%)
            `,
            filter: "blur(60px)",
            opacity: 0.8,
          }}
        />
        
        {/* Additional gradient layers for mountain-like effect */}
        <div
          className="absolute inset-0"
          style={{
            background: `
              linear-gradient(180deg, transparent 0%, rgba(59, 130, 246, 0.05) 40%, rgba(14, 165, 233, 0.05) 60%, transparent 100%)
            `,
            filter: "blur(40px)",
          }}
        />
      </div>
    );
  }

  // Light theme background (soft blue/light blue on light base)
  return (
    <div
      className="fixed inset-0 -z-10 overflow-hidden"
      style={{
        background: `
          radial-gradient(ellipse at top left, rgba(96, 165, 250, 0.15) 0%, transparent 50%),
          radial-gradient(ellipse at top right, rgba(56, 189, 248, 0.15) 0%, transparent 50%),
          radial-gradient(ellipse at bottom left, rgba(147, 197, 253, 0.12) 0%, transparent 50%),
          radial-gradient(ellipse at bottom right, rgba(125, 211, 252, 0.12) 0%, transparent 50%),
          linear-gradient(135deg, #FAFAFA 0%, #F5F5F5 50%, #FFFFFF 100%)
        `,
      }}
    >
      {/* Blurred overlay for depth - light theme */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(circle at 20% 30%, rgba(96, 165, 250, 0.08) 0%, transparent 40%),
            radial-gradient(circle at 80% 70%, rgba(56, 189, 248, 0.08) 0%, transparent 40%),
            radial-gradient(circle at 50% 50%, rgba(147, 197, 253, 0.06) 0%, transparent 60%)
          `,
          filter: "blur(80px)",
          opacity: 0.9,
        }}
      />
      
      {/* Additional gradient layers for soft atmospheric effect */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            linear-gradient(180deg, transparent 0%, rgba(96, 165, 250, 0.03) 40%, rgba(56, 189, 248, 0.03) 60%, transparent 100%)
          `,
          filter: "blur(50px)",
        }}
      />
      
      {/* Subtle cloud-like effect */}
      <div
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(ellipse at 30% 20%, rgba(255, 255, 255, 0.4) 0%, transparent 50%),
            radial-gradient(ellipse at 70% 80%, rgba(255, 255, 255, 0.3) 0%, transparent 50%)
          `,
          filter: "blur(100px)",
          opacity: 0.6,
        }}
      />
    </div>
  );
};

export default BackgroundLayer;

