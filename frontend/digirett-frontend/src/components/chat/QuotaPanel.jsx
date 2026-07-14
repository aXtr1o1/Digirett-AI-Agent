import React, { useState, useEffect, useCallback, useRef } from "react";
import documentService from "../../services/documentService";
import { ChevronDown, ChevronUp, Zap } from "lucide-react";

/* ─── Color thresholds ─────────────────────────────────── */
const barColor = (used, max) => {
  const pct = max > 0 ? (used / max) * 100 : 0;
  if (pct >= 90) return { fill: "#ef4444", glow: "rgba(239,68,68,0.35)", label: "#ef4444" };
  if (pct >= 70) return { fill: "#f59e0b", glow: "rgba(245,158,11,0.3)",  label: "#f59e0b" };
  return           { fill: "#22c55e", glow: "rgba(34,197,94,0.25)",   label: "#22c55e" };
};

const formatCountdown = (resetAt) => {
  if (!resetAt) return null;
  const diff = new Date(resetAt) - new Date();
  if (diff <= 0) return "Resetting…";
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  const s = Math.floor((diff % 60_000) / 1_000);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
};

/* ─── Single bar row ───────────────────────────────────── */
function UsageBar({ label, used, max, isDark, countdown }) {
  const pct = Math.min(max > 0 ? (used / max) * 100 : 0, 100);
  const isAtLimit = used >= max;
  const c = barColor(used, max);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
      {/* Label + numbers */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{
          fontSize: "11px",
          fontWeight: 600,
          color: isDark ? "#94a3b8" : "#64748b",
          letterSpacing: "0.02em",
        }}>
          {label}
        </span>
        <span style={{
          fontSize: "11px",
          fontWeight: 700,
          color: c.label,
          fontVariantNumeric: "tabular-nums",
          fontFamily: "ui-monospace, 'SF Mono', monospace",
        }}>
          {used}
          <span style={{ opacity: 0.45, fontWeight: 500, color: isDark ? "#64748b" : "#94a3b8" }}>
            {" "}/{" "}{max}
          </span>
        </span>
      </div>

      {/* Track */}
      <div style={{
        position: "relative",
        height: "4px",
        borderRadius: "99px",
        background: isDark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.08)",
        overflow: "hidden",
      }}>
        {/* Animated fill */}
        <div style={{
          position: "absolute",
          inset: 0,
          width: `${pct}%`,
          borderRadius: "99px",
          background: c.fill,
          boxShadow: pct > 0 ? `0 0 8px ${c.glow}` : "none",
          transition: "width 0.7s cubic-bezier(0.4, 0, 0.2, 1), background 0.4s ease, box-shadow 0.4s ease",
        }} />
      </div>

      {/* Warning / Limit message */}
      {pct >= 80 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "6px" }}>
          <p style={{
            fontSize: "10px",
            fontWeight: 600,
            color: c.label,
            margin: 0,
            opacity: 0.9,
            animation: isAtLimit ? "pulse 2s ease-in-out infinite" : "none",
          }}>
            {isAtLimit ? "⚠ Limit reached" : "Running low"}
          </p>
          {/* Show reset countdown only when fully at limit */}
          {isAtLimit && countdown && (
            <span style={{
              fontSize: "10px",
              fontWeight: 600,
              color: isDark ? "#94a3b8" : "#64748b",
              fontFamily: "ui-monospace, 'SF Mono', monospace",
              whiteSpace: "nowrap",
            }}>
              available in{" "}
              <strong style={{ color: isDark ? "#e2e8f0" : "#1e293b" }}>
                {countdown}
              </strong>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── MAIN COMPONENT ───────────────────────────────────── */
export default function QuotaPanel({ conversationId, isDark }) {
  const [quota, setQuota]       = useState(null);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem("quota-panel-collapsed");
      return saved !== null ? JSON.parse(saved) : true;
    } catch (e) {
      return true;
    }
  });
  const [countdown, setCountdown] = useState(null);
  const [pulse, setPulse]       = useState(false);          // subtle dot pulse on refresh
  const intervalRef             = useRef(null);
  const countdownRef            = useRef(null);

  const toggleCollapse = () => {
    setCollapsed(prev => {
      const next = !prev;
      try {
        localStorage.setItem("quota-panel-collapsed", JSON.stringify(next));
      } catch (e) {
        // ignore exceptions
      }
      return next;
    });
  };

  /* ── fetch ── */
  const fetchQuota = useCallback(async () => {
    const queryId = conversationId || "new-chat";
    try {
      const data = await documentService.getSessionStatus(queryId);
      setQuota(data);
      setPulse(true);
      setTimeout(() => setPulse(false), 600);
    } catch {
      /* silently fail — non-critical UI */
    }
  }, [conversationId]);

  /* initial + polling every 10 s */
  useEffect(() => {
    fetchQuota();
    intervalRef.current = setInterval(fetchQuota, 10_000);
    return () => clearInterval(intervalRef.current);
  }, [fetchQuota]);

  /* live countdown */
  useEffect(() => {
    if (!quota?.reset_at) return;
    const tick = () => setCountdown(formatCountdown(quota.reset_at));
    tick();
    countdownRef.current = setInterval(tick, 1_000);
    return () => clearInterval(countdownRef.current);
  }, [quota?.reset_at]);

  /* hide when no data */
  if (!quota) return null;

  const turns = quota.turn_count  ?? 0;
  const maxTurns = turns + (quota.turns_remaining ?? 10);
  const docs  = quota.doc_count   ?? 0;
  const maxDocs = docs + (quota.docs_remaining ?? 2);

  /* theme tokens */
  const bg      = isDark ? "rgba(15,23,42,0.75)" : "rgba(255,255,255,0.82)";
  const border  = isDark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.07)";
  const title   = isDark ? "#cbd5e1" : "#475569";
  const divider = isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.05)";

  return (
    <div style={{
      margin: "0 10px 10px",
      borderRadius: "14px",
      border: `1px solid ${border}`,
      background: bg,
      backdropFilter: "blur(20px)",
      WebkitBackdropFilter: "blur(20px)",
      flexShrink: 0,
      overflow: "hidden",
    }}>
      {/* ── Header ── */}
      <button
        onClick={toggleCollapse}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          background: "transparent",
          border: "none",
          outline: "none",
          cursor: "pointer",
          gap: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "7px" }}>
          {/* Live indicator dot */}
          <div style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: pulse ? "#22c55e" : (isDark ? "#334155" : "#cbd5e1"),
            transition: "background 0.3s ease",
            flexShrink: 0,
          }} />
          <span style={{
            fontSize: "10px",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: "0.09em",
            color: title,
          }}>
            Session Usage
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={12} style={{ color: title, opacity: 0.6 }} />
          : <ChevronUp size={12} style={{ color: title, opacity: 0.6 }} />
        }
      </button>

      {/* ── Body ── */}
      {!collapsed && (
        <div style={{ padding: "0 14px 13px", display: "flex", flexDirection: "column", gap: "11px" }}>

          {/* Divider */}
          <div style={{ height: "1px", background: divider, marginBottom: "1px" }} />

          <UsageBar label="Turns" used={turns} max={maxTurns} isDark={isDark} countdown={countdown} />
          <UsageBar label="Docs"  used={docs}  max={maxDocs}  isDark={isDark} countdown={countdown} />

          {/* Reset countdown */}
          {countdown && (
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: "5px",
              padding: "7px 10px",
              borderRadius: "8px",
              background: isDark ? "rgba(99,102,241,0.07)" : "rgba(99,102,241,0.06)",
              border: "1px solid rgba(99,102,241,0.12)",
              marginTop: "1px",
            }}>
              <Zap size={10} color="#818cf8" style={{ flexShrink: 0 }} />
              <span style={{
                fontSize: "10px",
                fontWeight: 600,
                color: isDark ? "#a5b4fc" : "#6366f1",
                fontVariantNumeric: "tabular-nums",
              }}>
                Resets in{" "}
                <strong style={{ fontFamily: "ui-monospace, 'SF Mono', monospace" }}>
                  {countdown}
                </strong>
              </span>
            </div>
          )}

          {/* Auto-refresh note */}
          <p style={{
            fontSize: "9px",
            color: isDark ? "#334155" : "#cbd5e1",
            margin: 0,
            textAlign: "right",
          }}>
            Auto-updates every 10s
          </p>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}
