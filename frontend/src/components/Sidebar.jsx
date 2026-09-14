import React from 'react';
import { Plus, MessageSquare, FileText, Trash2, Loader, AlertTriangle } from 'lucide-react';

function formatTime(dateStr) {
  if (!dateStr) return '';
  try {
    const utcStr = dateStr.endsWith('Z') ? dateStr : dateStr + 'Z';
    const d = new Date(utcStr);
    if (isNaN(d)) return '';
    const now = new Date();
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString();
  } catch {
    return '';
  }
}

export default function Sidebar({
  sessions,
  documents,
  currentSessionId,
  currentDocumentId,
  loadSession,
  handleNewChat,
  handleDeleteSession,
  handleSelectDocument,
  newChatLoading,
}) {
  return (
    <div className="left-col">
      <button
        className="btn-new-chat"
        onClick={handleNewChat}
        disabled={newChatLoading}
        title="Start a new empty conversation"
      >
        {newChatLoading ? <Loader size={14} className="spin" /> : <Plus size={14} />}
        New Chat
      </button>

      <div className="sidebar-inner">
        {/* ── Recent Conversations ── */}
        <div className="sidebar-section-label">Recent Conversations</div>

        {sessions.length === 0 && (
          <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', padding: '6px 8px 10px 8px' }}>
            No conversations yet
          </div>
        )}

        {sessions.map((sess) => (
          <div
            key={sess.id}
            className={`sidebar-item ${currentSessionId === sess.id ? 'active' : ''}`}
            onClick={() => loadSession(sess.id)}
            title={sess.title}
          >
            <MessageSquare size={13} style={{ flexShrink: 0, opacity: 0.7 }} />
            <span className="sidebar-item-text">{sess.title || 'Untitled'}</span>

            {/* Document-deleted indicator */}
            {sess.document_deleted && (
              <span
                title="This conversation's document was deleted — read-only"
                style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}
              >
                <AlertTriangle size={11} color="var(--warning)" />
              </span>
            )}

            <span className="sidebar-item-time">{formatTime(sess.updated_at)}</span>
            <button
              className="sidebar-item-delete"
              onClick={(e) => {
                e.stopPropagation();
                handleDeleteSession(sess.id);
              }}
              title="Delete this conversation"
            >
              <Trash2 size={11} />
            </button>
          </div>
        ))}

        {/* ── Document Library ── */}
        {documents.length > 0 && (
          <>
            <div className="sidebar-section-label" style={{ marginTop: '16px' }}>
              Document Library
            </div>
            {documents.map((doc) => (
              <div
                key={doc.id}
                className={`sidebar-item ${currentDocumentId === doc.id ? 'active' : ''}`}
                onClick={() => handleSelectDocument(doc.id)}
                title={doc.filename}
              >
                <FileText size={13} style={{ flexShrink: 0, opacity: 0.7 }} />
                <span className="sidebar-item-text">{doc.filename}</span>
                <span className="sidebar-item-time" style={{ fontSize: '0.62rem' }}>
                  {doc.num_pages}p
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* ── User Footer ── */}
      <div className="sidebar-footer">
        <div className="sidebar-user-avatar">H</div>
        <div>
          <div className="sidebar-user-name">HET GANDHI</div>
          <div className="sidebar-user-sub">NVIDIA DGX Spark</div>
        </div>
      </div>
    </div>
  );
}
