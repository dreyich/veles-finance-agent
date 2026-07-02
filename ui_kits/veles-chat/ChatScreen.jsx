const { useState, useRef, useEffect } = React;

function Composer({ onSend, thinking }) {
  const [val, setVal] = useState("");
  const [focused, setFocused] = useState(false);
  const send = () => { if (val.trim()) { onSend(val.trim()); setVal(""); } };
  return (
    <div style={{ position: "relative", padding: thinking ? "2px" : "1px", borderRadius: "26px",
      background: thinking
        ? "conic-gradient(from var(--rainbow-angle), rgba(255,255,255,0.10) 0deg, rgba(255,255,255,0.10) 210deg, #3da5ff 250deg, #8a4dff 285deg, #ff2d9b 315deg, #ff8a3d 345deg, rgba(255,255,255,0.10) 360deg)"
        : (focused ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.10)"),
      boxShadow: thinking ? "var(--shadow-island), 0 0 26px rgba(138,77,255,0.22)" : "var(--shadow-island)",
      transition: "padding var(--dur-med) var(--ease-soft)" }}>
      <div style={{ position: "relative", overflow: "hidden", background: thinking ? "rgba(14,14,20,0.86)" : "rgba(36,38,48,0.42)", backdropFilter: "blur(40px) saturate(200%) brightness(1.12)",
        WebkitBackdropFilter: "blur(40px) saturate(200%) brightness(1.12)", borderRadius: "24px", padding: "16px 18px",
        boxShadow: "inset 0 1.5px 0.5px rgba(255,255,255,0.45), inset 0 0 0 0.5px rgba(255,255,255,0.10), inset 0 -10px 22px rgba(0,0,0,0.35)" }}>
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, borderRadius: "24px", pointerEvents: "none",
          background: "linear-gradient(150deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 22%, rgba(255,255,255,0) 45%)" }} />
        <textarea
          value={val} rows={1}
          onChange={(e) => setVal(e.target.value)}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Ask follow up…"
          style={{ width: "100%", border: "none", outline: "none", resize: "none", background: "transparent",
            color: "var(--text-primary)", fontFamily: "var(--font-sans)", fontSize: "16px", lineHeight: 1.5 }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button style={pillBtn}>
              <i data-lucide="paperclip" style={{ width: 16, height: 16 }}></i> Attach report
            </button>
            <button style={{ ...pillBtn, padding: 9, borderRadius: "999px" }} aria-label="Voice input">
              <i data-lucide="mic" style={{ width: 16, height: 16 }}></i>
            </button>
          </div>
          <button onClick={send} style={{ width: 44, height: 44, borderRadius: "999px", border: "none",
            cursor: "pointer", background: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
            <i data-lucide={thinking ? "square" : "arrow-up"} style={{ width: 18, height: 18, color: "#0a0a0f" }}></i>
          </button>
        </div>
      </div>
    </div>
  );
}
const pillBtn = { display: "inline-flex", alignItems: "center", gap: "8px", padding: "9px 16px",
  borderRadius: "999px", border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.05)",
  color: "var(--text-secondary)", fontFamily: "var(--font-sans)", fontSize: "14px", cursor: "pointer" };

function Bubble({ role, children }) {
  const { Avatar, Card } = window.VelesDesignSystem_1bfbc8;
  const ai = role === "ai";
  const text = (
    <div style={{ fontSize: "15px", lineHeight: 1.6, color: "var(--text-primary)", fontFamily: ai ? "'Inter', sans-serif" : "var(--font-sans)", letterSpacing: ai ? "-0.011em" : "normal" }}>{children}</div>
  );
  if (ai) {
    return (
      <div style={{ maxWidth: "84%" }}>{text}</div>
    );
  }
  return (
    <div style={{ display: "flex", gap: "14px", alignItems: "flex-start", flexDirection: "row-reverse" }}>
      <Avatar label="JD" size={34} />
      <div style={{ maxWidth: "76%" }}>
        <Card padding="14px 18px"
          style={{ borderRadius: "20px 6px 20px 20px", background: "rgba(255,255,255,0.09)" }}>
          {text}
        </Card>
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      <span style={{ display: "inline-flex", gap: "5px", alignItems: "center" }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "#fff",
            opacity: 0.85, animation: `veles-pulse 1.2s ${i * 0.18}s ease-in-out infinite` }} />
        ))}
        <span style={{ marginLeft: 8, color: "var(--text-tertiary)", fontSize: 13 }}>Analyzing…</span>
      </span>
      <style>{`@keyframes veles-pulse{0%,100%{opacity:.25;transform:translateY(0)}50%{opacity:1;transform:translateY(-3px)}}`}</style>
    </div>
  );
}

async function askVeles(message, history) {
  if (window.VELES_CONFIG_READY) await window.VELES_CONFIG_READY;
  const gatewayUrl = window.VELES_GATEWAY_URL || "http://localhost:8080";
  const webSecret = window.VELES_WEB_SECRET || "";
  const res = await fetch(`${gatewayUrl}/web/agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-web-secret": webSecret },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(res.status === 401
      ? "Not authorized — sign in required."
      : `Request failed (${res.status}). ${detail}`);
  }
  const data = await res.json();
  return data.response ?? JSON.stringify(data);
}

const STARTER = [];

function ChatScreen() {
  const { Badge } = window.VelesDesignSystem_1bfbc8;
  const [msgs, setMsgs] = useState(STARTER);
  const [thinking, setThinking] = useState(false);
  const [thinkType, setThinkType] = useState("diligence");
  const [title, setTitle] = useState("New chat");
  const [sbOpen, setSbOpen] = useState(true);
  const [rpOpen, setRpOpen] = useState(true);
  const scrollRef = useRef(null);

  useEffect(() => { if (window.lucide) window.lucide.createIcons(); });
  useEffect(() => {
    const sc = scrollRef.current;
    if (!sc) return;
    sc.scrollTop = sc.scrollHeight;
    const t = setTimeout(() => { sc.scrollTop = sc.scrollHeight; }, 120);
    return () => clearTimeout(t);
  }, [msgs, thinking, thinkType]);

  const send = async (text) => {
    const history = msgs.map((m) => ({ role: m.role === "ai" ? "assistant" : "user", content: m.text }));
    setMsgs((m) => [...m, { role: "user", text }]);
    setThinkType(window.velesDetectType ? window.velesDetectType(text) : "diligence");
    setThinking(true);
    try {
      const reply = await askVeles(text, history);
      setMsgs((m) => [...m, { role: "ai", text: reply }]);
    } catch (err) {
      setMsgs((m) => [...m, { role: "ai", text: `Something went wrong: ${err.message}` }]);
    } finally {
      setThinking(false);
    }
  };

  const select = (t) => {
    if (t === "__new") { setMsgs([]); setTitle("New chat"); }
    else setTitle(t);
  };

  const iconBtn = { width: 38, height: 38, borderRadius: "50%", cursor: "pointer",
    display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--text-secondary)",
    background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.10)" };

  return (
    <div style={{ position: "relative", zIndex: 1, height: "100%", display: "flex" }}>
      {sbOpen && <window.VelesSidebar active={title} onSelect={select} />}

      <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", height: "100%" }}>
        <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 28px", borderBottom: "1px solid rgba(255,255,255,0.07)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
            <button style={iconBtn} aria-label="Toggle chats" onClick={() => setSbOpen((v) => !v)}>
              <i data-lucide={sbOpen ? "panel-left-close" : "panel-left-open"} style={{ width: 16, height: 16 }}></i>
            </button>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 15, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden",
                textOverflow: "ellipsis" }}>{title}</div>
              <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>Financial analyst · Due diligence</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Badge tone="neutral">Pro</Badge>
            <button style={iconBtn} aria-label="Share"><i data-lucide="share-2" style={{ width: 16, height: 16 }}></i></button>
            <button style={iconBtn} aria-label="Model settings"><i data-lucide="sliders-horizontal" style={{ width: 16, height: 16 }}></i></button>
            <button style={iconBtn} aria-label="Toggle analysis panel" onClick={() => setRpOpen((v) => !v)}>
              <i data-lucide={rpOpen ? "panel-right-close" : "panel-right-open"} style={{ width: 16, height: 16 }}></i>
            </button>
          </div>
        </header>

        <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column",
          maxWidth: 760, margin: "0 auto", width: "100%", padding: "0 24px", boxSizing: "border-box" }}>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column",
            gap: 18, padding: "24px 0 20px" }}>
            {msgs.map((m, i) => <Bubble key={i} role={m.role === "ai" ? "ai" : "user"}>{m.text}</Bubble>)}
            {thinking && <window.VelesThinking type={thinkType} />}
          </div>
          <div style={{ paddingBottom: 24 }}>
            <Composer onSend={send} thinking={thinking} />
          </div>
        </div>
      </main>

      {rpOpen && <window.VelesRightPanel />}
    </div>
  );
}
window.ChatScreenWrap = ChatScreen;
