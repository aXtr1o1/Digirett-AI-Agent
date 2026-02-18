import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL;

// Frontend-side tiny normalization (matches backend intent)
const normalizeText = (t = '') =>
  t
    .replace(/[ \t]+\n/g, '\n')     // trim trailing ws
    .replace(/\n{3,}/g, '\n\n');    // collapse huge gaps

function App() {
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);

  // Streaming refs
  const streamedTextRef = useRef('');
  const streamedSourcesRef = useRef([]);
  const isThinkingRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Tight markdown renderer: prevents <li><p> spacing inflation
  const markdownComponents = {
    p: ({ node, children, ...props }) => {
      const parent = node?.parent;
      const isInsideLI = parent && parent.type === 'listItem';
      if (isInsideLI) return <span {...props}>{children}</span>;
      return <p {...props}>{children}</p>;
    },
    li: ({ children, ...props }) => <li {...props}>{children}</li>,
  };

  const sendMessage = async () => {
    if (!query.trim() || isLoading) return;

    // push user msg
    setMessages((prev) => [...prev, { type: 'user', text: query }]);

    const currentQuery = query;
    setQuery('');
    setIsLoading(true);

    // assistant placeholder
    setMessages((prev) => [
      ...prev,
      { type: 'assistant', text: '', sources: [], streaming: true },
    ]);

    streamedTextRef.current = '';
    streamedSourcesRef.current = [];
    isThinkingRef.current = false;

    try {
      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          query: currentQuery,
          top_k: 3,
          temperature: 0.7,
          include_sources: true,
        }),
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events split by blank line
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const evt of events) {
          const dataLines = evt
            .split('\n')
            .filter((l) => l.startsWith('data:'))
            .map((l) => l.replace(/^data:\s?/, ''));

          if (!dataLines.length) continue;

          const jsonStr = dataLines.join('\n').trim();
          if (!jsonStr) continue;

          let event;
          try {
            event = JSON.parse(jsonStr);
          } catch {
            continue;
          }

          if (event.type === 'token') {
            const token = event.data || '';

            // hide think blocks
            if (token.includes('<think>')) {
              isThinkingRef.current = true;
              continue;
            }
            if (token.includes('</think>')) {
              isThinkingRef.current = false;
              continue;
            }
            if (isThinkingRef.current) continue;

            streamedTextRef.current += token;

            // normalize lightly to avoid weird spacing bursts during stream
            const normalized = normalizeText(streamedTextRef.current);

            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              updated[updated.length - 1] = { ...last, text: normalized };
              return updated;
            });
          }

          if (event.type === 'sources') {
            // store but DO NOT render until complete
            streamedSourcesRef.current = event.data || [];
          }

          if (event.type === 'complete') {
            const finalText = normalizeText(streamedTextRef.current.trim());

            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                type: 'assistant',
                text: finalText,
                sources: (streamedSourcesRef.current || []).slice(0, 3),
                streaming: false,
              };
              return updated;
            });
          }

          if (event.type === 'error') {
            throw new Error(event.message || 'Unknown error');
          }
        }
      }
    } catch (error) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          type: 'assistant',
          text: `❌ ${error.message}`,
          error: true,
          streaming: false,
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">Ask me anything about Norwegian law</div>
        )}

        {messages.map((msg, index) => (
          <div
            key={index}
            className={`message ${msg.type} ${msg.error ? 'error' : ''}`}
          >
            <div className="message-text">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {msg.text}
              </ReactMarkdown>
            </div>

            {msg.sources && msg.sources.length > 0 && !msg.streaming && (
              <div className="sources">
                <div className="sources-title">Sources ({msg.sources.length})</div>
                {msg.sources.map((s, i) => (
                  <div key={i} className="source-item">
                    <div className="source-header">
                      <span className="source-number">{i + 1}</span>
                      <a
                        href={s.url || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="source-link"
                      >
                        {s.title || `Source ${i + 1}`}
                      </a>
                    </div>
                    <div className="source-text">
                      {s.chunk_text || s.text || ''}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <div className="input-wrapper">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about Norwegian law..."
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !query.trim()}
            className="send-btn"
          >
            {isLoading ? <div className="spinner"></div> : '➤'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;