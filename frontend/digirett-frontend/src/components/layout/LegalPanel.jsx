import React from "react";
import EscalationStatusCard from "../chat/EscalationStatusCard";
import { Gavel, Info } from "lucide-react";

const LegalPanel = ({ conversationId, theme = "dark" }) => {
  const isDark = theme === "dark";
  console.log("[LegalPanel] Render | conversationId:", conversationId);

  return (
    <aside
      style={{
        width: "320px",
        minWidth: "320px",
        maxWidth: "320px",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: isDark
          ? "rgba(17, 17, 17, 0.5)"
          : "rgba(250, 250, 250, 0.6)",
        borderLeft: isDark
          ? "1px solid rgba(42, 42, 42, 0.4)"
          : "1px solid rgba(229, 231, 235, 0.4)",
        borderRadius: "16px",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        overflow: "hidden",
        height: "calc(100% - 16px)",
        marginTop: "8px",
        marginBottom: "8px",
      }}
    >
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className={`px-6 py-5 border-b ${isDark ? "border-white/5" : "border-slate-200"}`}>
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
              isDark ? "bg-indigo-500/20 text-indigo-400" : "bg-indigo-100 text-indigo-600"
            }`}>
              <Gavel size={18} />
            </div>
            <div>
              <h3 className={`text-sm font-black tracking-tight ${isDark ? "text-white" : "text-slate-900"}`}>
                Legal Assistant
              </h3>
              <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 opacity-70">
                Active Escalation
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 sidebar-scrollbar-hidden">
          <div className="mb-6">
            <div className={`flex items-start gap-2 p-3 rounded-xl mb-4 text-[11px] leading-relaxed ${
              isDark ? "bg-white/5 text-slate-400" : "bg-slate-100 text-slate-600"
            }`}>
              <Info size={14} className="mt-0.5 flex-shrink-0" />
              <span>
                Your conversation has been escalated to a human lawyer. You can still chat with the AI, but a specialized professional will review your case.
              </span>
            </div>
          </div>

          <EscalationStatusCard conversationId={conversationId} theme={theme} isSidebar={true} />
        </div>

        {/* Footer */}
        <div className={`px-6 py-4 border-t ${isDark ? "border-white/5" : "border-slate-200"}`}>
          <p className="text-[10px] text-center text-slate-500 font-medium">
            Secure Legal Workspace
          </p>
        </div>
      </div>
    </aside>
  );
};

export default LegalPanel;
