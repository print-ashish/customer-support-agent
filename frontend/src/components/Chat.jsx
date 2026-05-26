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
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [sessionId, setSessionId] = useState(() => {
    let sid = sessionStorage.getItem("chat_session_id");
    if (!sid) {
      sid = typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
      sessionStorage.setItem("chat_session_id", sid);
    }
    return sid;
  });
  const bottomRef = useRef(null);

  useEffect(() => {
    setHistoryLoading(true);
    getHistory(token, sessionId)
      .then(({ conversation_id, messages }) => {
        setConversationId(conversation_id);
        setMessages(messages ?? []);
      })
      .catch(() => setMessages([]))
      .finally(() => setHistoryLoading(false));
  }, [token, sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function startNewSession() {
    const newSid = typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    sessionStorage.setItem("chat_session_id", newSid);
    setSessionId(newSid);
    setConversationId(null);
    setMessages([]);
  }

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const { response, escalated } = await sendMessage(token, text, sessionId);
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
      <div className="session-badge-container">
        <div className="session-badge">
          Session&nbsp;<code>#{sessionId ? sessionId.substring(0, 8) + "..." : "none"}</code>
        </div>
        <button type="button" className="btn secondary btn-sm" onClick={startNewSession}>
          New Chat
        </button>
      </div>
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
