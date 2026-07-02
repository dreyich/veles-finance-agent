// Contextual Thinking Visualization — Veles draws a mini-viz matched to the question type.
const { useState: useTV, useEffect: useTVE } = React;

const ACCENT = "#cdb7ff"; // soft lilac — calm, premium
const tvText = { fontFamily: "var(--font-sans)", fontSize: 13.5, color: "var(--text-secondary)",
  letterSpacing: "-0.01em" };

// ---- detect type from the user's prompt ----
function detectType(q = "") {
  const s = q.toLowerCase();
  if (/(valuat|dcf|fair value|worth|оцінк|вартіст)/.test(s)) return "valuation";
  if (/(risk|ризик|exposure|liquidity|credit)/.test(s)) return "risk";
  if (/(market|trend|ринок|price|stock|candle)/.test(s)) return "market";
  return "diligence";
}

const STEPS = {
  diligence: ["Parsing filings…", "Charting revenue…", "Scoring risk exposure…", "Mapping competitors…"],
  risk: ["Market risk…", "Credit risk…", "Liquidity risk…", "Operational risk…"],
  valuation: ["Projecting cash flows…", "Applying discount rate…", "Adding terminal value…", "Deriving fair value…"],
  market: ["Fetching price history…", "Building candles…", "Reading momentum…", "Detecting trend…"],
};

// ===== Viz 1: Due-diligence dashboard =====
function VizDiligence() {
  return (
    <div style={{ display: "flex", gap: 16, alignItems: "stretch" }}>
      <svg width="190" height="92" viewBox="0 0 190 92" style={{ flexShrink: 0 }}>
        <line x1="6" y1="78" x2="184" y2="78" stroke="rgba(255,255,255,0.12)" />
        <polyline className="tv-draw" points="8,70 38,58 64,62 92,40 120,46 150,22 182,14"
          fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {[[8,70],[38,58],[64,62],[92,40],[120,46],[150,22],[182,14]].map(([x,y],i)=>(
          <circle key={i} cx={x} cy={y} r="2.6" fill={ACCENT} className="tv-dot" style={{ animationDelay: `${0.5+i*0.12}s` }} />
        ))}
      </svg>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 5 }}>Risk exposure</div>
          <div style={{ height: 6, borderRadius: 99, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
            <div className="tv-meter" style={{ height: "100%", background: ACCENT, borderRadius: 99 }} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["NW","Hx","Vl","Kr"].map((c,i)=>(
            <span key={c} className="tv-chip" style={{ animationDelay: `${1.4+i*0.18}s`, width: 28, height: 28,
              borderRadius: 8, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.12)",
              display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11,
              color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>{c}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ===== Viz 2: Risk radar =====
function VizRisk() {
  const cx = 95, cy = 70, R = 54;
  const pts = [[0,-1],[0.95,-0.31],[0.59,0.81],[-0.59,0.81],[-0.95,-0.31]];
  const poly = pts.map(([x,y])=>`${cx+x*R*0.78},${cy+y*R*0.78}`).join(" ");
  return (
    <svg width="190" height="140" viewBox="0 0 190 140">
      {[0.4,0.7,1].map((r,gi)=>(
        <polygon key={gi} points={pts.map(([x,y])=>`${cx+x*R*r},${cy+y*R*r}`).join(" ")}
          fill="none" stroke="rgba(255,255,255,0.10)" />
      ))}
      {pts.map(([x,y],i)=>(
        <line key={i} x1={cx} y1={cy} x2={cx+x*R} y2={cy+y*R} stroke="rgba(255,255,255,0.08)" />
      ))}
      <polygon className="tv-radar" points={poly} fill={ACCENT+"33"} stroke={ACCENT} strokeWidth="2" />
      {pts.map(([x,y],i)=>(
        <circle key={i} cx={cx+x*R*0.78} cy={cy+y*R*0.78} r="3" fill={ACCENT} className="tv-dot"
          style={{ animationDelay: `${0.6+i*0.22}s` }} />
      ))}
    </svg>
  );
}

// ===== Viz 3: Valuation DCF table =====
function VizValuation() {
  const rows = [["Yr1","2.1"],["Yr2","2.9"],["Yr3","3.8"],["TV","18.4"]];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 6, width: 200 }}>
      {rows.map(([k,v],i)=>(
        <React.Fragment key={k}>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", display: "flex", alignItems: "center",
            padding: "6px 8px", background: "rgba(255,255,255,0.04)", borderRadius: 7 }}>{k}</div>
          <div className="tv-cell" style={{ animationDelay: `${0.3+i*0.25}s`, fontFamily: "var(--font-mono)",
            fontSize: 14, color: "var(--text-primary)", padding: "6px 8px", background: "rgba(255,255,255,0.06)",
            borderRadius: 7, textAlign: "right" }}>${v}M</div>
        </React.Fragment>
      ))}
    </div>
  );
}

// ===== Viz 4: Market candlesticks =====
function VizMarket() {
  const candles = [[60,18,1],[52,22,0],[58,16,1],[64,20,1],[55,24,0],[68,18,1],[62,26,0],[72,16,1],[78,20,1],[70,22,0],[82,18,1],[90,24,1]];
  return (
    <svg width="220" height="100" viewBox="0 0 220 100">
      {candles.map(([h,wick,up],i)=>{
        const x = 12 + i*16, top = 86-h, col = up ? "#9fe6c4" : "#e6a8a8";
        return (
          <g key={i} className="tv-candle" style={{ animationDelay: `${0.2+i*0.13}s`, transformOrigin: `${x+3}px 86px` }}>
            <line x1={x+3} y1={top-wick/2} x2={x+3} y2={86-h+h+wick/2-h} stroke={col} strokeWidth="1" opacity="0.6" />
            <line x1={x+3} y1={top-6} x2={x+3} y2={top+h*0.0} stroke={col} strokeWidth="1" opacity="0.5" />
            <rect x={x} y={top} width="7" height={h*0.5} rx="1.5" fill={col} />
          </g>
        );
      })}
    </svg>
  );
}

const VIZ = { diligence: VizDiligence, risk: VizRisk, valuation: VizValuation, market: VizMarket };

function VelesThinking({ type = "diligence" }) {
  const steps = STEPS[type] || STEPS.diligence;
  const [idx, setIdx] = useTV(0);
  useTVE(() => {
    const id = setInterval(() => setIdx((i) => (i + 1) % steps.length), 1100);
    return () => clearInterval(id);
  }, [type]);
  useTVE(() => { if (window.lucide) window.lucide.createIcons(); }, [type]);
  const Viz = VIZ[type] || VizDiligence;

  return (
    <div style={{ maxWidth: 460 }}>
      <div style={{ position: "relative", overflow: "hidden", borderRadius: 18, padding: "16px 18px",
        background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.09)",
        backdropFilter: "blur(20px) saturate(160%)", WebkitBackdropFilter: "blur(20px) saturate(160%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.10)" }}>
        <div className="tv-shimmer" aria-hidden="true" />
        <div style={{ minHeight: 92, display: "flex", alignItems: "center" }}><Viz /></div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, paddingLeft: 2 }}>
        <span className="tv-spark"><i data-lucide="sparkles" style={{ width: 14, height: 14, color: ACCENT }}></i></span>
        <span key={idx} className="tv-fadein" style={tvText}>{steps[idx]}</span>
      </div>

      <style>{`
        .tv-draw{stroke-dasharray:420;stroke-dashoffset:420;animation:tvDraw 1.6s var(--ease-soft) forwards}
        @keyframes tvDraw{to{stroke-dashoffset:0}}
        .tv-dot{opacity:0;animation:tvPop .4s var(--ease-soft) forwards}
        @keyframes tvPop{from{opacity:0;transform:scale(0)}to{opacity:1;transform:scale(1)}}
        .tv-meter{width:0;animation:tvMeter 1.6s .6s var(--ease-soft) forwards}
        @keyframes tvMeter{to{width:64%}}
        .tv-chip{opacity:0;animation:tvChip .5s var(--ease-soft) forwards}
        @keyframes tvChip{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
        .tv-radar{opacity:0;transform-origin:center;animation:tvRadar 1.2s .3s var(--ease-soft) forwards}
        @keyframes tvRadar{from{opacity:0;transform:scale(.4)}to{opacity:1;transform:scale(1)}}
        .tv-cell{opacity:0;animation:tvCell .5s var(--ease-soft) forwards}
        @keyframes tvCell{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
        .tv-candle{opacity:0;animation:tvCandle .4s var(--ease-soft) forwards}
        @keyframes tvCandle{from{opacity:0;transform:scaleY(0)}to{opacity:1;transform:scaleY(1)}}
        .tv-fadein{animation:tvFade .45s var(--ease-soft)}
        @keyframes tvFade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
        .tv-spark{display:inline-flex;animation:tvSpin 3s linear infinite}
        @keyframes tvSpin{to{transform:rotate(360deg)}}
        .tv-shimmer{position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(205,183,255,0.10) 50%,transparent 70%);background-size:220% 100%;animation:tvShim 2.4s linear infinite;pointer-events:none}
        @keyframes tvShim{to{background-position:-220% 0}}
      `}</style>
    </div>
  );
}
window.VelesThinking = VelesThinking;
window.velesDetectType = detectType;
