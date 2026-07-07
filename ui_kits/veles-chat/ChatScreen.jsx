const { useState, useRef, useEffect } = React;

// ---- persistent chats (real data, localStorage) ----
const VELES_LS_KEY = "veles.chats.v2";
function loadChats() {
  try {
    const v = JSON.parse(localStorage.getItem(VELES_LS_KEY) || "[]");
    return Array.isArray(v) ? v.filter((c) => c && c.id && c.title) : [];
  } catch { return []; }
}
function uid() {
  return (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}
function timeAgo(ts) {
  const s = Math.max(1, Math.round((Date.now() - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60); if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60); if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24); if (d === 1) return "yesterday";
  if (d < 7) return `${d}d ago`;
  return new Date(ts).toLocaleDateString();
}

function Composer({ onSend, onStop, thinking, empty }) {
  const [val, setVal] = useState("");
  const [focused, setFocused] = useState(false);
  const mobile = window.useVelesMobile();
  const taRef = useRef(null);
  const send = () => { if (val.trim() && !thinking) { onSend(val.trim()); setVal(""); if (taRef.current) taRef.current.style.height = "auto"; } };
  const autosize = (el) => { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 168) + "px"; };
  return (
    <div style={{ position: "relative", padding: thinking ? 2 : 1.5, borderRadius: 23,
      background: thinking
        ? "conic-gradient(from var(--rainbow-angle), rgba(27,36,49,0.08) 0deg 205deg, #8ec5ff 245deg, #b9a7ff 288deg, #8ee7d2 330deg, rgba(27,36,49,0.08) 360deg)"
        : (focused ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.6)"),
      boxShadow: focused || thinking
        ? "0 16px 44px rgba(31,54,84,0.20), 0 3px 10px rgba(31,54,84,0.10)"
        : "0 12px 36px rgba(31,54,84,0.15), 0 2px 8px rgba(31,54,84,0.07)",
      transition: "background .3s var(--ease-soft), box-shadow .35s var(--ease-soft), padding .3s var(--ease-soft)" }}>
      <div style={{ position: "relative", overflow: "hidden", borderRadius: 21.5,
        background: "rgba(255,255,255,0.82)", backdropFilter: "blur(30px) saturate(1.7)",
        WebkitBackdropFilter: "blur(30px) saturate(1.7)", padding: "14px 15px 12px",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.95)" }}>
        <textarea
          ref={taRef} value={val} rows={1}
          onChange={(e) => { setVal(e.target.value); autosize(e.target); }}
          onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || e.shiftKey) return;
            const enterToSend = !window.velesSettings || window.velesSettings.enterToSend !== false;
            if (enterToSend || e.ctrlKey || e.metaKey) { e.preventDefault(); send(); }
          }}
          placeholder={empty ? "Ask Veles anything…" : "Ask follow up…"}
          style={{ width: "100%", boxSizing: "border-box", border: "none", outline: "none", resize: "none",
            background: "transparent", color: "var(--ink-1)",
            fontSize: mobile ? 16 : 15, lineHeight: 1.55,
            padding: "2px 4px", minHeight: 24, maxHeight: 168 }} />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", marginTop: 10 }}>
          <button onClick={thinking ? onStop : send}
            aria-label={thinking ? "Stop generating" : "Send"} title={thinking ? "Stop generating" : "Send"}
            style={{ width: 38, height: 38, borderRadius: 999, border: "none", cursor: "pointer",
              background: thinking ? "rgba(27,36,49,0.72)" : "#1b2431",
              boxShadow: "0 4px 12px rgba(21,29,42,0.30)",
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              transition: "transform .18s var(--ease-soft), background .25s" }}
            onMouseEnter={(e) => { e.currentTarget.style.transform = "scale(1.06)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.transform = "scale(1)"; }}>
            {thinking ? (
              <span aria-hidden="true" style={{ width: 12, height: 12, borderRadius: 3.5, background: "#fff", display: "block" }} />
            ) : (
              <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none"
                stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

function mdToHtml(text) {
  try {
    if (window.marked && window.DOMPurify) {
      const raw = window.marked.parse(text, { gfm: true, breaks: true });
      return window.DOMPurify.sanitize(raw);
    }
  } catch {}
  return null;
}

function copyText(text) {
  const legacy = () => new Promise((resolve, reject) => {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy") ? resolve() : reject(new Error("copy blocked")); }
    catch (e) { reject(e); }
    finally { document.body.removeChild(ta); }
  });
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).catch(legacy);
  }
  return legacy();
}

function Bubble({ role, text, onRetry, retryDisabled }) {
  const [hov, setHov] = useState(false);
  const [copied, setCopied] = useState(false);
  const mobile = window.useVelesMobile();
  useEffect(() => { if (window.lucide) window.lucide.createIcons(); });

  if (role === "user") {
    return (
      <div className="v-fadeup" style={{ display: "flex", justifyContent: "flex-end" }}>
        <div style={{ maxWidth: mobile ? "88%" : "76%", padding: "10px 15px", borderRadius: "17px 17px 5px 17px",
          background: "rgba(27,36,49,0.065)", border: "1px solid rgba(27,36,49,0.05)",
          fontSize: 15, lineHeight: 1.6, color: "var(--ink-1)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {text}
        </div>
      </div>
    );
  }
  const error = role === "error";
  const html = !error ? mdToHtml(text) : null;
  const copy = () => {
    copyText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    }).catch(() => {});
  };
  return (
    <div className="v-fadeup" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      <span aria-hidden="true" style={{ width: 26, height: 26, borderRadius: 8.5, flexShrink: 0, marginTop: 2,
        background: error ? "rgba(194,69,60,0.10)" : "linear-gradient(145deg,#2a3950,#151d2a)",
        border: error ? "1px solid rgba(194,69,60,0.25)" : "none", boxSizing: "border-box",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        color: error ? "#c2453c" : "#fff", fontWeight: 650, fontSize: 12 }}>
        {error ? <i data-lucide="triangle-alert" style={{ width: 13, height: 13 }}></i> : "V"}
      </span>
      <div style={{ maxWidth: mobile ? "100%" : "86%", minWidth: 0, flex: mobile ? 1 : "none", paddingTop: 3 }}>
        {html ? (
          <div className="v-md" dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <div style={{ fontSize: 15, lineHeight: 1.65, color: error ? "#a03f37" : "var(--ink-1)",
            whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{text}</div>
        )}
        {error && onRetry && (
          <button onClick={onRetry} disabled={retryDisabled}
            style={{ marginTop: 8, display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 11px",
              borderRadius: 8, border: "1px solid rgba(194,69,60,0.25)",
              cursor: retryDisabled ? "default" : "pointer",
              opacity: retryDisabled ? 0.5 : 1,
              fontSize: 12.5, fontWeight: 550, color: "#a03f37",
              background: "rgba(194,69,60,0.06)" }}>
            <i data-lucide="rotate-cw" style={{ width: 12, height: 12 }}></i>
            {retryDisabled ? "Retrying…" : "Try again"}
          </button>
        )}
        {!error && (
          <div style={{ height: 26, marginTop: 4, display: "flex", alignItems: "center",
            opacity: hov || copied || mobile ? 1 : 0, transition: "opacity .2s var(--ease-soft)" }}>
            <button onClick={copy} aria-label="Copy response"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4.5px 10px",
                borderRadius: 8, border: "1px solid rgba(27,36,49,0.08)", cursor: "pointer",
                fontSize: 11.5, fontWeight: 550, color: copied ? "#2a7d4f" : "var(--ink-2)",
                background: copied ? "rgba(42,125,79,0.08)" : "rgba(255,255,255,0.6)",
                boxShadow: "0 1px 2px rgba(31,54,84,0.05)",
                transition: "background .2s, color .2s" }}>
              <i data-lucide={copied ? "check" : "copy"} style={{ width: 12, height: 12 }}></i>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

async function askVeles(message, history, signal) {
  if (window.VELES_CONFIG_READY) await window.VELES_CONFIG_READY;
  const gatewayUrl = window.VELES_GATEWAY_URL || "http://localhost:8080";
  const webSecret = window.VELES_WEB_SECRET || "";
  const res = await fetch(`${gatewayUrl}/web/agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-web-secret": webSecret },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(res.status === 401
      ? "Not authorized — sign in required."
      : `Request failed (${res.status}). ${detail}`);
  }
  const data = await res.json();
  return data.answer ?? data.response ?? JSON.stringify(data);
}

function HeaderBtn({ icon, label, onClick, danger }) {
  const [hov, setHov] = useState(false);
  return (
    <button aria-label={label} title={label} onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ width: 32, height: 32, borderRadius: 9, border: "none", cursor: "pointer",
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        color: danger && hov ? "#c2453c" : hov ? "var(--ink-1)" : "var(--ink-2)",
        background: hov ? (danger ? "rgba(194,69,60,0.09)" : "rgba(27,36,49,0.06)") : "transparent",
        transition: "background .2s var(--ease-soft), color .2s" }}>
      <i data-lucide={icon} style={{ width: 15.5, height: 15.5 }}></i>
    </button>
  );
}

function ChatScreen() {
  const [chats, setChats] = useState(loadChats);
  const [activeId, setActiveId] = useState(null);
  const [thinkingId, setThinkingId] = useState(null);
  const [thinkType, setThinkType] = useState("diligence");
  const mobile = window.useVelesMobile();
  const [sbOpen, setSbOpen] = useState(() => !window.velesIsMobile());
  const [confirmDel, setConfirmDel] = useState(false);
  const scrollRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => { setSbOpen(!mobile); }, [mobile]);

  // Pre-warm the RunPod backend on page load, before the user has typed
  // anything — a cold worker takes ~2 minutes, so firing this now instead of
  // on first send hides most of that behind normal page-load/typing time.
  useEffect(() => {
    (async () => {
      if (window.VELES_CONFIG_READY) await window.VELES_CONFIG_READY;
      const gatewayUrl = window.VELES_GATEWAY_URL || "http://localhost:8080";
      fetch(`${gatewayUrl}/warm`, { method: "POST" }).catch(() => {});
    })();
  }, []);

  const active = chats.find((c) => c.id === activeId) || null;
  const msgs = active ? active.msgs : [];
  const thinkingHere = thinkingId !== null && thinkingId === activeId;
  const empty = msgs.length === 0 && !thinkingHere;

  const [, setSetTick] = useState(0);
  useEffect(() => {
    const onSet = () => setSetTick((n) => n + 1);
    window.addEventListener("veles-settings", onSet);
    return () => window.removeEventListener("veles-settings", onSet);
  }, []);

  useEffect(() => { if (window.lucide) window.lucide.createIcons(); });
  useEffect(() => { try { localStorage.setItem(VELES_LS_KEY, JSON.stringify(chats)); } catch {} }, [chats]);
  useEffect(() => { setConfirmDel(false); }, [activeId]);
  useEffect(() => {
    const sc = scrollRef.current;
    if (!sc) return;
    sc.scrollTop = sc.scrollHeight;
    const t = setTimeout(() => { sc.scrollTop = sc.scrollHeight; }, 120);
    return () => clearTimeout(t);
  }, [msgs.length, thinkingId, thinkType, activeId]);

  const appendMsg = (id, m) =>
    setChats((cs) => cs.map((c) => c.id === id ? { ...c, msgs: [...c.msgs, m], ts: Date.now() } : c));

  // With Max workers = 1 on RunPod, there's no longer "a different, already-
  // warm worker" for a retry to land on — a network-layer failure is either
  // (a) a fast connection-level rejection (worth one quick retry) or (b) the
  // request was just slow and finally timed out on the client while the
  // backend kept working (retrying a slow multi-tool-call request piles a
  // second, equally slow, concurrent request onto the same single worker —
  // actively harmful, not helpful). Only auto-retry when the failure came
  // back fast, since that's the signature of (a), not (b).
  const MAX_AUTO_RETRIES = 1;
  const FAST_FAILURE_MS = 8000;

  const send = async (text, { retryCount = 0, chatId = null } = {}) => {
    // chatId is passed explicitly on the internal retry calls below instead
    // of reading activeId from state — activeId is only guaranteed current
    // on the *next* render, so a recursive retry call (made from inside this
    // same invocation, before React re-renders) would otherwise see the
    // pre-update value and mint a second chat entry for a brand-new chat.
    let id = chatId || activeId;
    const history = msgs.map((m) => ({ role: m.role === "user" ? "user" : "assistant", content: m.text }));
    if (!id) {
      id = uid();
      const title = text.length > 58 ? text.slice(0, 58).trimEnd() + "…" : text;
      setChats((cs) => [{ id, title, msgs: [], ts: Date.now() }, ...cs]);
      setActiveId(id);
    }
    if (retryCount === 0) appendMsg(id, { role: "user", text });
    setThinkType(window.velesDetectType ? window.velesDetectType(text) : "diligence");
    setThinkingId(id);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const startedAt = Date.now();
    try {
      const reply = await askVeles(text, history, ctrl.signal);
      appendMsg(id, { role: "ai", text: reply });
    } catch (err) {
      const failedFast = Date.now() - startedAt < FAST_FAILURE_MS;
      if (err.name === "AbortError") { /* user-cancelled, no message */ }
      else if (err instanceof TypeError && retryCount < MAX_AUTO_RETRIES && failedFast) {
        // A network-layer failure (connection dropped) that happened almost
        // immediately — likely a transient connection hiccup, not a slow
        // request timing out. Worth one quick silent retry.
        await send(text, { retryCount: retryCount + 1, chatId: id });
        return;
      } else if (err instanceof TypeError) {
        appendMsg(id, {
          role: "error",
          text: "The server is taking unusually long to respond and the connection dropped. Try again — it usually goes through on the next attempt.",
          retryText: text,
        });
      } else {
        appendMsg(id, { role: "error", text: `Something went wrong: ${err.message}`, retryText: text });
      }
    } finally {
      if (abortRef.current === ctrl) abortRef.current = null;
      setThinkingId((cur) => (cur === id ? null : cur));
    }
  };

  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

  const deleteChat = (id) => {
    setChats((cs) => cs.filter((c) => c.id !== id));
    if (activeId === id) setActiveId(null);
  };
  const renameChat = (id, title) =>
    setChats((cs) => cs.map((c) => c.id === id ? { ...c, title } : c));

  const showRecents = !window.velesSettings || window.velesSettings.showRecents !== false;
  const recents = showRecents ? chats.slice(0, 3) : [];

  const sidebar = (
    <window.VelesSidebar
      chats={chats} activeId={activeId}
      onSelect={(id) => { setActiveId(id); if (mobile) setSbOpen(false); }}
      onNew={() => { setActiveId(null); if (mobile) setSbOpen(false); }}
      onDelete={deleteChat}
      onRename={renameChat}
      onClearAll={() => { setChats([]); setActiveId(null); }} />
  );

  return (
    <div style={{ position: "relative", zIndex: 1, height: "100%", display: "flex",
      padding: mobile ? 8 : 10, boxSizing: "border-box" }}>

      {mobile ? (
        <>
          {/* mobile: sidebar slides over the chat */}
          <div onClick={() => setSbOpen(false)} aria-hidden={!sbOpen}
            style={{ position: "fixed", inset: 0, zIndex: 40,
              background: "rgba(27,36,49,0.30)", backdropFilter: "blur(6px)",
              WebkitBackdropFilter: "blur(6px)",
              opacity: sbOpen ? 1 : 0, pointerEvents: sbOpen ? "auto" : "none",
              transition: "opacity .35s var(--ease-soft)" }} />
          <div style={{ position: "fixed", top: 8, bottom: 8, left: 8,
            width: "min(300px, 84vw)", zIndex: 41,
            transform: sbOpen ? "translateX(0)" : "translateX(calc(-100% - 16px))",
            transition: "transform .45s var(--ease-soft)",
            pointerEvents: sbOpen ? "auto" : "none" }}>
            {sidebar}
          </div>
        </>
      ) : (
        /* desktop: sidebar pushes content (animated width) */
        <div style={{ width: sbOpen ? 274 : 0, flexShrink: 0, height: "100%", overflow: "hidden",
          transition: "width .5s var(--ease-soft)" }}>
          <div style={{ width: 274, height: "100%", boxSizing: "border-box", paddingRight: 10,
            opacity: sbOpen ? 1 : 0, transform: sbOpen ? "translateX(0)" : "translateX(-16px)",
            transition: "opacity .4s var(--ease-soft), transform .5s var(--ease-soft)" }}>
            {sidebar}
          </div>
        </div>
      )}

      {/* main glass panel */}
      <main style={{ flex: 1, minWidth: 0, position: "relative", height: "100%", boxSizing: "border-box",
        borderRadius: 18, overflow: "hidden",
        background: "var(--panel)", backdropFilter: "blur(44px) saturate(1.7)",
        WebkitBackdropFilter: "blur(44px) saturate(1.7)",
        border: "1px solid rgba(255,255,255,0.65)",
        boxShadow: "0 18px 50px rgba(31,54,84,0.14), inset 0 1px 0 rgba(255,255,255,0.85)" }}>

        {/* header */}
        <header style={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 5,
          display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", boxSizing: "border-box" }}>
          <HeaderBtn icon={sbOpen ? "panel-left-close" : "panel-left-open"} label="Toggle sidebar"
            onClick={() => setSbOpen((v) => !v)} />
          <div style={{ minWidth: 0, flex: 1, fontSize: 13.5, fontWeight: 600, letterSpacing: "-0.012em",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            opacity: empty ? 0 : 1, transition: "opacity .3s var(--ease-soft)" }}>
            {active ? active.title : "New chat"}
          </div>
          {active && (
            confirmDel ? (
              <button onClick={() => deleteChat(active.id)} className="v-pop"
                style={{ border: "none", cursor: "pointer", borderRadius: 9, padding: "6.5px 12px",
                  background: "rgba(194,69,60,0.10)", color: "#c2453c", fontSize: 12.5, fontWeight: 550 }}>
                Delete chat?
              </button>
            ) : (
              <HeaderBtn icon="trash-2" label="Delete chat" danger onClick={() => setConfirmDel(true)} />
            )
          )}
        </header>

        {/* messages */}
        <div ref={scrollRef} style={{ position: "absolute", inset: "54px 0 0 0", overflowY: "auto",
          opacity: empty ? 0 : 1, transition: "opacity .35s var(--ease-soft)",
          pointerEvents: empty ? "none" : "auto" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", boxSizing: "border-box",
            padding: mobile ? "12px 14px 150px" : "14px 26px 170px",
            display: "flex", flexDirection: "column", gap: mobile ? 16 : 20 }}>
            {msgs.map((m, i) => (
              <Bubble key={i} role={m.role} text={m.text} retryDisabled={thinkingHere}
                onRetry={m.retryText ? () => send(m.retryText, { retryCount: 1, chatId: activeId }) : null} />
            ))}
            {thinkingHere && <window.VelesThinking type={thinkType} />}
          </div>
        </div>

        {/* empty-state hero */}
        <div aria-hidden={!empty} style={{ position: "absolute", left: 0, right: 0,
          bottom: "calc(46% + 118px)", display: "flex", flexDirection: "column",
          alignItems: "center", gap: 10, padding: "0 24px", textAlign: "center",
          opacity: empty ? 1 : 0, transform: empty ? "translateY(0)" : "translateY(-16px)",
          transition: "opacity .4s var(--ease-soft), transform .5s var(--ease-soft)",
          pointerEvents: "none" }}>
          <img src="/ui_kits/veles-chat/assets/logo-full.svg" alt="Veles" style={{ height: 38, width: "auto", marginBottom: 14 }} />
          <div style={{ fontSize: mobile ? 13 : 14, color: "var(--ink-2)", maxWidth: 420, lineHeight: 1.5 }}>
            Ask about filings, valuations or risk — Veles reads the documents for you.
          </div>
        </div>

        {/* composer (docks center → bottom) */}
        <div style={{ position: "absolute", left: 0, right: 0,
          bottom: empty ? "calc(46% + 0px)" : (mobile ? "calc(0% + 12px)" : "calc(0% + 18px)"),
          transition: "bottom .6s var(--ease-soft)",
          display: "flex", justifyContent: "center", padding: mobile ? "0 12px" : "0 24px", zIndex: 6 }}>
          <div style={{ width: "100%", maxWidth: empty ? 620 : 720,
            transition: "max-width .6s var(--ease-soft)" }}>
            <Composer onSend={send} onStop={stop} thinking={thinkingId !== null} empty={empty} />
          </div>
        </div>

        {/* recent chats (empty state only, real data) */}
        {recents.length > 0 && (
          <div style={{ position: "absolute", left: 0, right: 0, top: "calc(54% + 78px)",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
            padding: "0 24px",
            opacity: empty ? 1 : 0, transform: empty ? "translateY(0)" : "translateY(16px)",
            transition: "opacity .4s var(--ease-soft), transform .5s var(--ease-soft)",
            pointerEvents: empty ? "auto" : "none" }}>
            <div style={{ fontSize: 11, fontWeight: 550, letterSpacing: "0.07em",
              textTransform: "uppercase", color: "var(--ink-3)" }}>Recent chats</div>
            <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap",
              maxWidth: 620, width: "100%" }}>
              {recents.map((c) => (
                <RecentCard key={c.id} chat={c} onOpen={() => setActiveId(c.id)} />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

function RecentCard({ chat, onOpen }) {
  const [hov, setHov] = useState(false);
  const last = chat.msgs[chat.msgs.length - 1];
  return (
    <button onClick={onOpen}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ flex: "1 1 170px", maxWidth: 200, textAlign: "left", cursor: "pointer",
        padding: "12px 13px", borderRadius: 14, border: "1px solid rgba(255,255,255,0.7)",
        background: hov ? "rgba(255,255,255,0.85)" : "rgba(255,255,255,0.55)",
        boxShadow: hov ? "0 10px 26px rgba(31,54,84,0.14)" : "0 4px 14px rgba(31,54,84,0.07)",
        transform: hov ? "translateY(-2px)" : "translateY(0)",
        transition: "all .25s var(--ease-soft)" }}>
      <div style={{ fontSize: 12.5, fontWeight: 550, color: "var(--ink-1)", lineHeight: 1.4,
        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
        overflow: "hidden", marginBottom: 6 }}>{chat.title}</div>
      <div style={{ fontSize: 11, color: "var(--ink-3)" }}>
        {timeAgo(chat.ts)}{last ? ` · ${chat.msgs.length} messages` : ""}
      </div>
    </button>
  );
}

window.ChatScreenWrap = ChatScreen;
