import { useState, useEffect } from "react";
import { getEscalations, resolveEscalation } from "../api";

export default function Admin() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [responses, setResponses] = useState({});
  const [submitting, setSubmitting] = useState(null);

  function load() {
    setLoading(true);
    getEscalations()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function handleResolve(id) {
    const response = responses[id]?.trim();
    if (!response) return;

    setSubmitting(id);
    try {
      await resolveEscalation(id, response);
      setResponses((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      load();
    } catch (err) {
      alert(err.message);
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="admin">
      <div className="admin-header">
        <h2>Open escalations</h2>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted empty-admin">No open escalations.</p>
      ) : (
        <ul className="escalation-list">
          {items.map((item) => (
            <li key={item.id} className="escalation-card">
              <div className="escalation-meta">
                <span className="esc-id">#{item.id}</span>
                <span className="badge">{item.status}</span>
              </div>
              <p className="esc-reason">{item.reason}</p>
              <textarea
                placeholder="Write response to customer…"
                value={responses[item.id] || ""}
                onChange={(e) =>
                  setResponses((prev) => ({ ...prev, [item.id]: e.target.value }))
                }
                rows={3}
              />
              <button
                type="button"
                className="btn primary"
                disabled={submitting === item.id || !responses[item.id]?.trim()}
                onClick={() => handleResolve(item.id)}
              >
                {submitting === item.id ? "Sending…" : "Resolve & send"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
