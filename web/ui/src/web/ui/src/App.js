import React, { useEffect, useState } from "react";

function App() {
  const [templates, setTemplates] = useState([]);
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [html, setHtml] = useState("<h1>Invoice</h1>");
  useEffect(() => {
    const t = localStorage.getItem("token");
    if (t) setToken(t);
  }, []);
  async function loadTemplates() {
    const res = await fetch("/templates", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const json = await res.json();
      setTemplates(json);
    } else {
      console.error("Failed to load templates");
    }
  }
  async function createTemplate(e) {
    e.preventDefault();
    const res = await fetch("/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name, html })
    });
    if (res.ok) {
      setName(""); setHtml("<h1>Invoice</h1>");
      loadTemplates();
    } else {
      alert("Failed to create template");
    }
  }
  return (
    <div style={{ padding: 20 }}>
      <h2>Template Manager (UI scaffold)</h2>
      {!token && <div>Please login using the API to obtain a bearer token and save it to localStorage as "token".</div>}
      <button onClick={loadTemplates}>Load templates</button>
      <ul>
        {templates.map(t => <li key={t.id}>{t.name}</li>)}
      </ul>
      <h3>Create Template</h3>
      <form onSubmit={createTemplate}>
        <div><input value={name} onChange={e => setName(e.target.value)} placeholder="Template name" /></div>
        <div><textarea rows={10} cols={80} value={html} onChange={e => setHtml(e.target.value)} /></div>
        <button type="submit">Create</button>
      </form>
    </div>
  );
}

export default App;
            
