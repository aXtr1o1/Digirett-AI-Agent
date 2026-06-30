import React, { useState, useEffect, useCallback } from "react";
import adminService from "../../services/adminService";
import {
  AlertTriangle, Clock, CheckCircle, RefreshCw, Loader2,
  ChevronUp, ChevronDown, TrendingUp, Users, Star, Award
} from "lucide-react";

/* ─── helpers ─────────────────────────────────────────── */
const fmtHours = (h) => {
  if (h == null) return "-";
  if (h < 1) return `${Math.round(h * 60)}m`;
  return `${h.toFixed(1)}h`;
};
const fmtDays = (d) => {
  if (d == null) return "-";
  if (d < 1) return `${Math.round(d * 24)}h`;
  return `${d.toFixed(1)} days`;
};
const fmtWaitingText = (h) => {
  if (h == null) return "-";
  if (h < 24) {
    if (h < 1) return `${Math.round(h * 60)}m`;
    return `${Math.round(h)}h`;
  }
  let days = Math.floor(h / 24);
  let remainingHours = Math.round(h % 24);
  if (remainingHours === 24) {
    days += 1;
    remainingHours = 0;
  }
  if (remainingHours === 0) {
    return `${days} ${days === 1 ? "day" : "days"}`;
  }
  return `${days} ${days === 1 ? "day" : "days"} ${remainingHours}h`;
};
const fmtTicketId = (id) => (id ? `#${id.slice(0, 8).toUpperCase()}` : "-");

const ALERT_LABEL = {
  unclaimed:   { text: "No lawyer assigned", color: "#ef4444", bg: "rgba(239,68,68,0.08)" },
  no_booking:  { text: "No booking scheduled", color: "#f59e0b", bg: "rgba(245,158,11,0.08)" },
  no_resolve:  { text: "Unresolved after SLA", color: "#8b5cf6", bg: "rgba(139,92,246,0.08)" },
};

/* ─── sub-components ──────────────────────────────────── */
function KpiCard({ label, value, sublabel, statusText, statusColor, color, icon: Icon, isDark }) {
  return (
    <div style={{
      flex: 1,
      padding: "24px",
      borderRadius: "16px",
      border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`,
      background: isDark ? "rgba(15,23,42,0.8)" : "#fff",
      display: "flex",
      flexDirection: "column",
      justifyContent: "space-between",
      minWidth: "240px",
    }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
          <div style={{
            width: 36, height: 36, borderRadius: "10px",
            background: `${color}18`,
            display: "flex", alignItems: "center", justifyContent: "center"
          }}>
            <Icon size={16} color={color} />
          </div>
          <span style={{ fontSize: "12px", fontWeight: 700, color: isDark ? "#94a3b8" : "#64748b", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            {label}
          </span>
        </div>
        <p style={{ fontSize: "28px", fontWeight: 800, color: isDark ? "#f1f5f9" : "#0f172a", margin: 0 }}>
          {value}
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "16px", gap: "8px" }}>
        {sublabel && (
          <p style={{ fontSize: "11px", color: isDark ? "#64748b" : "#94a3b8", margin: 0 }}>
            {sublabel}
          </p>
        )}
        {statusText && (
          <span style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: "99px",
            backgroundColor: `${statusColor}15`,
            color: statusColor,
            border: `1px solid ${statusColor}30`,
            whiteSpace: "nowrap"
          }}>
            {statusText}
          </span>
        )}
      </div>
    </div>
  );
}

function StarRating({ value }) {
  if (value == null) return <span style={{ color: "#64748b", fontSize: "12px" }}>N/A</span>;
  const full = Math.round(value);
  return (
    <span style={{ display: "flex", alignItems: "center", gap: "3px" }}>
      {[1,2,3,4,5].map(i => (
        <Star key={i} size={12} fill={i <= full ? "#f59e0b" : "none"} color={i <= full ? "#f59e0b" : "#64748b"} />
      ))}
      <span style={{ fontSize: "12px", fontWeight: 700, color: "#f59e0b", marginLeft: "4px" }}>
        {value.toFixed(1)}
      </span>
    </span>
  );
}

/* ─── MAIN COMPONENT ──────────────────────────────────── */
export default function SlaView({ isDark, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState("avg_resolve_days");
  const [sortDir, setSortDir] = useState("asc");

  const fetchReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const report = await adminService.getSlaReport();
      
      // Adapt backend keys to frontend expected keys
      const formattedReport = {
        alerts: (report.active_breaches || report.alerts || []).map(alert => ({
          ...alert,
          type: alert.type === "claim_delay" ? "unclaimed" : (alert.type === "booking_delay" ? "no_booking" : alert.type),
          waiting_hours: alert.waiting_hours ?? alert.hours_delayed
        })),
        avg_response_times: {
          time_to_claim_hours: report.average_response_times?.avg_claim_hours ?? report.avg_response_times?.time_to_claim_hours,
          time_to_book_hours: report.average_response_times?.avg_book_hours ?? report.avg_response_times?.time_to_book_hours,
          time_to_resolve_days: report.average_response_times?.avg_resolve_days ?? report.avg_response_times?.time_to_resolve_days
        },
        lawyer_performance: (report.lawyer_performance || []).map(l => ({
          ...l,
          lawyer_name: l.name ?? l.lawyer_name,
          total_tickets: l.tickets ?? l.total_tickets,
          avg_rating: l.rating ?? l.avg_rating
        })),
        sla_thresholds: report.sla_thresholds || { claim_hours: 24, booking_hours: 48, resolve_days: 5 }
      };

      setData(formattedReport);
    } catch (err) {
      setError(err.message || "Failed to load SLA report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  const handleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("asc"); }
  };

  const sortedLawyers = [...(data?.lawyer_performance || [])].sort((a, b) => {
    const av = a[sortBy] ?? 0;
    const bv = b[sortBy] ?? 0;
    return sortDir === "asc" ? av - bv : bv - av;
  });

  const SortIcon = ({ col }) => {
    if (sortBy !== col) return <ChevronUp size={12} style={{ opacity: 0.25 }} />;
    return sortDir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  /* ── loading ── */
  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "50vh", flexDirection: "column", gap: "12px" }}>
      <Loader2 size={28} className="animate-spin" style={{ color: "#6366f1", animation: "spin 1s linear infinite" }} />
      <p style={{ color: isDark ? "#94a3b8" : "#64748b", fontSize: "14px" }}>Loading SLA report…</p>
    </div>
  );

  /* ── error ── */
  if (error) return (
    <div style={{
      padding: "24px", borderRadius: "16px",
      background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)",
      display: "flex", alignItems: "center", gap: "12px"
    }}>
      <AlertTriangle size={18} color="#ef4444" />
      <div style={{ flex: 1 }}>
        <p style={{ color: "#ef4444", fontWeight: 700, fontSize: "14px" }}>Failed to load SLA report</p>
        <p style={{ color: isDark ? "#94a3b8" : "#64748b", fontSize: "12px", marginTop: "2px" }}>{error}</p>
      </div>
      <button
        onClick={fetchReport}
        style={{ display: "flex", alignItems: "center", gap: "6px", padding: "8px 14px", borderRadius: "8px", background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444", fontSize: "12px", fontWeight: 700, cursor: "pointer" }}
      >
        <RefreshCw size={12} /> Retry
      </button>
    </div>
  );

  const alerts = data?.alerts || [];
  const avg = data?.avg_response_times || {};
  const thresholds = data?.sla_thresholds || { claim_hours: 24, booking_hours: 48, resolve_days: 5 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "28px", paddingBottom: "40px", animation: "fadeIn 0.3s ease" }}>

      {/* ── Header ── */}
      <div style={{
        padding: "28px 32px",
        borderRadius: "20px",
        border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`,
        background: isDark ? "rgba(15,23,42,0.8)" : "#fff",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: 800, color: isDark ? "#f1f5f9" : "#0f172a", margin: 0 }}>
              Performance Report
            </h1>
            <p style={{ marginTop: "6px", fontSize: "13px", color: isDark ? "#94a3b8" : "#64748b" }}>
              Response times, SLA compliance, and lawyer performance - last 30 days
            </p>
          </div>
          <button
            onClick={fetchReport}
            style={{ display: "flex", alignItems: "center", gap: "6px", padding: "10px 16px", borderRadius: "10px", background: isDark ? "rgba(99,102,241,0.12)" : "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)", color: "#6366f1", fontSize: "13px", fontWeight: 700, cursor: "pointer" }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* ── SECTION 1: SLA Alerts ── */}
      <div style={{
        padding: "24px 28px",
        borderRadius: "20px",
        border: `1px solid ${alerts.length > 0 ? "rgba(239,68,68,0.25)" : (isDark ? "rgba(16,185,129,0.25)" : "rgba(16,185,129,0.25)")}`,
        background: isDark ? "rgba(15,23,42,0.8)" : "#fff",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: alerts.length > 0 ? "20px" : "0" }}>
          {alerts.length > 0 ? (
            <AlertTriangle size={18} color="#ef4444" />
          ) : (
            <CheckCircle size={18} color="#10b981" />
          )}
          <h2 style={{ fontSize: "15px", fontWeight: 800, color: isDark ? "#f1f5f9" : "#0f172a", margin: 0 }}>
            {alerts.length > 0 ? `SLA Alerts - ${alerts.length} active` : "All SLA metrics within threshold"}
          </h2>
        </div>

        {alerts.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {alerts.map((alert, i) => {
              const info = ALERT_LABEL[alert.type] || ALERT_LABEL.unclaimed;
              return (
                <div
                  key={i}
                  onClick={() => onNavigate?.("queue")}
                  style={{
                    display: "flex", alignItems: "center", gap: "14px",
                    padding: "14px 18px", borderRadius: "12px",
                    background: info.bg, border: `1px solid ${info.color}25`,
                    cursor: "pointer", transition: "opacity 0.15s"
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = "0.8"}
                  onMouseLeave={e => e.currentTarget.style.opacity = "1"}
                >
                  <AlertTriangle size={15} color={info.color} style={{ flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: "13px", fontWeight: 700, color: info.color, margin: 0 }}>
                      {info.text} - Ticket {fmtTicketId(alert.ticket_id)}
                    </p>
                    <p style={{ fontSize: "12px", color: isDark ? "#94a3b8" : "#64748b", margin: "2px 0 0" }}>
                      {alert.user_name && `User: ${alert.user_name} · `}
                      Waiting {fmtWaitingText(alert.waiting_hours)}
                      {alert.lawyer_name && ` · Lawyer: ${alert.lawyer_name}`}
                    </p>
                  </div>
                  <span style={{ fontSize: "10px", fontWeight: 700, color: info.color, letterSpacing: "0.06em", textTransform: "uppercase", flexShrink: 0 }}>
                    View →
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── SECTION 2: KPI Cards ── */}
      <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
        <KpiCard
          label="Avg Time to Claim"
          value={fmtHours(avg.time_to_claim_hours)}
          sublabel={`SLA threshold: ${thresholds.claim_hours}h`}
          statusText={avg.time_to_claim_hours > thresholds.claim_hours ? "Exceeded Threshold" : null}
          statusColor="#ef4444"
          color="#10b981"
          icon={Clock}
          isDark={isDark}
        />
        <KpiCard
          label="Avg Time to Book"
          value={fmtHours(avg.time_to_book_hours)}
          sublabel={`SLA threshold: ${thresholds.booking_hours}h`}
          statusText={avg.time_to_book_hours > thresholds.booking_hours ? "Exceeded Threshold" : null}
          statusColor="#ef4444"
          color="#3b82f6"
          icon={TrendingUp}
          isDark={isDark}
        />
        <KpiCard
          label="Avg Time to Resolve"
          value={fmtDays(avg.time_to_resolve_days)}
          sublabel={`SLA threshold: ${thresholds.resolve_days} days`}
          statusText={avg.time_to_resolve_days > thresholds.resolve_days ? "Exceeded Threshold" : null}
          statusColor="#ef4444"
          color="#6366f1"
          icon={CheckCircle}
          isDark={isDark}
        />
      </div>

      {/* ── SECTION 3: Lawyer Performance Table ── */}
      <div style={{
        borderRadius: "20px",
        border: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`,
        background: isDark ? "rgba(15,23,42,0.8)" : "#fff",
        overflow: "hidden"
      }}>
        {/* Table Header */}
        <div style={{
          padding: "20px 28px 16px",
          borderBottom: `1px solid ${isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)"}`,
          display: "flex", alignItems: "center", gap: "10px"
        }}>
          <h2 style={{ fontSize: "15px", fontWeight: 800, color: isDark ? "#f1f5f9" : "#0f172a", margin: 0 }}>
            Lawyer Performance
          </h2>
        </div>

        {sortedLawyers.length === 0 ? (
          <div style={{ padding: "48px", textAlign: "center", color: isDark ? "#64748b" : "#94a3b8", fontSize: "13px" }}>
            No resolved tickets yet - performance data will appear here once lawyers resolve matters.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)" }}>
                  {[
                    { key: null, label: "Lawyer" },
                    { key: "total_tickets", label: "Tickets" },
                    { key: "avg_resolve_days", label: "Avg Resolve Time" },
                    { key: "avg_rating", label: "Avg Rating" },
                  ].map(col => (
                    <th
                      key={col.label}
                      onClick={() => col.key && handleSort(col.key)}
                      style={{
                        padding: "12px 20px",
                        textAlign: "left",
                        fontSize: "10px", fontWeight: 800,
                        textTransform: "uppercase", letterSpacing: "0.08em",
                        color: isDark ? "#64748b" : "#94a3b8",
                        cursor: col.key ? "pointer" : "default",
                        userSelect: "none",
                        whiteSpace: "nowrap"
                      }}
                    >
                      <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                        {col.label}
                        {col.key && <SortIcon col={col.key} />}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedLawyers.map((l, i) => (
                  <tr
                    key={l.lawyer_id || i}
                    style={{
                      borderTop: `1px solid ${isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)"}`,
                      transition: "background 0.15s"
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = isDark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.02)"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                  >
                    {/* Lawyer name */}
                    <td style={{ padding: "16px 20px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <div style={{
                          width: 34, height: 34, borderRadius: "10px",
                          background: "rgba(99,102,241,0.12)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "13px", fontWeight: 800, color: "#6366f1", flexShrink: 0
                        }}>
                          {(l.lawyer_name || "L").charAt(0).toUpperCase()}
                        </div>
                        <span style={{ fontSize: "14px", fontWeight: 600, color: isDark ? "#e2e8f0" : "#1e293b" }}>
                          {l.lawyer_name || "Unknown"}
                        </span>
                      </div>
                    </td>
                    {/* Tickets */}
                    <td style={{ padding: "16px 20px" }}>
                      <span style={{
                        display: "inline-flex", alignItems: "center", gap: "4px",
                        padding: "4px 10px", borderRadius: "99px",
                        background: "rgba(99,102,241,0.1)",
                        fontSize: "12px", fontWeight: 700, color: "#6366f1"
                      }}>
                        <Users size={11} /> {l.total_tickets}
                      </span>
                    </td>
                    {/* Avg resolve */}
                    <td style={{ padding: "16px 20px" }}>
                      <span style={{
                        fontSize: "13px", fontWeight: 700,
                        color: isDark ? "#10b981" : "#059669"
                      }}>
                        {fmtDays(l.avg_resolve_days)}
                      </span>
                    </td>
                    {/* Rating */}
                    <td style={{ padding: "16px 20px" }}>
                      <StarRating value={l.avg_rating} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
