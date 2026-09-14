import React from 'react';
import { FileText } from 'lucide-react';

export default function Navbar() {
  return (
    <div className="top-nav">
      <div className="nav-logo">
        <div className="nav-logo-icon">
          <FileText size={17} />
        </div>
        <div>
          <div className="nav-logo-title">Self-Reflective Agentic RAG</div>
          <div className="nav-logo-sub">Grounded document QA with retrieval grading &amp; query refinement</div>
        </div>
      </div>
      <div className="nav-badges">
        <span className="nav-badge"><span style={{ color: 'var(--success)', fontSize: '0.6rem' }}>●</span> vLLM (qwen3.8-27b)</span>
        <span className="nav-badge"><span style={{ color: 'var(--accent-blue)' }}>✓</span> nomic-embed-text</span>
        <span className="nav-badge"><span style={{ color: 'var(--success)', fontSize: '0.6rem' }}>●</span> NVIDIA DGX Spark</span>
        <div className="nav-avatar">H</div>
      </div>
    </div>
  );
}
