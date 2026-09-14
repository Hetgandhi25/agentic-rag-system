import React, { useState, useRef } from 'react';
import {
  Send, Paperclip, Copy, Check, RotateCw,
  ThumbsUp, ThumbsDown, MessageSquare, Link, X, Lock
} from 'lucide-react';

// ─── Lightweight Markdown Renderer ──────────────────────────────────────────
// Converts common markdown patterns to safe HTML.
function renderMarkdown(text) {
  if (!text) return '';

  let html = text
    // 1. Escape HTML entities to prevent XSS
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 2. Fenced code blocks  ```lang\n...\n```
    .replace(/```[\w]*\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    // 3. Inline code `...`
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
    // 4. Bold **...**
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    // 5. Italic *...*  (but not **)
    .replace(/(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
    // 6. Headings
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // 7. Unordered list items (- or *)
    .replace(/^[ \t]*[-*] (.+)$/gm, '<li>$1</li>')
    // 8. Ordered list items
    .replace(/^[ \t]*\d+\. (.+)$/gm, '<li>$1</li>')
    // 9. Wrap consecutive <li> items in <ul>
    .replace(/(<li>.*<\/li>\n?)+/gs, '<ul>$&</ul>')
    // 10. Double newline → paragraph break
    .replace(/\n\n+/g, '</p><p>')
    // 11. Single newline → <br>
    .replace(/\n/g, '<br>');

  return `<p>${html}</p>`;
}

export default function ChatWorkspace({
  isReady,
  documentDeleted,
  loading,
  streamingStatus,
  question,
  setQuestion,
  handleAsk,
  chatEndRef,
  messages,
  handleRegenerate,
  handleFeedback,
  errorMsg,
  setErrorMsg,
}) {
  const [copiedId, setCopiedId] = useState(null);
  const textareaRef = useRef(null);

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }).catch(() => {
      const el = document.createElement('textarea');
      el.value = text;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  const autoResize = (e) => {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  };

  const lastAiMsg = messages.filter(m => m.role === 'ai').at(-1);

  // Determine composer placeholder and disabled state
  const composerDisabled = (!isReady && !documentDeleted) || loading || documentDeleted;
  const composerPlaceholder = documentDeleted
    ? 'Document was deleted — this chat is read-only'
    : isReady
    ? 'Ask a question about the document… (Shift+Enter for new line)'
    : 'Upload a document to start asking questions';

  return (
    <div className="center-col">
      {/* ── Chat Header ── */}
      <div className="chat-header">
        <div className="chat-header-title">Chat &amp; Ask</div>
        <div className="chat-header-sub">
          Ask questions about your document. Answers are grounded in retrieved context with self-reflection and query refinement.
        </div>
      </div>

      {/* ── Document Deleted Banner ── */}
      {documentDeleted && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: '8px',
          background: '#fef3c7', borderBottom: '1px solid #fcd34d',
          padding: '8px 20px', fontSize: '0.80rem', color: '#92400e', flexShrink: 0,
        }}>
          <Lock size={13} />
          <span>
            <strong>Read-only mode</strong> — this conversation's document was deleted.
            You can view the history but cannot ask new questions.
            Upload a new PDF to start a fresh chat.
          </span>
        </div>
      )}

      {/* ── Error Banner ── */}
      {errorMsg && (
        <div className="error-banner">
          <span>⚠️ {errorMsg}</span>
          <button onClick={() => setErrorMsg('')} className="error-close">
            <X size={14} />
          </button>
        </div>
      )}

      {/* ── Messages ── */}
      <div className="chat-display">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-icon">
              <MessageSquare size={26} />
            </div>
            <div className="empty-state-title">
              {isReady
                ? 'Ask your first question'
                : documentDeleted
                ? 'No messages in this conversation'
                : 'Select or upload a document to start'}
            </div>
            <div className="empty-state-desc">
              {isReady
                ? 'The agent retrieves relevant context, grades quality, refines queries if needed, and provides a grounded answer.'
                : documentDeleted
                ? 'This conversation\'s document was deleted. Upload a new PDF to start a new chat.'
                : 'Upload a PDF using the panel on the right. The agent will index it and you can start asking questions immediately.'}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const isLastMsg = idx === messages.length - 1;

          if (msg.role === 'user') {
            return (
              <div key={msg.id || idx} className="msg-user-row">
                <div className="msg-user-bubble">{msg.content}</div>
              </div>
            );
          }

          // ── AI Message ──
          const isStreamingThisMsg = loading && isLastMsg;
          const isEmptyStreaming = isStreamingThisMsg && !msg.content;

          // Only show sources when context was actually used (allNo flag not set)
          const showSources = msg.sources && msg.sources.length > 0 && !msg.allNo && !isEmptyStreaming;

          return (
            <div key={msg.id || idx} className="msg-ai-row">
              <div className="msg-ai-avatar">🤖</div>
              <div className="msg-ai-content">
                <div className="msg-ai-bubble">
                  {isEmptyStreaming ? (
                    /* Still waiting for first content */
                    <div className="streaming-status">
                      <div className="streaming-dot" />
                      <span className="pulse-text">{streamingStatus || 'Thinking...'}</span>
                    </div>
                  ) : (
                    <>
                      <div dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />

                      {/* Show streaming indicator below partial content */}
                      {isStreamingThisMsg && msg.content && streamingStatus && (
                        <div className="streaming-status" style={{ marginTop: '10px' }}>
                          <div className="streaming-dot" />
                          <span className="pulse-text">{streamingStatus}</span>
                        </div>
                      )}

                      {/* ── Source Cards (only when retrieval succeeded) ── */}
                      {showSources && (
                        <div className="sources-section">
                          <div className="sources-header">
                            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                              <Link size={12} /> Retrieved sources
                            </span>
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.70rem' }}>
                              {msg.sources.length} chunk{msg.sources.length !== 1 ? 's' : ''}
                            </span>
                          </div>
                          <div className="sources-grid">
                            {[...msg.sources]
                              .sort((a, b) => parseFloat(b.rel || 0) - parseFloat(a.rel || 0))
                              .map((src, i) => (
                                <div key={i} className="source-card">
                                  <div className="source-page">Page {src.page}</div>
                                  <div className="source-text">{src.text}</div>
                                  <div className="source-score">
                                    Relevance: {src.rel}
                                  </div>
                                </div>
                              ))}
                          </div>
                        </div>
                      )}

                      {/* ── Metrics ── */}
                      {msg.metrics && !isStreamingThisMsg && (
                        <div style={{
                          display: 'flex', gap: '12px', marginTop: '12px', paddingTop: '10px',
                          borderTop: '1px solid var(--border)', fontSize: '0.70rem', color: 'var(--text-muted)'
                        }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6' }}></span>
                            Total System: {(msg.metrics.total_time || 0).toFixed(2)}s
                          </span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10b981' }}></span>
                            Retrieval: {(msg.metrics.retrieval_time || 0).toFixed(2)}s
                          </span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#8b5cf6' }}></span>
                            LLM Generation: {(msg.metrics.llm_time || 0).toFixed(2)}s
                          </span>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* ── Action Buttons (shown only after streaming completes) ── */}
                {msg.content && !isEmptyStreaming && (
                  <div className="msg-actions">
                    <button
                      className={`action-btn ${copiedId === msg.id ? 'copied' : ''}`}
                      onClick={() => handleCopy(msg.content, msg.id)}
                      title="Copy answer to clipboard"
                    >
                      {copiedId === msg.id
                        ? <><Check size={12} /> Copied</>
                        : <><Copy size={12} /> Copy</>}
                    </button>

                    {/* Only show Regenerate on the most recent AI message, and only if doc is not deleted */}
                    {msg.id === lastAiMsg?.id && !loading && !documentDeleted && (
                      <button
                        className="action-btn"
                        onClick={handleRegenerate}
                        title="Generate a new answer for this question"
                        disabled={loading}
                      >
                        <RotateCw size={12} /> Regenerate
                      </button>
                    )}

                    <button
                      className={`action-btn ${msg.feedback === 1 ? 'active-good' : ''}`}
                      onClick={() => handleFeedback(msg.id, msg.feedback === 1 ? 0 : 1)}
                      title="Good answer"
                    >
                      <ThumbsUp size={12} />
                    </button>

                    <button
                      className={`action-btn ${msg.feedback === -1 ? 'active-bad' : ''}`}
                      onClick={() => handleFeedback(msg.id, msg.feedback === -1 ? 0 : -1)}
                      title="Not helpful"
                    >
                      <ThumbsDown size={12} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        <div ref={chatEndRef} />
      </div>

      {/* ── Composer Bar ── */}
      <div className="composer-wrap">
        <div className={`composer-bar ${composerDisabled ? 'composer-disabled' : ''}`}>
          {documentDeleted ? (
            <Lock size={16} color="var(--text-muted)" style={{ flexShrink: 0 }} />
          ) : (
            <Paperclip size={16} color="var(--text-muted)" style={{ flexShrink: 0 }} />
          )}
          <textarea
            ref={textareaRef}
            className="composer-input"
            placeholder={composerPlaceholder}
            value={question}
            onChange={(e) => { setQuestion(e.target.value); autoResize(e); }}
            onKeyDown={handleKeyDown}
            disabled={composerDisabled}
            rows={1}
          />
          <button
            className="btn-send"
            onClick={handleAsk}
            disabled={composerDisabled || !question.trim()}
            title={documentDeleted ? 'Read-only — document was deleted' : 'Send (Enter)'}
          >
            <Send size={15} /> Send
          </button>
        </div>
      </div>
    </div>
  );
}
