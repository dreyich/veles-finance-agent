const { useState: useStateSB } = React;

const sbPanel = {
  width: 272, flexShrink: 0, height: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: 14, padding: "18px 14px",
  background: "rgba(7,7,10,0.66)", backdropFilter: "blur(30px) saturate(150%)",
  WebkitBackdropFilter: "blur(30px) saturate(150%)",
  borderRight: "1px solid rgba(255,255,255,0.06)",
};
const sbSearch = {
  width: "100%", boxSizing: "border-box", border: "1px solid rgba(255,255,255,0.10)",
  background: "rgba(255,255,255,0.05)", borderRadius: 12, padding: "9px 12px 9px 34px",
  color: "var(--text-primary)", fontFamily: "var(--font-sans)", fontSize: 13.5, outline: "none",
};

const SB_SECTIONS = [
  { label: "Today", items: ["Northwind Robotics — DD", "Q3 revenue breakdown"] },
  { label: "Yesterday", items: ["SaaS market sizing", "Helios Energy valuation"] },
  { label: "Last week", items: ["Competitor margins", "Term sheet review", "Cap table analysis"] },
];

function VelesSidebar({ active = "Northwind Robotics — DD", onSelect }) {
  const [q, setQ] = useStateSB("");
  return (
    <aside style={sbPanel}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "2px 6px 6px" }}>
        <span style={{ width: 26, height: 26, borderRadius: 8, padding: 1.5, background: "var(--rainbow)",
          display: "inline-flex" }}>
          <span style={{ width: "100%", height: "100%", borderRadius: 7, background: "#0c0c10",
            display: "inline-flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13 }}>V</span>
        </span>
        <span style={{ fontWeight: 600, fontSize: 15 }}>Veles</span>
      </div>

      <button onClick={() => onSelect && onSelect("__new")}
        style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", boxSizing: "border-box",
          padding: "11px 14px", borderRadius: 12, cursor: "pointer", color: "var(--text-primary)",
          background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.14)",
          fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 500 }}>
        <i data-lucide="plus" style={{ width: 16, height: 16 }}></i> New chat
      </button>

      <div style={{ position: "relative" }}>
        <i data-lucide="search" style={{ width: 15, height: 15, position: "absolute", left: 12, top: 10,
          color: "var(--text-tertiary)" }}></i>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" style={sbSearch} />
      </div>

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16, marginTop: 4 }}>
        {SB_SECTIONS.map((sec) => {
          const items = sec.items.filter((t) => t.toLowerCase().includes(q.toLowerCase()));
          if (!items.length) return null;
          return (
            <div key={sec.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase",
                color: "var(--text-tertiary)", padding: "2px 10px 6px" }}>{sec.label}</div>
              {items.map((t) => {
                const on = t === active;
                return (
                  <button key={t} onClick={() => onSelect && onSelect(t)}
                    style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", boxSizing: "border-box",
                      textAlign: "left", padding: "9px 10px", borderRadius: 9, cursor: "pointer", border: "none",
                      background: on ? "rgba(255,255,255,0.09)" : "transparent",
                      color: on ? "var(--text-primary)" : "var(--text-secondary)",
                      fontFamily: "var(--font-sans)", fontSize: 13.5, whiteSpace: "nowrap", overflow: "hidden",
                      textOverflow: "ellipsis" }}>
                    <i data-lucide="message-square" style={{ width: 14, height: 14, flexShrink: 0, opacity: 0.7 }}></i>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{t}</span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      <button style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", borderRadius: 10,
        cursor: "pointer", border: "none", background: "transparent", color: "var(--text-secondary)",
        fontFamily: "var(--font-sans)", fontSize: 13.5 }}>
        <span style={{ width: 26, height: 26, borderRadius: "50%", background: "rgba(255,255,255,0.10)",
          border: "1px solid rgba(255,255,255,0.14)", display: "inline-flex", alignItems: "center",
          justifyContent: "center", fontSize: 11, fontWeight: 600 }}>JD</span>
        Jordan Davies
      </button>
    </aside>
  );
}
window.VelesSidebar = VelesSidebar;
