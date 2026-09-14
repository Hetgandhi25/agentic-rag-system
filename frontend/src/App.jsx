import React, { useState, useEffect, useRef, useCallback } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import ChatWorkspace from './components/ChatWorkspace';
import RightSidebar from './components/RightSidebar';
import './App.css';

const LS_SESSION_KEY = 'rag_active_session_id';

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [documents, setDocuments] = useState([]);

  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [currentDocumentId, setCurrentDocumentId] = useState(null);
  const [currentDocumentDeleted, setCurrentDocumentDeleted] = useState(false);
  const [messages, setMessages] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [newChatLoading, setNewChatLoading] = useState(false);

  const [question, setQuestion] = useState('');
  const [iterations, setIterations] = useState(0);
  const [reflectionLog, setReflectionLog] = useState([]);
  const [streamingStatus, setStreamingStatus] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);
  const abortRef = useRef(null);

  // ── Boot: load documents + sessions, then restore last active session ──
  useEffect(() => {
    const init = async () => {
      await fetchDocuments();
      const sessData = await fetchSessions();
      // Restore last active session from localStorage
      const savedId = localStorage.getItem(LS_SESSION_KEY);
      if (savedId && sessData && sessData.some(s => s.id === savedId)) {
        await loadSession(savedId, true);
      }
    };
    init();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist active session to localStorage whenever it changes
  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem(LS_SESSION_KEY, currentSessionId);
    }
  }, [currentSessionId]);

  const fetchDocuments = async () => {
    try {
      const res = await fetch('/api/documents');
      if (!res.ok) return;
      const data = await res.json();
      setDocuments(data.documents || []);
    } catch (e) {
      console.error('fetchDocuments:', e);
    }
  };

  // Returns the fetched sessions array for use in init()
  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) return [];
      const data = await res.json();
      const sess = data.sessions || [];
      setSessions(sess);
      return sess;
    } catch (e) {
      console.error('fetchSessions:', e);
      return [];
    }
  };

  const loadSession = async (sessionId, force = false) => {
    if (!force && sessionId === currentSessionId) return; // Already loaded
    try {
      const res = await fetch(`/api/sessions/${sessionId}`);
      if (!res.ok) {
        setErrorMsg('Could not load session. It may have been deleted.');
        return;
      }
      const data = await res.json();
      setCurrentSessionId(data.session.id);
      setCurrentDocumentId(data.session.document_id);
      setCurrentDocumentDeleted(data.session.document_deleted || false);
      setMessages(data.messages || []);
      setReflectionLog([]);
      setIterations(0);
      setStreamingStatus('');
      setErrorMsg('');
    } catch (e) {
      console.error('loadSession:', e);
      setErrorMsg('Failed to load conversation.');
    }
  };

  const handleNewChat = async () => {
    if (newChatLoading) return; // Prevent duplicate clicks
    setNewChatLoading(true);
    setErrorMsg('');
    try {
      // Guard: reuse any existing completely empty session instead of creating duplicate New Chats
      const existingEmpty = sessions.find(s => s.title === 'New Chat' && !s.document_id);
      if (existingEmpty) {
        if (existingEmpty.id !== currentSessionId) {
          await loadSession(existingEmpty.id);
        }
        setNewChatLoading(false);
        return;
      }

      // Create an empty session
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        setErrorMsg('Failed to create session: ' + (err.detail || ''));
        return;
      }
      const data = await res.json();
      await fetchSessions();
      loadSessionDirect(data.session);
    } catch (e) {
      console.error('handleNewChat:', e);
      setErrorMsg('Failed to create new chat.');
    } finally {
      setNewChatLoading(false);
    }
  };

  // Load session from an already-known session object (avoids extra API call)
  const loadSessionDirect = (session) => {
    setCurrentSessionId(session.id);
    setCurrentDocumentId(session.document_id);
    setCurrentDocumentDeleted(session.document_deleted || false);
    setMessages([]);
    setReflectionLog([]);
    setIterations(0);
    setStreamingStatus('');
    setErrorMsg('');
  };

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setErrorMsg('Only PDF files are supported.');
      return;
    }
    setUploading(true);
    setErrorMsg('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        setErrorMsg('Upload failed: ' + (data.detail || response.statusText));
        return;
      }
      if (data.success) {
        await fetchDocuments();
        const newDocId = data.document.id;

        // If we are currently in an empty "New Chat" session, attach the document
        // Otherwise, create a new session for this document.
        const freshSessions = await fetch('/api/sessions').then(r => r.json()).then(d => d.sessions || []);
        const existingSess = freshSessions.find(s => s.id === currentSessionId);
        
        if (currentSessionId && existingSess && existingSess.title === 'New Chat' && messages.length === 0) {
           const res = await fetch(`/api/sessions/${currentSessionId}`, {
               method: 'PUT',
               headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify({ document_id: newDocId }),
           });
           const sessData = await res.json();
           await fetchSessions();
           loadSessionDirect(sessData.session);
        } else {
           const res = await fetch('/api/sessions', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ document_id: newDocId }),
           });
           const sessData = await res.json();
           await fetchSessions();
           loadSessionDirect(sessData.session);
        }
      }
    } catch (error) {
      console.error('handleUpload:', error);
      setErrorMsg('Upload error: ' + error.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSelectDocument = async (docId) => {
    setErrorMsg('');
    try {
      const freshSessions = await fetch('/api/sessions').then(r => r.json()).then(d => d.sessions || []);
      const existingSess = freshSessions.find(s => s.id === currentSessionId);
      
      // If currently in an empty new chat, attach it
      if (currentSessionId && existingSess && existingSess.title === 'New Chat' && messages.length === 0 && !existingSess.document_id) {
         const res = await fetch(`/api/sessions/${currentSessionId}`, {
             method: 'PUT',
             headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify({ document_id: docId }),
         });
         const sessData = await res.json();
         await fetchSessions();
         loadSessionDirect(sessData.session);
      } else {
         // See if there's an empty session for this doc
         const existingEmpty = freshSessions.find(
           s => s.document_id === docId && s.title === 'New Chat' && (!s.messages || s.messages.length === 0)
         );
         if (existingEmpty) {
            await loadSession(existingEmpty.id);
         } else {
            // Create a new session
            const res = await fetch('/api/sessions', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ document_id: docId }),
            });
            const sessData = await res.json();
            await fetchSessions();
            loadSessionDirect(sessData.session);
         }
      }
    } catch (error) {
      console.error('handleSelectDocument:', error);
      setErrorMsg('Error selecting document.');
    }
  };
  const handleDeleteDocument = async (docId) => {
    if (!window.confirm(
      'Delete this document?\n\n' +
      'Existing conversations will be kept in read-only mode — you can still review the chat history, ' +
      'but new questions cannot be answered without a document.'
    )) return;
    setErrorMsg('');
    try {
      const res = await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
        setErrorMsg('Delete failed: ' + (err.detail || ''));
        return;
      }
      await fetchDocuments();
      await fetchSessions();

      // If the current session belonged to this document, mark it as read-only
      // (the API has already null'd its document_id) — reload to get fresh state
      if (currentDocumentId === docId) {
        setCurrentDocumentId(null);
        setCurrentDocumentDeleted(true);
        // Keep currentSessionId so history remains visible
        // But refresh the messages from DB to confirm state
        if (currentSessionId) {
          await loadSession(currentSessionId, true);
        }
      }
    } catch (e) {
      console.error('handleDeleteDocument:', e);
      setErrorMsg('Failed to delete document.');
    }
  };

  const handleDeleteSession = async (sessionId) => {
    if (!window.confirm('Delete this conversation?')) return;
    try {
      await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      await fetchSessions();
      if (currentSessionId === sessionId) {
        localStorage.removeItem(LS_SESSION_KEY);
        // Find next available session
        const remaining = await fetch('/api/sessions').then(r => r.json()).then(d => d.sessions || []);
        if (remaining.length > 0) {
          loadSession(remaining[0].id);
        } else {
          handleNewChat();
        }
      }
    } catch (e) {
      console.error('handleDeleteSession:', e);
    }
  };

  const handleAsk = useCallback(async (retryQuestion = null) => {
    const textToAsk = retryQuestion !== null ? retryQuestion : question;
    if (!textToAsk.trim()) {
      setErrorMsg('Please enter a question.');
      return;
    }
    if (!currentSessionId) {
      setErrorMsg('No active session. Please create a new chat first.');
      return;
    }
    if (currentDocumentDeleted) {
      setErrorMsg('This conversation\'s document was deleted. New questions cannot be answered.');
      return;
    }
    if (loading) return; // Prevent concurrent requests

    // Cancel any previous stream
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    // Optimistically add user message and AI placeholder
    const tempUserId = 'u-' + Date.now();
    setMessages(prev => [
      ...prev,
      { id: tempUserId, role: 'user', content: textToAsk },
      { id: 'temp-ai', role: 'ai', content: '', sources: null },
    ]);

    setQuestion('');
    setLoading(true);
    setStreamingStatus('Connecting to agent...');
    setReflectionLog([]);
    setIterations(0);
    setErrorMsg('');
    scrollToBottom();

    try {
      const response = await fetch('/api/chat_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId, question: textToAsk }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        let result;
        try {
          result = await reader.read();
        } catch (readErr) {
          if (readErr.name === 'AbortError') break;
          throw readErr;
        }

        const { value, done } = result;
        
        if (value) {
          buffer += decoder.decode(value, { stream: true });
        }

        if (done) {
          if (buffer.trim()) {
            let eventType = 'message';
            let dataStr = '';
            for (const line of buffer.split(/\r?\n/)) {
              if (line.startsWith('event:')) eventType = line.slice(6).trim();
              else if (line.startsWith('data:')) dataStr = line.slice(5).trim();
            }
            if (dataStr) processSSEEvent(eventType, dataStr);
          }
          break;
        }

        // Process complete SSE blocks (delimited by \n\n or \r\n\r\n)
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop(); // keep incomplete last block

        for (const block of blocks) {
          if (!block.trim()) continue;
          let eventType = 'message';
          let dataStr = '';
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith('event:')) eventType = line.slice(6).trim();
            else if (line.startsWith('data:')) dataStr = line.slice(5).trim();
          }
          processSSEEvent(eventType, dataStr);
          scrollToBottom();
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        setMessages(prev => prev.filter(m => m.id !== 'temp-ai'));
      } else {
        console.error('handleAsk stream error:', error);
        const errMsg = `⚠️ ${error.message || 'Network error. Please try again.'}`;
        setMessages(prev => prev.map(m =>
          m.id === 'temp-ai' ? { ...m, content: errMsg } : m
        ));
        setErrorMsg(error.message || 'Stream failed');
      }
    } finally {
      setLoading(false);
      setStreamingStatus('');
      abortRef.current = null;
      // Refresh session list to update titles
      fetchSessions();
    }
  }, [question, currentSessionId, currentDocumentDeleted, loading]);

  const processSSEEvent = (eventType, dataStr) => {
    switch (eventType) {
      case 'status':
        setStreamingStatus(dataStr);
        break;
      case 'log':
        try {
          const logs = JSON.parse(dataStr);
          setReflectionLog(logs);
          setIterations(logs.length);
        } catch {}
        break;
      case 'sources':
        try {
          const srcs = JSON.parse(dataStr);
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, sources: srcs };
            return copy;
          });
        } catch {}
        break;
      case 'all_no':
        try {
          const isAllNo = JSON.parse(dataStr);
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, allNo: isAllNo };
            return copy;
          });
        } catch {}
        break;
      case 'token':
        try {
          const t = JSON.parse(dataStr);
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, content: last.content + t };
            return copy;
          });
        } catch {}
        break;
      case 'metrics':
        try {
          const m = JSON.parse(dataStr);
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, metrics: m };
            return copy;
          });
        } catch {}
        break;
      case 'answer':
        try {
          const ans = JSON.parse(dataStr);
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, content: ans };
            return copy;
          });
        } catch {
          setMessages(prev => {
            const copy = [...prev];
            const last = copy[copy.length - 1];
            if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, content: dataStr };
            return copy;
          });
        }
        break;
      case 'message_id':
        setMessages(prev => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === 'ai') copy[copy.length - 1] = { ...last, id: dataStr };
          return copy;
        });
        break;
      case 'error':
        console.error('SSE error event:', dataStr);
        setMessages(prev => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last && last.role === 'ai') {
            copy[copy.length - 1] = { ...last, content: `⚠️ Error: ${dataStr}` };
          }
          return copy;
        });
        setErrorMsg(dataStr);
        break;
      case 'done':
        setStreamingStatus('');
        break;
      default:
        break;
    }
  };

  const handleRegenerate = useCallback(async () => {
    if (!currentSessionId || loading) return;

    // Find the last user question from local state
    let lastUserQ = '';
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        lastUserQ = messages[i].content;
        break;
      }
    }
    if (!lastUserQ) return;

    try {
      const res = await fetch('/api/regenerate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSessionId }),
      });
      if (!res.ok) return;

      // Remove the last AI message from local state
      setMessages(prev => {
        const copy = [...prev];
        for (let i = copy.length - 1; i >= 0; i--) {
          if (copy[i].role === 'ai') {
            copy.splice(i, 1);
            break;
          }
        }
        return copy;
      });

      await handleAsk(lastUserQ);
    } catch (e) {
      console.error('handleRegenerate:', e);
    }
  }, [currentSessionId, loading, messages, handleAsk]);

  const handleFeedback = async (msgId, val) => {
    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: msgId, feedback: val }),
      });
      if (!res.ok) return;
      setMessages(prev => prev.map(m =>
        m.id === msgId ? { ...m, feedback: val } : m
      ));
    } catch (e) {
      console.error('handleFeedback:', e);
    }
  };

  const scrollToBottom = () =>
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { scrollToBottom(); }, [messages]);

  const activeDocument = documents.find(d => d.id === currentDocumentId);
  // isReady: session exists AND document is available (not deleted)
  const isReady = !!currentSessionId && !!currentDocumentId && !currentDocumentDeleted;

  return (
    <div className="app-shell">
      <Navbar />
      <div className="main-layout">
        <Sidebar
          sessions={sessions}
          documents={documents}
          currentSessionId={currentSessionId}
          currentDocumentId={currentDocumentId}
          loadSession={loadSession}
          handleNewChat={handleNewChat}
          handleDeleteSession={handleDeleteSession}
          handleSelectDocument={handleSelectDocument}
          newChatLoading={newChatLoading}
        />

        <ChatWorkspace
          isReady={isReady}
          documentDeleted={currentDocumentDeleted}
          loading={loading}
          streamingStatus={streamingStatus}
          question={question}
          setQuestion={setQuestion}
          handleAsk={() => handleAsk()}
          chatEndRef={chatEndRef}
          messages={messages}
          handleRegenerate={handleRegenerate}
          handleFeedback={handleFeedback}
          errorMsg={errorMsg}
          setErrorMsg={setErrorMsg}
        />

        <RightSidebar
          activeDocument={activeDocument}
          documentDeleted={currentDocumentDeleted}
          uploading={uploading}
          handleDeleteDocument={handleDeleteDocument}
          handleUpload={handleUpload}
          fileInputRef={fileInputRef}
          iterations={iterations}
          reflectionLog={reflectionLog}
        />
      </div>
    </div>
  );
}
