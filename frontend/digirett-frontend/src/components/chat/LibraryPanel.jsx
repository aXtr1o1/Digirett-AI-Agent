// frontend/digirett-frontend/src/components/chat/LibraryPanel.jsx
import React, { useState, useEffect, useRef } from "react";
import { Search, Bookmark, Trash2, Calendar, Edit2, Download, Upload, FileText, Loader2, AlertCircle } from "lucide-react";
import libraryService from "../../services/libraryService";
import { API_BASE_URL } from "../../utils/constants";

const LibraryPanel = ({ isDark }) => {
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editNoteText, setEditNoteText] = useState("");
  
  // Upload states
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const fileInputRef = useRef(null);

  const loadSaved = async () => {
    const docs = await libraryService.getSavedMessages();
    setDocuments(docs);
  };

  useEffect(() => {
    loadSaved();

    // Listen for updates from other components
    window.addEventListener("digirett_library_updated", loadSaved);
    return () => {
      window.removeEventListener("digirett_library_updated", loadSaved);
    };
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError("");
    try {
      await libraryService.uploadDocument(file, "");
      await loadSaved();
    } catch (err) {
      console.error("Failed to upload document:", err);
      setUploadError(err.message || "Failed to upload document");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleRemove = async (e, docId) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to remove this document from the library?")) return;
    try {
      await libraryService.unsaveMessage(docId);
      loadSaved();
    } catch (err) {
      console.error("Failed to remove document:", err);
    }
  };

  const handleDownload = async (e, docId) => {
    e.stopPropagation();
    try {
      const token = await window.Clerk?.session?.getToken();
      const url = `${API_BASE_URL}/api/v1/library/documents/${docId}/view${token ? `?token=${token}` : ""}`;
      window.open(url, "_blank");
    } catch (err) {
      console.error("Failed to view document:", err);
    }
  };

  const startEditingNote = (e, doc) => {
    e.stopPropagation();
    setEditingNoteId(doc.id);
    setEditNoteText(doc.note || "");
  };

  const saveNote = async (e, docId) => {
    e.stopPropagation();
    try {
      await libraryService.updateMessageNote(docId, editNoteText);
      setEditingNoteId(null);
      setEditNoteText("");
      loadSaved();
    } catch (err) {
      console.error("Failed to save note:", err);
    }
  };

  const cancelEditing = (e) => {
    e.stopPropagation();
    setEditingNoteId(null);
    setEditNoteText("");
  };

  const filteredDocuments = documents.filter((doc) => {
    const q = searchQuery.toLowerCase();
    return (
      (doc.file_name || "").toLowerCase().includes(q) ||
      (doc.note || "").toLowerCase().includes(q)
    );
  });

  const formatDate = (isoString) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return "";
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        width: "100%",
        padding: "0px 8px 8px",
      }}
    >
      {/* Title Header */}
      <div
        style={{
          padding: "0 8px 12px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          borderBottom: isDark ? "1px solid rgba(255, 255, 255, 0.05)" : "1px solid rgba(0, 0, 0, 0.05)",
          marginBottom: "12px",
        }}
      >
        <Bookmark size={18} className="text-blue-500" />
        <span style={{ fontSize: "14px", fontWeight: "600", color: isDark ? "#ffffff" : "#111827" }}>
          Legal Library ({documents.length})
        </span>
      </div>

      {/* Upload Dropzone/Button */}
      <div style={{ padding: "0 4px 12px" }}>
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          accept=".pdf,.docx,.doc"
          style={{ display: "none" }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          style={{
            width: "100%",
            padding: "12px",
            borderRadius: "12px",
            border: isDark ? "1.5px dashed rgba(255, 255, 255, 0.15)" : "1.5px dashed rgba(0, 0, 0, 0.15)",
            backgroundColor: isDark ? "rgba(255, 255, 255, 0.02)" : "rgba(0, 0, 0, 0.01)",
            color: isDark ? "#d1d5db" : "#374151",
            cursor: isUploading ? "not-allowed" : "pointer",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            transition: "all 0.2s",
            outline: "none",
          }}
          onMouseEnter={(e) => {
            if (!isUploading) {
              e.currentTarget.style.borderColor = "#3b82f6";
              e.currentTarget.style.backgroundColor = isDark ? "rgba(59, 130, 246, 0.04)" : "rgba(59, 130, 246, 0.02)";
            }
          }}
          onMouseLeave={(e) => {
            if (!isUploading) {
              e.currentTarget.style.borderColor = isDark ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.15)";
              e.currentTarget.style.backgroundColor = isDark ? "rgba(255, 255, 255, 0.02)" : "rgba(0, 0, 0, 0.01)";
            }
          }}
        >
          {isUploading ? (
            <>
              <Loader2 size={16} className="text-blue-500 animate-spin" />
              <span style={{ fontSize: "11px", fontWeight: "600" }}>Uploading...</span>
            </>
          ) : (
            <>
              <Upload size={16} className="text-blue-500" />
              <span style={{ fontSize: "11px", fontWeight: "600" }}>Upload PDF or DOCX</span>
            </>
          )}
        </button>

        {uploadError && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "4px",
            color: "#f87171",
            fontSize: "10px",
            marginTop: "6px",
            padding: "0 4px"
          }}>
            <AlertCircle size={10} />
            <span>{uploadError}</span>
          </div>
        )}
      </div>

      {/* Search Input */}
      {documents.length > 0 && (
        <div style={{ padding: "0 4px 12px", position: "relative" }}>
          <Search
            size={14}
            style={{
              position: "absolute",
              left: "14px",
              top: "50%",
              transform: "translateY(-50%)",
              color: isDark ? "#6b7280" : "#9ca3af",
            }}
          />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 12px 8px 30px",
              borderRadius: "8px",
              fontSize: "12px",
              backgroundColor: isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.03)",
              color: isDark ? "#ffffff" : "#111827",
              border: isDark ? "1px solid rgba(255, 255, 255, 0.1)" : "1px solid rgba(0, 0, 0, 0.1)",
              outline: "none",
              transition: "border-color 0.2s",
            }}
            onFocus={(e) => (e.target.style.borderColor = "#3b82f6")}
            onBlur={(e) => (e.target.style.borderColor = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)")}
          />
        </div>
      )}

      {/* Saved items list */}
      <div
        className="sidebar-scrollbar-hidden"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          maxHeight: "calc(100vh - 280px)",
        }}
      >
        {filteredDocuments.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              fontSize: "12px",
              color: isDark ? "#6b7280" : "#9ca3af",
            }}
          >
            {documents.length === 0 ? "Upload PDFs or Word documents to keep them in your Legal Library." : "No matching documents found."}
          </div>
        ) : (
          filteredDocuments.map((doc) => (
            <div
              key={doc.id}
              style={{
                padding: "10px",
                borderRadius: "10px",
                backgroundColor: isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.02)",
                border: isDark ? "1px solid rgba(255, 255, 255, 0.06)" : "1px solid rgba(0, 0, 0, 0.06)",
                cursor: "default",
                transition: "all 0.2s",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
                position: "relative",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.04)";
                e.currentTarget.style.transform = "translateY(-1px)";
                const actions = e.currentTarget.querySelector(".bookmark-actions");
                if (actions) actions.style.opacity = "1";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = isDark ? "rgba(255, 255, 255, 0.03)" : "rgba(0, 0, 0, 0.02)";
                e.currentTarget.style.transform = "translateY(0)";
                const actions = e.currentTarget.querySelector(".bookmark-actions");
                if (actions) actions.style.opacity = "0";
              }}
            >
              {/* Header metadata */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px", minWidth: 0, flex: 1 }}>
                  <FileText 
                    size={14} 
                    className="text-blue-500 flex-shrink-0" 
                    onClick={(e) => handleDownload(e, doc.id)}
                    style={{ cursor: "pointer" }}
                    title="Download / View file"
                  />
                  <span
                    onClick={(e) => handleDownload(e, doc.id)}
                    style={{
                      fontSize: "12px",
                      fontWeight: "600",
                      color: isDark ? "#f3f4f6" : "#1f2937",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      cursor: "pointer",
                    }}
                    title={doc.file_name}
                    onMouseEnter={(e) => e.currentTarget.style.textDecoration = "underline"}
                    onMouseLeave={(e) => e.currentTarget.style.textDecoration = "none"}
                  >
                    {doc.file_name}
                  </span>
                  <span
                    style={{
                      fontSize: "8px",
                      fontWeight: "800",
                      padding: "1px 4px",
                      borderRadius: "4px",
                      backgroundColor: isDark ? "rgba(59, 130, 246, 0.15)" : "rgba(59, 130, 246, 0.1)",
                      color: "#60a5fa",
                      border: `1px solid ${isDark ? "rgba(59, 130, 246, 0.25)" : "rgba(59, 130, 246, 0.2)"}`,
                      flexShrink: 0,
                      textTransform: "uppercase"
                    }}
                  >
                    {doc.file_type || "File"}
                  </span>
                </div>

                <div
                  className="bookmark-actions"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    opacity: 0,
                    transition: "opacity 0.15s",
                  }}
                >
                  <Trash2
                    size={12}
                    onClick={(e) => handleRemove(e, doc.id)}
                    style={{
                      color: isDark ? "#9ca3af" : "#6b7280",
                      cursor: "pointer",
                      transition: "color 0.15s",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#ef4444")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = isDark ? "#9ca3af" : "#6b7280")}
                    title="Delete document"
                  />
                  <Download
                    size={12}
                    onClick={(e) => handleDownload(e, doc.id)}
                    style={{
                      color: isDark ? "#9ca3af" : "#6b7280",
                      cursor: "pointer",
                      transition: "color 0.15s",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#3b82f6")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = isDark ? "#9ca3af" : "#6b7280")}
                    title="Download document"
                  />
                </div>
              </div>

              {/* Personal Annotations note block */}
              {editingNoteId === doc.id ? (
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    marginTop: "4px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "6px",
                  }}
                >
                  <textarea
                    value={editNoteText}
                    onChange={(e) => setEditNoteText(e.target.value)}
                    placeholder="Add personal note/annotation..."
                    rows={2}
                    style={{
                      width: "100%",
                      fontSize: "11px",
                      padding: "6px",
                      borderRadius: "6px",
                      backgroundColor: isDark ? "#1e1e1e" : "#ffffff",
                      color: isDark ? "#ffffff" : "#111827",
                      border: isDark ? "1px solid rgba(255, 255, 255, 0.15)" : "1px solid rgba(0, 0, 0, 0.15)",
                      outline: "none",
                      resize: "none",
                    }}
                  />
                  <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
                    <button
                      onClick={(e) => cancelEditing(e)}
                      style={{
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        border: isDark ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(0,0,0,0.1)",
                        backgroundColor: "transparent",
                        color: isDark ? "#9ca3af" : "#4b5563",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={(e) => saveNote(e, doc.id)}
                      style={{
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "10px",
                        border: "none",
                        backgroundColor: "#3b82f6",
                        color: "#ffffff",
                        cursor: "pointer",
                      }}
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : doc.note ? (
                <div
                  style={{
                    marginTop: "4px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    backgroundColor: isDark ? "rgba(245, 158, 11, 0.08)" : "rgba(245, 158, 11, 0.05)",
                    borderLeft: "2.5px solid #d97706",
                    fontSize: "11px",
                    color: isDark ? "#f59e0b" : "#b45309",
                    lineHeight: "1.4",
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                  }}
                >
                  <div style={{ wordBreak: "break-word" }}>
                    <strong style={{ fontWeight: "600" }}>Note:</strong> {doc.note}
                  </div>
                  <button
                    onClick={(e) => startEditingNote(e, doc)}
                    style={{
                      border: "none",
                      background: "none",
                      fontSize: "10px",
                      color: isDark ? "#f59e0b" : "#b45309",
                      cursor: "pointer",
                      padding: 0,
                      alignSelf: "flex-end",
                      textDecoration: "underline",
                    }}
                  >
                    Edit note
                  </button>
                </div>
              ) : (
                <button
                  onClick={(e) => startEditingNote(e, doc)}
                  style={{
                    border: "none",
                    background: "none",
                    fontSize: "10px",
                    color: "#3b82f6",
                    cursor: "pointer",
                    padding: 0,
                    textAlign: "left",
                    alignSelf: "flex-start",
                    marginTop: "2px",
                  }}
                >
                  + Add annotation note
                </button>
              )}

              {/* Mapped sections & date */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontSize: "10px",
                  color: isDark ? "#6b7280" : "#9ca3af",
                  marginTop: "4px",
                  borderTop: isDark ? "1px solid rgba(255,255,255,0.05)" : "1px solid rgba(0,0,0,0.05)",
                  paddingTop: "4px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "3px" }}>
                  <Calendar size={10} />
                  <span>{formatDate(doc.created_at)}</span>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LibraryPanel;
