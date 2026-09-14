import React, { useState } from 'react';
import { BookOpen, Trash2, FileText, CheckCircle2, ChevronDown, ChevronUp, AlertCircle, Upload, AlertTriangle } from 'lucide-react';

export default function RightSidebar({
  activeDocument,
  documentDeleted,
  uploading,
  handleDeleteDocument,
  handleUpload,
  fileInputRef,
  iterations,
  reflectionLog,
}) {
  const [logOpen, setLogOpen] = useState(true);

  return (
    <div className="right-col">

      {/* ── Active Document ── */}
      <div className="right-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <div className="section-toggle-title">
            <BookOpen size={14} color="var(--accent-blue)" /> Active Document
          </div>
          {activeDocument && (
            <button className="btn-danger-sm" onClick={() => handleDeleteDocument(activeDocument.id)}>
              <Trash2 size={12} /> Delete
            </button>
          )}
        </div>

        {/* Document-deleted state */}
        {documentDeleted && !activeDocument && (
          <div style={{
            display: 'flex', alignItems: 'flex-start', gap: '8px',
            background: '#fef3c7', border: '1px solid #fcd34d',
            borderRadius: '8px', padding: '10px 12px', marginBottom: '10px',
          }}>
            <AlertTriangle size={14} color="var(--warning)" style={{ flexShrink: 0, marginTop: '1px' }} />
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.76rem', color: '#92400e' }}>Document Deleted</div>
              <div style={{ fontSize: '0.70rem', color: '#b45309', marginTop: '2px' }}>
                This chat's document was deleted. You can still review the conversation history,
                but new questions cannot be answered. Upload a new PDF to start a fresh chat.
              </div>
            </div>
          </div>
        )}

        {activeDocument ? (
          <>
            {/* Document info */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px 12px', marginBottom: '10px' }}>
              <div style={{ width: '36px', height: '36px', background: '#ef4444', borderRadius: '7px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white', flexShrink: 0 }}>
                <FileText size={16} />
              </div>
              <div style={{ overflow: 'hidden', flex: 1 }}>
                <div style={{ fontWeight: 700, fontSize: '0.82rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={activeDocument.filename}>
                  {activeDocument.filename}
                </div>
                <div style={{ fontSize: '0.70rem', color: 'var(--text-secondary)', marginTop: '1px' }}>
                  {activeDocument.num_pages} pages · {activeDocument.num_chunks} chunks
                </div>
              </div>
            </div>

            {/* Status badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'var(--success-light)', border: '1px solid #bbf7d0', borderRadius: '7px', padding: '7px 10px', marginBottom: '12px' }}>
              <CheckCircle2 size={14} color="var(--success)" />
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.76rem', color: '#065f46' }}>Indexed &amp; Ready</div>
                <div style={{ fontSize: '0.68rem', color: '#047857' }}>{activeDocument.num_chunks} chunks in vector store</div>
              </div>
            </div>

            <button className="btn-primary" onClick={() => fileInputRef.current?.click()}>
              <Upload size={14} /> Upload Another PDF
            </button>
            <input type="file" accept=".pdf" className="upload-hidden-input" ref={fileInputRef} onChange={handleUpload} />
          </>
        ) : !documentDeleted ? (
          <>
            <div className="upload-drop" onClick={() => fileInputRef.current?.click()}>
              <div style={{ marginBottom: '6px', fontSize: '1.5rem' }}>📄</div>
              {uploading ? (
                <span className="pulse-text" style={{ color: 'var(--accent-blue)' }}>Processing PDF...</span>
              ) : (
                <>
                  <div style={{ fontWeight: 600, marginBottom: '2px', fontSize: '0.82rem' }}>Click to upload PDF</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>or drag &amp; drop</div>
                </>
              )}
            </div>
            <input type="file" accept=".pdf" className="upload-hidden-input" ref={fileInputRef} onChange={handleUpload} />
          </>
        ) : (
          /* Document deleted — show upload prompt to start fresh */
          <>
            <div className="upload-drop" onClick={() => fileInputRef.current?.click()} style={{ marginTop: '8px' }}>
              <div style={{ marginBottom: '6px', fontSize: '1.5rem' }}>📄</div>
              {uploading ? (
                <span className="pulse-text" style={{ color: 'var(--accent-blue)' }}>Processing PDF...</span>
              ) : (
                <>
                  <div style={{ fontWeight: 600, marginBottom: '2px', fontSize: '0.82rem' }}>Upload a new PDF</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>to start a new conversation</div>
                </>
              )}
            </div>
            <input type="file" accept=".pdf" className="upload-hidden-input" ref={fileInputRef} onChange={handleUpload} />
          </>
        )}
      </div>

      {/* ── Self-Reflection Log ── */}
      {reflectionLog.length > 0 && (
        <div className="right-card">
          <div className="section-toggle" onClick={() => setLogOpen(o => !o)}>
            <div className="section-toggle-title">
              <CheckCircle2 size={14} color="var(--accent-blue)" /> Self-Reflection Log
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.72rem' }}>
              {iterations} iteration{iterations !== 1 ? 's' : ''}
              {logOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </div>
          </div>

          {logOpen && (
            <div style={{ marginTop: '10px' }}>
              {reflectionLog.map((log, idx) => {
                const isYes = /VERDICT:\s*YES/i.test(log);
                const isNo = /VERDICT:\s*NO/i.test(log);

                // Find lines robustly (handle leading/trailing spaces and think-tag remnants)
                const lines = log.split('\n').map(l => l.trim());
                const reasonLine = lines.find(l => /^REASON:/i.test(l));
                const queryLine = lines.find(l => /^REFINED_QUERY:/i.test(l));

                const reasonText = reasonLine ? reasonLine.replace(/^REASON:\s*/i, '').trim() : '';
                const queryText = queryLine ? queryLine.replace(/^REFINED_QUERY:\s*/i, '').trim() : '';
                const showQuery = queryText && queryText.toUpperCase() !== 'NONE' && queryText.length > 3;

                return (
                  <div key={idx} className="reflection-item">
                    <div className="reflection-header">
                      <span className="reflection-iter">Iteration {idx + 1}</span>
                      <span className={`badge ${isYes ? 'badge-success' : 'badge-error'}`}>
                        {isYes ? 'VERDICT: YES' : isNo ? 'VERDICT: NO' : 'VERDICT: ?'}
                      </span>
                    </div>
                    {reasonText && (
                      <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', lineHeight: 1.4, marginBottom: '3px' }}>
                        {reasonText}
                      </div>
                    )}
                    {showQuery && (
                      <div style={{ fontSize: '0.72rem', color: 'var(--accent-blue)', marginTop: '2px' }}>
                        🔍 {queryText}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Tips ── */}
      <div className="right-card">
        <div className="section-toggle-title" style={{ marginBottom: '10px' }}>
          <AlertCircle size={14} color="var(--warning)" /> Tips for Better Results
        </div>
        <div>
          {[
            'Ask specific, focused questions',
            'Follow-up questions use previous context',
            'Unclear queries are automatically refined',
            'Answers are grounded in your document only',
            'Upload multiple PDFs to build a library',
          ].map((tip, i) => (
            <div key={i} className="tip-item">
              <CheckCircle2 size={13} fill="var(--accent-blue)" color="white" />
              {tip}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
