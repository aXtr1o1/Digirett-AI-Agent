// frontend/digirett-frontend/src/components/chat/LibraryDashboard.jsx
import React, { useState, useEffect, useRef } from "react";
import {
  Search,
  Trash2,
  Calendar,
  Edit3,
  X,
  Plus,
  Download,
  FileText,
  Loader2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  File
} from "lucide-react";
import libraryService from "../../services/libraryService";
import { API_BASE_URL } from "../../utils/constants";

const LibraryDashboard = ({ theme = "dark" }) => {
  const isDark = theme === "dark";
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("all"); // "all", "pdf", "docx"
  
  // Note editing states
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editNoteText, setEditNoteText] = useState("");
  const [expandedNoteId, setExpandedNoteId] = useState(null);
  const [deletingDocId, setDeletingDocId] = useState(null);
  
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
    window.addEventListener("digirett_library_updated", loadSaved);
    return () => window.removeEventListener("digirett_library_updated", loadSaved);
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadFile(file);
  };

  const uploadFile = async (file) => {
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
    try {
      await libraryService.unsaveMessage(docId);
      loadSaved();
    } catch (err) {
      console.error("Failed to delete document:", err);
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
    setExpandedNoteId(doc.id);
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

  const toggleExpandNote = (e, docId) => {
    e.stopPropagation();
    setExpandedNoteId(expandedNoteId === docId ? null : docId);
  };

  const filteredDocuments = documents.filter((doc) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch = 
      (doc.file_name || "").toLowerCase().includes(q) ||
      (doc.note || "").toLowerCase().includes(q);
    
    if (activeTab === "pdf") {
      return matchesSearch && (doc.file_type || "").toLowerCase() === "pdf";
    }
    if (activeTab === "docx") {
      return matchesSearch && ["docx", "doc"].includes((doc.file_type || "").toLowerCase());
    }
    return matchesSearch;
  });

  const formatDate = (isoString) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffTime = Math.abs(now - date);
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      
      if (diffDays === 1) return "Today";
      if (diffDays === 2) return "Yesterday";
      
      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
    } catch {
      return "";
    }
  };

  const formatSize = (charCount) => {
    if (!charCount) return "0 KB";
    // Rough estimation: 1 character ~ 1 byte
    const kb = charCount / 1024;
    if (kb < 1) return "1 KB";
    return `${Math.round(kb)} KB`;
  };

  // Theme colors matching GPT style
  const bgColor = isDark ? "#171717" : "#ffffff";
  const textPrimaryColor = isDark ? "#ececec" : "#171717";
  const textSecondaryColor = isDark ? "#b4b4b4" : "#676767";
  const borderColor = isDark ? "#2f2f2f" : "#e5e5e5";
  const hoverColor = isDark ? "#212121" : "#f9f9f9";
  const pillActiveBg = isDark ? "#212121" : "#f4f4f4";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: bgColor,
        color: textPrimaryColor,
        fontFamily: 'Söhne, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        overflow: "hidden",
      }}
    >
      {/* ── Top Header Bar ── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "40px 40px 24px",
          maxWidth: "1000px",
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "32px", fontWeight: "600", tracking: "-0.02em" }}>
          Library
        </h1>

        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {/* Search Input */}
          <div style={{ position: "relative" }}>
            <Search
              size={16}
              style={{
                position: "absolute",
                left: "14px",
                top: "50%",
                transform: "translateY(-50%)",
                color: textSecondaryColor,
              }}
            />
            <input
              type="text"
              placeholder="Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                width: "240px",
                padding: "8px 14px 8px 38px",
                borderRadius: "9999px",
                fontSize: "14px",
                backgroundColor: isDark ? "#212121" : "#f4f4f4",
                color: textPrimaryColor,
                border: "none",
                outline: "none",
                transition: "width 0.2s",
              }}
            />
          </div>

          {/* New Upload Pill Button */}
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
              padding: "8px 16px",
              borderRadius: "9999px",
              fontSize: "14px",
              fontWeight: "500",
              backgroundColor: isDark ? "#171717" : "#ffffff",
              color: "#3b82f6",
              border: "1px solid #3b82f6",
              cursor: isUploading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = isDark ? "rgba(59, 130, 246, 0.1)" : "#f0f7ff";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = isDark ? "#171717" : "#ffffff";
            }}
          >
            {isUploading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Plus size={14} />
            )}
            <span>New</span>
          </button>
        </div>
      </div>

      {/* ── Filter Pills Bar ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "0 40px 24px",
          maxWidth: "1000px",
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        <button
          onClick={() => setActiveTab("all")}
          style={{
            padding: "6px 12px",
            borderRadius: "9999px",
            fontSize: "13px",
            fontWeight: "500",
            border: "none",
            backgroundColor: activeTab === "all" ? pillActiveBg : "transparent",
            color: activeTab === "all" ? textPrimaryColor : textSecondaryColor,
            cursor: "pointer",
          }}
        >
          All
        </button>
        <button
          onClick={() => setActiveTab("pdf")}
          style={{
            padding: "6px 12px",
            borderRadius: "9999px",
            fontSize: "13px",
            fontWeight: "500",
            border: "none",
            backgroundColor: activeTab === "pdf" ? pillActiveBg : "transparent",
            color: activeTab === "pdf" ? textPrimaryColor : textSecondaryColor,
            cursor: "pointer",
          }}
        >
          PDFs
        </button>
        <button
          onClick={() => setActiveTab("docx")}
          style={{
            padding: "6px 12px",
            borderRadius: "9999px",
            fontSize: "13px",
            fontWeight: "500",
            border: "none",
            backgroundColor: activeTab === "docx" ? pillActiveBg : "transparent",
            color: activeTab === "docx" ? textPrimaryColor : textSecondaryColor,
            cursor: "pointer",
          }}
        >
          Word Docs
        </button>
      </div>

      {/* Error Banner */}
      {uploadError && (
        <div
          style={{
            maxWidth: "1000px",
            width: "100%",
            margin: "0 auto 16px",
            padding: "10px 16px",
            borderRadius: "8px",
            backgroundColor: "rgba(239, 68, 68, 0.1)",
            color: "#f87171",
            fontSize: "13px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            boxSizing: "border-box",
          }}
        >
          <AlertCircle size={16} />
          <span>{uploadError}</span>
          <button
            onClick={() => setUploadError("")}
            style={{ marginLeft: "auto", background: "none", border: "none", color: "inherit", cursor: "pointer" }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── Documents Table/List ── */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "0 40px 40px",
          maxWidth: "1000px",
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
        className="sidebar-scrollbar-hidden"
      >
        {/* Table Headers */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 120px 100px 140px",
            padding: "8px 12px",
            fontSize: "12px",
            fontWeight: "500",
            color: textSecondaryColor,
            borderBottom: `1px solid ${borderColor}`,
          }}
        >
          <div>Name</div>
          <div>Modified ↓</div>
          <div style={{ textAlign: "right", paddingRight: "16px" }}>Size</div>
          <div style={{ textAlign: "right", paddingRight: "12px" }}>Actions</div>
        </div>

        {/* Empty State */}
        {filteredDocuments.length === 0 && (
          <div
            style={{
              padding: "80px 0",
              textAlign: "center",
              color: textSecondaryColor,
              fontSize: "14px",
            }}
          >
            {documents.length === 0 
              ? "No files in your library yet. Upload a PDF or DOCX file to get started." 
              : "No files match your search."}
          </div>
        )}

        {/* Table Rows */}
        {filteredDocuments.map((doc) => {
          const isPdf = (doc.file_type || "").toLowerCase() === "pdf";
          const isExpanded = expandedNoteId === doc.id;
          const isEditing = editingNoteId === doc.id;

          return (
            <div key={doc.id} style={{ borderBottom: `1px solid ${borderColor}` }}>
              <div
                className="library-row"
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 120px 100px 140px",
                  alignItems: "center",
                  padding: "14px 12px",
                  fontSize: "14px",
                  cursor: "default",
                  borderRadius: "8px",
                  transition: "background-color 0.15s",
                  position: "relative",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = hoverColor;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = "transparent";
                }}
              >
                {/* Name column */}
                <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
                  <div
                    onClick={(e) => handleDownload(e, doc.id)}
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "6px",
                      backgroundColor: isPdf ? "rgba(239, 68, 68, 0.08)" : "rgba(59, 130, 246, 0.08)",
                      color: isPdf ? "#ef4444" : "#3b82f6",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                      cursor: "pointer",
                    }}
                    title="Download / View file"
                  >
                    <FileText size={16} />
                  </div>
                  <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: "4px", flex: 1 }}>
                    <span
                      onClick={(e) => handleDownload(e, doc.id)}
                      style={{
                        fontWeight: "500",
                        color: textPrimaryColor,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        cursor: "pointer",
                        alignSelf: "flex-start",
                      }}
                      title="Download / View file"
                      onMouseEnter={(e) => e.currentTarget.style.textDecoration = "underline"}
                      onMouseLeave={(e) => e.currentTarget.style.textDecoration = "none"}
                    >
                      {doc.file_name}
                    </span>
                    
                    {/* Render Edit form inline under filename */}
                    {isEditing ? (
                      <div 
                        onClick={(e) => e.stopPropagation()} 
                        style={{ 
                          display: "flex", 
                          flexDirection: "column", 
                          gap: "8px", 
                          marginTop: "4px",
                          width: "100%",
                          maxWidth: "600px"
                        }}
                      >
                        <textarea
                          value={editNoteText}
                          onChange={(e) => setEditNoteText(e.target.value)}
                          placeholder="Type your personal notes or annotations here..."
                          rows={2}
                          style={{
                            width: "100%",
                            fontSize: "12px",
                            lineHeight: "1.4",
                            padding: "6px 10px",
                            borderRadius: "6px",
                            backgroundColor: isDark ? "#212121" : "#ffffff",
                            color: textPrimaryColor,
                            border: `1px solid ${borderColor}`,
                            outline: "none",
                            resize: "none",
                            boxSizing: "border-box",
                          }}
                        />
                        <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
                          <button
                            onClick={cancelEditing}
                            style={{
                              padding: "4px 10px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              border: `1px solid ${borderColor}`,
                              backgroundColor: "transparent",
                              color: textSecondaryColor,
                              cursor: "pointer",
                            }}
                          >
                            Cancel
                          </button>
                          <button
                            onClick={(e) => saveNote(e, doc.id)}
                            style={{
                              padding: "4px 10px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              fontWeight: "600",
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
                    ) : (
                      /* Render Full Note professionally inline under filename */
                      doc.note && (
                        <div
                          style={{
                            marginTop: "4px",
                            fontSize: "12px",
                            color: textPrimaryColor,
                            backgroundColor: isDark ? "rgba(255, 255, 255, 0.02)" : "#f9fafb",
                            borderLeft: `3px solid #3b82f6`,
                            padding: "6px 12px",
                            borderRadius: "4px",
                            wordBreak: "break-word",
                            maxWidth: "600px",
                            lineHeight: "1.5",
                          }}
                        >
                          <span style={{ fontWeight: "700", color: "#3b82f6", marginRight: "6px", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                            Note:
                          </span>
                          {doc.note.length <= 140 || expandedNoteId === doc.id ? (
                            <>
                              {doc.note}
                              {doc.note.length > 140 && (
                                <span
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedNoteId(null);
                                  }}
                                  style={{ color: "#3b82f6", marginLeft: "6px", cursor: "pointer", fontWeight: "600" }}
                                >
                                  Show less
                                </span>
                              )}
                            </>
                          ) : (
                            <>
                              {doc.note.substring(0, 140)}...
                              <span
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedNoteId(doc.id);
                                }}
                                style={{ color: "#3b82f6", marginLeft: "6px", cursor: "pointer", fontWeight: "600" }}
                              >
                                Show more
                              </span>
                            </>
                          )}
                        </div>
                      )
                    )}
                  </div>
                </div>

                {/* Modified date column */}
                <div style={{ color: textSecondaryColor, fontSize: "13px" }}>
                  {formatDate(doc.created_at)}
                </div>

                {/* Size column */}
                <div style={{ color: textSecondaryColor, fontSize: "13px", textAlign: "right", paddingRight: "16px" }}>
                  {formatSize(doc.char_count)}
                </div>

                {/* Actions column */}
                <div
                  className="row-actions"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    gap: "8px",
                  }}
                  onClick={(e) => e.stopPropagation()} // Prevent triggering file download
                >
                  {/* Download / View */}
                  <button
                    onClick={(e) => handleDownload(e, doc.id)}
                    style={{
                      background: "none",
                      border: "none",
                      color: textSecondaryColor,
                      cursor: "pointer",
                      padding: "4px",
                      borderRadius: "4px",
                      display: "flex",
                    }}
                    title="Download Document"
                    onMouseEnter={(e) => e.currentTarget.style.color = "#3b82f6"}
                    onMouseLeave={(e) => e.currentTarget.style.color = textSecondaryColor}
                  >
                    <Download size={15} />
                  </button>

                  {/* Edit Note */}
                  <button
                    onClick={(e) => startEditingNote(e, doc)}
                    style={{
                      background: "none",
                      border: "none",
                      color: textSecondaryColor,
                      cursor: "pointer",
                      padding: "4px",
                      borderRadius: "4px",
                      display: "flex",
                    }}
                    title="Edit Note"
                  >
                    <Edit3 size={15} />
                  </button>

                  {/* Delete */}
                  <button
                    onClick={(e) => handleRemove(e, doc.id)}
                    style={{
                      background: "none",
                      border: "none",
                      color: textSecondaryColor,
                      cursor: "pointer",
                      padding: "4px",
                      borderRadius: "4px",
                      display: "flex",
                    }}
                    title="Delete"
                    onMouseEnter={(e) => e.currentTarget.style.color = "#ef4444"}
                    onMouseLeave={(e) => e.currentTarget.style.color = textSecondaryColor}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default LibraryDashboard;
