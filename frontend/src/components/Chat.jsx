import { useState, useEffect, useRef } from "react";
import { getHistory, sendMessage } from "../api";
import MessageContent from "./MessageContent";

const ROLE_LABEL = {
  user: "You",
  agent: "Agent",
  human_agent: "Human agent",
  system: "System",
  tool: "Tool",
};

export default function Chat({ token }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const bottomRef = useRef(null);

  useEffect(() => {
    getHistory(token)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setHistoryLoading(false));
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const { response, escalated } = await sendMessage(token, text);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          content: response,
          escalated,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "agent", content: `Error: ${err.message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat">
      <div className="chat-messages">
        {historyLoading ? (
          <p className="muted center">Loading conversation…</p>
        ) : messages.length === 0 ? (
          <div className="empty-state">
            <p>How can we help you today?</p>
            <span>Ask about orders, returns, or account issues.</span>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              className={`bubble ${msg.role === "user" ? "user" : "agent"}${msg.error ? " error" : ""}`}
            >
              <span className="bubble-label">
                {ROLE_LABEL[msg.role] || msg.role}
                {msg.escalated && <span className="badge">Escalated</span>}
              </span>
              <MessageContent
                content={msg.content}
                markdown={msg.role !== "user"}
              />
            </div>
          ))
        )}
        {loading && (
          <div className="bubble agent typing">
            <span className="bubble-label">Agent</span>
            <div className="dots">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message…"
          disabled={loading}
          autoFocus
        />
        <button type="submit" className="btn primary" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
