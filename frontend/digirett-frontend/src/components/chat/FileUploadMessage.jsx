import React from "react";

const statusConfig = {
  uploaded:  { label: "Uploaded",  color: "#6b7280", dot: "#6b7280" },
  parsing:   { label: "Processing", color: "#f59e0b", dot: "#f59e0b" },
  indexed:   { label: "Ready",     color: "#10b981", dot: "#10b981" },
  failed:    { label: "Failed",    color: "#ef4444", dot: "#ef4444" },
};

function FileIcon({ fileType }) {
  const isPdf = fileType?.includes("pdf");
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 8,
      background: isPdf ? "#fee2e2" : "#dbeafe",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: 18, flexShrink: 0
    }}>
      {isPdf ? "📄" : "📝"}
    </div>
  );
}

function AttachmentCard({ attachment }) {
  const status = statusConfig[attachment.status] || statusConfig.uploaded;
  const isClickable = attachment.status === "indexed" && attachment.preview_url;

  const handleClick = () => {
    if (isClickable) window.open(attachment.preview_url, "_blank");
  };

  return (
    <div
      onClick={handleClick}
      style={{
        display: "flex", alignItems: "center", gap: 12,
        padding: "10px 14px", borderRadius: 12,
        background: "rgba(255,255,255,0.85)",
        border: "1px solid #e5e7eb",
        cursor: isClickable ? "pointer" : "default",
        maxWidth: 320, width: "100%",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)"
      }}
    >
      <FileIcon fileType={attachment.file_type} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 600, fontSize: 14,
          color: "#111827", whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis"
        }}>
          {attachment.file_name}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
          <span style={{
            width: 7, height: 7, borderRadius: "50%",
            background: status.dot, display: "inline-block"
          }} />
          <span style={{ fontSize: 12, color: status.color, fontWeight: 500 }}>
            {status.label}
          </span>
          {attachment.file_type && (
            <span style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>
              · {attachment.file_type.split("/").pop()}
            </span>
          )}
        </div>
      </div>
      {isClickable && (
        <span style={{ fontSize: 16, color: "#9ca3af" }}>↗</span>
      )}
    </div>
  );
}

export default function FileUploadMessage({ message }) {
  const attachments = message.attachments || [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-end" }}>
      {attachments.map((att) => (
        <AttachmentCard key={att.document_id} attachment={att} />
      ))}
    </div>
  );
}