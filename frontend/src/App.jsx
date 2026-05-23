import { useState, useEffect } from "react";
import Auth from "./components/Auth";
import Chat from "./components/Chat";
import Admin from "./components/Admin";

const TOKEN_KEY = "support_token";

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [view, setView] = useState("chat");

  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }, [token]);

  function handleAuth(accessToken) {
    setToken(accessToken);
    setView("chat");
  }

  function logout() {
    setToken(null);
    setView("chat");
  }

  if (!token) {
    return <Auth onAuth={handleAuth} />;
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand-dot" />
          <h1>Support Agent</h1>
        </div>
        <nav className="nav">
          <button
            type="button"
            className={view === "chat" ? "nav-btn active" : "nav-btn"}
            onClick={() => setView("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            className={view === "admin" ? "nav-btn active" : "nav-btn"}
            onClick={() => setView("admin")}
          >
            Admin
          </button>
          <button type="button" className="nav-btn ghost" onClick={logout}>
            Sign out
          </button>
        </nav>
      </header>

      <main className="main">
        {view === "chat" ? <Chat token={token} /> : <Admin />}
      </main>
    </div>
  );
}
