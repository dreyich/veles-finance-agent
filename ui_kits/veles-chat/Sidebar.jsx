const { useState: useSB, useEffect: useSBE, useRef: useSBRef } = React;

// ---- responsive: shared "is mobile" hook ----
const VELES_MQ = window.matchMedia("(max-width: 720px)");
window.velesIsMobile = () => VELES_MQ.matches;
window.useVelesMobile = function useVelesMobile() {
  const [m, setM] = React.useState(VELES_MQ.matches);
  React.useEffect(() => {
    const f = (e) => setM(e.matches);
    if (VELES_MQ.addEventListener) VELES_MQ.addEventListener("change", f);
    else VELES_MQ.addListener(f);
    return () => {
      if (VELES_MQ.removeEventListener) VELES_MQ.removeEventListener("change", f);
      else VELES_MQ.removeListener(f);
    };
  }, []);
  return m;
};

// ---- tiny settings store (localStorage + window event) ----
const VELES_SET_KEY = "veles.settings.v1";
const VELES_SET_DEFAULTS = { enterToSend: true, showRecents: true };
function velesLoadSettings() {
  try { return { ...VELES_SET_DEFAULTS, ...JSON.parse(localStorage.getItem(VELES_SET_KEY) || "{}") }; }
  catch { return { ...VELES_SET_DEFAULTS }; }
}
window.velesSettings = velesLoadSettings();
window.velesUpdateSetting = (key, value) => {
  window.velesSettings = { ...window.velesSettings, [key]: value };
  try { localStorage.setItem(VELES_SET_KEY, JSON.stringify(window.velesSettings)); } catch {}
  window.dispatchEvent(new CustomEvent("veles-settings"));
};

// ---- date grouping for real chats ----
function sbGroupLabel(ts) {
  const d = new Date(ts), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(now) - day(d)) / 86400000);
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 7) return "Previous 7 days";
  return "Older";
}
const SB_ORDER = ["Today", "Yesterday", "Previous 7 days", "Older"];

const sbGhostBtn = {
  width: 30, height: 30, borderRadius: 9, border: "none", cursor: "pointer",
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  color: "var(--ink-2)", background: "transparent",
  transition: "background .2s var(--ease-soft), color .2s var(--ease-soft)",
};

function SbIconBtn({ icon, label, onClick, active }) {
  const [hov, setHov] = useSB(false);
  return (
    <button aria-label={label} title={label} onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ ...sbGhostBtn, background: hov || active ? "rgba(27,36,49,0.07)" : "transparent",
        color: hov || active ? "var(--ink-1)" : "var(--ink-2)" }}>
      <i data-lucide={icon} style={{ width: 15.5, height: 15.5 }}></i>
    </button>
  );
}

function SbMenu({ items, style }) {
  return (
    <div className="v-pop" onClick={(e) => e.stopPropagation()}
      style={{ position: "absolute", zIndex: 40, minWidth: 168, padding: 5,
        background: "rgba(255,255,255,0.92)", backdropFilter: "blur(24px) saturate(1.6)",
        WebkitBackdropFilter: "blur(24px) saturate(1.6)",
        border: "1px solid rgba(255,255,255,0.8)", borderRadius: 13,
        boxShadow: "var(--shadow-pop)", ...style }}>
      {items.map((it, i) => it === "---" ? (
        <div key={i} style={{ height: 1, background: "var(--hair)", margin: "4px 6px" }} />
      ) : (
        <MenuRow key={i} {...it} />
      ))}
    </div>
  );
}
function MenuRow({ icon, label, danger, onClick }) {
  const [hov, setHov] = useSB(false);
  const col = danger ? "#c2453c" : "var(--ink-1)";
  return (
    <button onClick={onClick} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", boxSizing: "border-box",
        padding: "8px 10px", borderRadius: 9, border: "none", cursor: "pointer", textAlign: "left",
        fontSize: 13, fontWeight: 500, color: col,
        background: hov ? (danger ? "rgba(194,69,60,0.09)" : "rgba(27,36,49,0.06)") : "transparent",
        transition: "background .15s" }}>
      <i data-lucide={icon} style={{ width: 14, height: 14, flexShrink: 0 }}></i>
      <span style={{ whiteSpace: "nowrap" }}>{label}</span>
    </button>
  );
}

// ---- settings modal ----
function VToggle({ on, onChange }) {
  return (
    <button role="switch" aria-checked={on} onClick={() => onChange(!on)}
      style={{ width: 40, height: 24, borderRadius: 999, border: "none", cursor: "pointer",
        padding: 2, boxSizing: "border-box", flexShrink: 0,
        background: on ? "#1b2431" : "rgba(27,36,49,0.16)",
        transition: "background .25s var(--ease-soft)" }}>
      <span style={{ display: "block", width: 20, height: 20, borderRadius: 999, background: "#fff",
        boxShadow: "0 1px 3px rgba(21,29,42,0.30)",
        transform: on ? "translateX(16px)" : "translateX(0)",
        transition: "transform .25s var(--ease-soft)" }} />
    </button>
  );
}

function SetRow({ title, desc, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "13px 2px" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13.5, fontWeight: 550, color: "var(--ink-1)" }}>{title}</div>
        {desc && <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 3, lineHeight: 1.5 }}>{desc}</div>}
      </div>
      {children}
    </div>
  );
}

function SetTab({ icon, label, active, onClick, center }) {
  const [hov, setHov] = useSB(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{ display: "flex", alignItems: "center", justifyContent: center ? "center" : "flex-start",
        gap: 7, width: "100%", boxSizing: "border-box",
        padding: "8px 11px", borderRadius: 10, border: "none", cursor: "pointer", textAlign: "left",
        fontSize: 13, fontWeight: active ? 560 : 480,
        color: active ? "var(--ink-1)" : "var(--ink-2)",
        background: active ? "rgba(255,255,255,0.95)" : hov ? "rgba(255,255,255,0.5)" : "transparent",
        boxShadow: active ? "0 1px 2px rgba(31,54,84,0.10), 0 4px 14px rgba(31,54,84,0.07)" : "none",
        transition: "background .2s var(--ease-soft), box-shadow .2s var(--ease-soft), color .2s" }}>
      <i data-lucide={icon} style={{ width: 14.5, height: 14.5, flexShrink: 0, opacity: active ? 0.85 : 0.6 }}></i>
      {label}
    </button>
  );
}

function VelesSettingsModal({ chats, onClearAll, onClose }) {
  const [tab, setTab] = useSB("general");
  const [confirmClear, setConfirmClear] = useSB(false);
  const [, bump] = useSB(0);
  const mobile = window.useVelesMobile();

  useSBE(() => { if (window.lucide) window.lucide.createIcons(); });
  useSBE(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const onSet = () => bump((n) => n + 1);
    window.addEventListener("veles-settings", onSet);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("veles-settings", onSet); };
  }, []);

  const s = window.velesSettings || {};
  const tabs = [
    { id: "general", icon: "sliders-horizontal", label: "General" },
    { id: "data", icon: "database", label: "Data" },
    { id: "about", icon: "info", label: "About" },
  ];
  const titles = { general: "General", data: "Data", about: "About Veles" };

  return ReactDOM.createPortal(
    <div className="v-dim" onClick={onClose} role="dialog" aria-modal="true" aria-label="Settings"
      style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex",
        alignItems: "center", justifyContent: "center", padding: mobile ? 14 : 24,
        background: "rgba(27,36,49,0.28)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)" }}>
      <div className="v-modal" onClick={(e) => e.stopPropagation()}
        style={{ width: 600, maxWidth: "100%",
          height: mobile ? "min(480px, calc(100vh - 28px))" : 420, maxHeight: "calc(100vh - 28px)",
          display: "flex", flexDirection: mobile ? "column" : "row",
          overflow: "hidden", borderRadius: 20, boxSizing: "border-box",
          background: "rgba(255,255,255,0.88)", backdropFilter: "blur(44px) saturate(1.7)",
          WebkitBackdropFilter: "blur(44px) saturate(1.7)",
          border: "1px solid rgba(255,255,255,0.85)",
          boxShadow: "0 30px 80px rgba(31,54,84,0.30), 0 4px 16px rgba(31,54,84,0.12), inset 0 1px 0 rgba(255,255,255,0.95)" }}>

        {/* rail: side column on desktop, top tab-row on mobile */}
        <div style={mobile
          ? { flexShrink: 0, boxSizing: "border-box", padding: "10px 10px 9px",
              display: "flex", flexDirection: "row", gap: 4,
              background: "rgba(27,36,49,0.035)", borderBottom: "1px solid var(--hair)" }
          : { width: 168, flexShrink: 0, boxSizing: "border-box", padding: "16px 10px",
              display: "flex", flexDirection: "column", gap: 3,
              background: "rgba(27,36,49,0.035)", borderRight: "1px solid var(--hair)" }}>
          {!mobile && (
            <div style={{ fontSize: 15, fontWeight: 630, letterSpacing: "-0.015em",
              color: "var(--ink-1)", padding: "2px 11px 12px" }}>Settings</div>
          )}
          {tabs.map((t) => (
            <SetTab key={t.id} {...t} active={tab === t.id} center={mobile}
              onClick={() => { setTab(t.id); setConfirmClear(false); }} />
          ))}
        </div>

        {/* content */}
        <div style={{ flex: 1, minWidth: 0, minHeight: 0, position: "relative", boxSizing: "border-box",
          padding: mobile ? "14px 16px 16px" : "18px 24px 20px", overflowY: "auto" }}>
          <button aria-label="Close settings" onClick={onClose}
            style={{ ...sbGhostBtn, position: "absolute", top: 12, right: 12 }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(27,36,49,0.07)"; e.currentTarget.style.color = "var(--ink-1)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--ink-2)"; }}>
            <i data-lucide="x" style={{ width: 15, height: 15 }}></i>
          </button>
          <div style={{ fontSize: 13.5, fontWeight: 600, letterSpacing: "-0.012em",
            color: "var(--ink-1)", paddingBottom: 6, marginBottom: 4,
            borderBottom: "1px solid var(--hair)" }}>{titles[tab]}</div>

          {tab === "general" && (
            <div className="v-fadeup" style={{ display: "flex", flexDirection: "column" }}>
              <SetRow title="Send with Enter"
                desc="Enter sends the message, Shift+Enter adds a new line. When off, press Ctrl+Enter to send.">
                <VToggle on={s.enterToSend !== false} onChange={(v) => window.velesUpdateSetting("enterToSend", v)} />
              </SetRow>
              <div style={{ height: 1, background: "var(--hair)" }} />
              <SetRow title="Recent chats on home"
                desc="Show your three latest conversations under the composer on the start screen.">
                <VToggle on={s.showRecents !== false} onChange={(v) => window.velesUpdateSetting("showRecents", v)} />
              </SetRow>
            </div>
          )}

          {tab === "data" && (
            <div className="v-fadeup" style={{ display: "flex", flexDirection: "column" }}>
              <SetRow title="Chats on this device"
                desc="Conversations are stored locally in this browser — nothing is uploaded.">
                <span style={{ padding: "4px 11px", borderRadius: 999, fontSize: 12, fontWeight: 550,
                  color: "var(--ink-2)", background: "rgba(27,36,49,0.06)",
                  border: "1px solid rgba(27,36,49,0.06)", whiteSpace: "nowrap" }}>
                  {chats.length} {chats.length === 1 ? "chat" : "chats"}
                </span>
              </SetRow>
              <div style={{ height: 1, background: "var(--hair)" }} />
              <SetRow title="Clear all chats"
                desc="Permanently removes every conversation from this device. This can’t be undone.">
                <button onClick={() => {
                    if (confirmClear) { onClearAll(); setConfirmClear(false); }
                    else setConfirmClear(true);
                  }}
                  disabled={chats.length === 0}
                  style={{ padding: "7px 13px", borderRadius: 10, border: "1px solid rgba(194,69,60,0.25)",
                    cursor: chats.length === 0 ? "default" : "pointer", fontSize: 12.5, fontWeight: 550,
                    whiteSpace: "nowrap", opacity: chats.length === 0 ? 0.45 : 1,
                    color: confirmClear ? "#fff" : "#c2453c",
                    background: confirmClear ? "#c2453c" : "rgba(194,69,60,0.08)",
                    transition: "background .2s var(--ease-soft), color .2s" }}>
                  {confirmClear ? "Click to confirm" : "Clear all"}
                </button>
              </SetRow>
            </div>
          )}

          {tab === "about" && (
            <div className="v-fadeup" style={{ display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 13, padding: "16px 2px 14px" }}>
                <span style={{ width: 42, height: 42, borderRadius: 13, flexShrink: 0,
                  background: "linear-gradient(145deg,#2a3950,#151d2a)",
                  boxShadow: "0 6px 18px rgba(21,29,42,0.32), inset 0 1px 0 rgba(255,255,255,0.18)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  color: "#fff", fontWeight: 650, fontSize: 18 }}>V</span>
                <div>
                  <div style={{ fontSize: 14.5, fontWeight: 620, letterSpacing: "-0.015em", color: "var(--ink-1)" }}>Veles</div>
                  <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>Financial analyst · v2.1.0</div>
                </div>
              </div>
              <div style={{ height: 1, background: "var(--hair)" }} />
              <SetRow title="Model"
                desc="Veles-Finance-7B — fine-tuned for SEC-filing extraction and financial due diligence." />
              <div style={{ height: 1, background: "var(--hair)" }} />
              <SetRow title="Website" desc="News, pricing and documentation.">
                <button onClick={() => window.open("https://velesfin.com", "_blank", "noopener")}
                  style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "7px 13px",
                    borderRadius: 10, border: "1px solid rgba(27,36,49,0.10)", cursor: "pointer",
                    fontSize: 12.5, fontWeight: 550, color: "var(--ink-1)", whiteSpace: "nowrap",
                    background: "rgba(255,255,255,0.75)",
                    boxShadow: "0 1px 2px rgba(31,54,84,0.06)" }}>
                  velesfin.com
                  <i data-lucide="arrow-up-right" style={{ width: 13, height: 13, opacity: 0.6 }}></i>
                </button>
              </SetRow>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}

function SbChatItem({ chat, active, onSelect, onDelete, onRename }) {
  const [hov, setHov] = useSB(false);
  const [menu, setMenu] = useSB(false);
  const [editing, setEditing] = useSB(false);
  const [draft, setDraft] = useSB(chat.title);
  const mobile = window.useVelesMobile();
  const inputRef = useSBRef(null);

  useSBE(() => { if (editing && inputRef.current) { inputRef.current.focus(); inputRef.current.select(); } }, [editing]);
  useSBE(() => {
    if (!menu) return;
    const close = () => setMenu(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [menu]);

  const commit = () => {
    setEditing(false);
    const t = draft.trim();
    if (t && t !== chat.title) onRename(chat.id, t);
    else setDraft(chat.title);
  };

  return (
    <div style={{ position: "relative" }}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}>
      <button onClick={() => !editing && onSelect(chat.id)}
        style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", boxSizing: "border-box",
          textAlign: "left", padding: "8.5px 11px", paddingRight: 34, borderRadius: 11, cursor: "pointer",
          border: "none",
          background: active ? "rgba(255,255,255,0.92)" : hov ? "rgba(255,255,255,0.45)" : "transparent",
          boxShadow: active ? "0 1px 2px rgba(31,54,84,0.10), 0 5px 16px rgba(31,54,84,0.07)" : "none",
          color: active ? "var(--ink-1)" : "var(--ink-2)",
          fontSize: 13, fontWeight: active ? 550 : 450,
          transition: "background .22s var(--ease-soft), box-shadow .22s var(--ease-soft), color .22s" }}>
        <i data-lucide="message-square" style={{ width: 14, height: 14, flexShrink: 0, opacity: active ? 0.75 : 0.5 }}></i>
        {editing ? (
          <input ref={inputRef} value={draft} onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") { setDraft(chat.title); setEditing(false); } }}
            onClick={(e) => e.stopPropagation()}
            style={{ flex: 1, minWidth: 0, border: "none", outline: "none", background: "transparent",
              fontSize: 13, fontWeight: 500, color: "var(--ink-1)", padding: 0 }} />
        ) : (
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{chat.title}</span>
        )}
      </button>
      {(hov || menu || active || mobile) && !editing && (
        <button aria-label="Chat options" title="Rename or delete"
          onClick={(e) => { e.stopPropagation(); setMenu((v) => !v); }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(27,36,49,0.09)"; e.currentTarget.style.color = "var(--ink-1)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = menu ? "rgba(27,36,49,0.09)" : "transparent"; e.currentTarget.style.color = "var(--ink-2)"; }}
          style={{ position: "absolute", right: 5, top: "50%", transform: "translateY(-50%)",
            width: 24, height: 24, borderRadius: 7, border: "none", cursor: "pointer",
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            color: "var(--ink-2)", background: menu ? "rgba(27,36,49,0.09)" : "transparent",
            transition: "background .15s, color .15s" }}>
          <i data-lucide="ellipsis" style={{ width: 15, height: 15 }}></i>
        </button>
      )}
      {menu && (
        <SbMenu style={{ right: 4, top: "calc(100% + 4px)" }} items={[
          { icon: "pencil", label: "Rename", onClick: () => { setMenu(false); setEditing(true); } },
          { icon: "trash-2", label: "Delete chat", danger: true, onClick: () => { setMenu(false); onDelete(chat.id); } },
        ]} />
      )}
    </div>
  );
}

function VelesSidebar({ chats = [], activeId, onSelect, onNew, onDelete, onRename, onClearAll }) {
  const [q, setQ] = useSB("");
  const [searchOn, setSearchOn] = useSB(false);
  const [settings, setSettings] = useSB(false);
  const searchRef = useSBRef(null);

  useSBE(() => { if (window.lucide) window.lucide.createIcons(); });
  useSBE(() => { if (searchOn && searchRef.current) searchRef.current.focus(); }, [searchOn]);

  const filtered = chats.filter((c) => c.title.toLowerCase().includes(q.toLowerCase()));
  const groups = SB_ORDER.map((label) => ({
    label,
    items: filtered.filter((c) => sbGroupLabel(c.ts) === label),
  })).filter((g) => g.items.length);

  return (
    <aside style={{ width: "100%", height: "100%", boxSizing: "border-box",
      display: "flex", flexDirection: "column", gap: 8, padding: "14px 10px 10px",
      background: "rgba(255,255,255,0.34)", backdropFilter: "blur(28px) saturate(1.6)",
      WebkitBackdropFilter: "blur(28px) saturate(1.6)",
      border: "1px solid rgba(255,255,255,0.55)", borderRadius: 18,
      boxShadow: "0 10px 34px rgba(31,54,84,0.10), inset 0 1px 0 rgba(255,255,255,0.7)" }}>

      {/* workspace row */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "0 4px 2px" }}>
        <span style={{ width: 26, height: 26, borderRadius: 8.5, flexShrink: 0,
          background: "linear-gradient(145deg,#2a3950,#151d2a)",
          boxShadow: "0 2px 6px rgba(21,29,42,0.35), inset 0 1px 0 rgba(255,255,255,0.18)",
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          color: "#fff", fontWeight: 650, fontSize: 12.5 }}>V</span>
        <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: "-0.012em" }}>Veles</span>
        <span style={{ flex: 1 }} />
        <SbIconBtn icon="search" label="Search chats" active={searchOn}
          onClick={() => { setSearchOn((v) => !v); setQ(""); }} />
        <SbIconBtn icon="square-pen" label="New chat" onClick={onNew} />
      </div>

      {/* collapsible search */}
      <div style={{ overflow: "hidden", maxHeight: searchOn ? 44 : 0, opacity: searchOn ? 1 : 0,
        transition: "max-height .35s var(--ease-soft), opacity .3s var(--ease-soft)" }}>
        <div style={{ position: "relative", padding: "2px 2px 4px" }}>
          <i data-lucide="search" style={{ width: 13.5, height: 13.5, position: "absolute", left: 13, top: 12,
            color: "var(--ink-3)", pointerEvents: "none" }}></i>
          <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") { setSearchOn(false); setQ(""); } }}
            placeholder="Search chats"
            style={{ width: "100%", boxSizing: "border-box", border: "1px solid rgba(27,36,49,0.10)",
              background: "rgba(255,255,255,0.65)", borderRadius: 10, padding: "8px 10px 8px 32px",
              color: "var(--ink-1)", fontSize: 13, outline: "none" }} />
        </div>
      </div>

      {/* chats list */}
      <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", display: "flex",
        flexDirection: "column", gap: 14, padding: "4px 2px", marginTop: 2 }}>
        {groups.length === 0 && (
          <div style={{ padding: "18px 10px", fontSize: 12.5, color: "var(--ink-3)", textAlign: "center" }}>
            {q ? "No chats match your search." : "No chats yet — start a new one."}
          </div>
        )}
        {groups.map((g) => (
          <div key={g.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ fontSize: 10.5, fontWeight: 550, letterSpacing: "0.07em", textTransform: "uppercase",
              color: "var(--ink-3)", padding: "2px 11px 5px" }}>{g.label}</div>
            {g.items.map((c) => (
              <SbChatItem key={c.id} chat={c} active={c.id === activeId}
                onSelect={onSelect} onDelete={onDelete} onRename={onRename} />
            ))}
          </div>
        ))}
      </div>

      {/* settings */}
      <div style={{ borderTop: "1px solid rgba(27,36,49,0.07)", paddingTop: 8 }}>
        <button onClick={() => setSettings(true)}
          style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", boxSizing: "border-box",
            padding: "8px 11px", borderRadius: 11, cursor: "pointer", border: "none",
            background: settings ? "rgba(255,255,255,0.55)" : "transparent",
            color: "var(--ink-2)", fontSize: 13, fontWeight: 500,
            transition: "background .2s var(--ease-soft)" }}
          onMouseEnter={(e) => { if (!settings) e.currentTarget.style.background = "rgba(255,255,255,0.45)"; }}
          onMouseLeave={(e) => { if (!settings) e.currentTarget.style.background = "transparent"; }}>
          <i data-lucide="settings" style={{ width: 15, height: 15 }}></i> Settings
        </button>
      </div>
      {settings && (
        <VelesSettingsModal chats={chats} onClearAll={onClearAll} onClose={() => setSettings(false)} />
      )}
    </aside>
  );
}
window.VelesSidebar = VelesSidebar;
