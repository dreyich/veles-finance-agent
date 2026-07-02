const rpPanel = {
  width: 320, flexShrink: 0, height: "100%", boxSizing: "border-box",
  display: "flex", flexDirection: "column", gap: 20, padding: "20px 18px",
  overflowY: "auto",
  background: "rgba(7,7,10,0.66)", backdropFilter: "blur(30px) saturate(150%)",
  WebkitBackdropFilter: "blur(30px) saturate(150%)",
  borderLeft: "1px solid rgba(255,255,255,0.06)",
};
const rpHead = { fontSize: 11, letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--text-tertiary)", marginBottom: 10 };
const rpTile = { background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 12, padding: "12px 14px" };

const SOURCES = [
  { name: "Northwind_10-K_2025.pdf", meta: "PDF · 84 pages" },
  { name: "Q3_Financials.xlsx", meta: "Excel · 12 sheets" },
  { name: "Customer_Contracts.pdf", meta: "PDF · 31 pages" },
];
const METRICS = [
  { k: "Revenue (TTM)", v: "$23.8M", d: "+34%", up: true },
  { k: "Gross margin", v: "61%", d: "+4pp", up: true },
  { k: "Customer concentration", v: "58%", d: "top-2", up: false },
  { k: "Net burn / mo", v: "$420K", d: "−12%", up: true },
];

function VelesRightPanel() {
  const { Badge } = window.VelesDesignSystem_1bfbc8;
  return (
    <aside style={rpPanel}>
      <div>
        <div style={rpHead}>Sources analyzed</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {SOURCES.map((s) => (
            <div key={s.name} style={{ ...rpTile, display: "flex", alignItems: "center", gap: 11 }}>
              <span style={{ width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                background: "rgba(255,255,255,0.07)",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                color: "var(--text-secondary)" }}>
                <i data-lucide={s.name.endsWith("xlsx") ? "sheet" : "file-text"} style={{ width: 16, height: 16 }}></i>
              </span>
              <div style={{ overflow: "hidden" }}>
                <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden",
                  textOverflow: "ellipsis" }}>{s.name}</div>
                <div style={{ fontSize: 11.5, color: "var(--text-tertiary)" }}>{s.meta}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={rpHead}>Key metrics extracted</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {METRICS.map((m) => (
            <div key={m.k} style={{ ...rpTile, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{m.k}</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 19, fontWeight: 500, marginTop: 2 }}>{m.v}</div>
              </div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, padding: "3px 8px", borderRadius: 999,
                color: "var(--text-secondary)", background: "rgba(255,255,255,0.07)" }}>{m.d}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={rpHead}>Export</div>
        <div style={{ display: "flex", gap: 8 }}>
          {[["file-down", "PDF"], ["sheet", "Excel"]].map(([ic, lbl]) => (
            <button key={lbl} style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
              gap: 8, padding: "10px 0", borderRadius: 11, cursor: "pointer", color: "var(--text-primary)",
              background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
              fontFamily: "var(--font-sans)", fontSize: 13.5, fontWeight: 500 }}>
              <i data-lucide={ic} style={{ width: 15, height: 15 }}></i> {lbl}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
window.VelesRightPanel = VelesRightPanel;
