import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ReactMarkdown from 'react-markdown';

const API_BASE_URL = 'http://127.0.0.1:8000';

function App() {
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);

  // 🔹 Streaming refs (no re-render issues)
  const streamedTextRef = useRef('');
  const streamedSourcesRef = useRef([]);
  const isThinkingRef = useRef(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!query.trim() || isLoading) return;

    // User message
    setMessages(prev => [...prev, { type: 'user', text: query }]);

    const currentQuery = query;
    setQuery('');
    setIsLoading(true);

    // Assistant placeholder
    setMessages(prev => [...prev, { type: 'assistant', text: '', sources: [] }]);

    // Reset refs
    streamedTextRef.current = '';
    streamedSourcesRef.current = [];
    isThinkingRef.current = false;

    try {
      const response = await fetch(`${API_BASE_URL}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
          query: currentQuery,
          top_k: 3,
          temperature: 0.7,
          include_sources: true
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep incomplete line

        for (const line of lines) {
          if (!line.startsWith('data:')) continue;

          const jsonStr = line.replace('data:', '').trim();
          if (!jsonStr) continue;

          const event = JSON.parse(jsonStr);

          // 🔹 STREAM TOKENS (HIDE THINKING)
          if (event.type === 'token') {
            const token = event.data;

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

            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                ...updated[updated.length - 1],
                text: streamedTextRef.current
              };
              return updated;
            });
          }

          // 🔹 SOURCES
          if (event.type === 'sources') {
            streamedSourcesRef.current = event.data || [];
          }

          // 🔹 COMPLETE
          if (event.type === 'complete') {
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = {
                type: 'assistant',
                text: streamedTextRef.current.trim(),
                sources: streamedSourcesRef.current.slice(0, 3)
              };
              return updated;
            });
          }

          // 🔹 ERROR
          if (event.type === 'error') {
            throw new Error(event.message);
          }
        }
      }

    } catch (error) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          type: 'assistant',
          text: `❌ ${error.message}`,
          error: true
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
          <div key={index} className={`message ${msg.type} ${msg.error ? 'error' : ''}`}>
            <div className="message-text">
              <ReactMarkdown>{msg.text}</ReactMarkdown>
            </div>

            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                <div className="sources-title">📚 Sources ({msg.sources.length})</div>
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