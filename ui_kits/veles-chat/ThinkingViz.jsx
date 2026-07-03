// Thinking indicator — shimmering step text matched to the question type. No card, no icons.
const { useState: useTV, useEffect: useTVE } = React;

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
  risk: ["Assessing market risk…", "Weighing credit risk…", "Checking liquidity…", "Scanning operations…"],
  valuation: ["Projecting cash flows…", "Applying discount rate…", "Adding terminal value…", "Deriving fair value…"],
  market: ["Fetching price history…", "Reading momentum…", "Comparing benchmarks…", "Detecting trend…"],
};

function VelesThinking({ type = "diligence" }) {
  const steps = STEPS[type] || STEPS.diligence;
  const [idx, setIdx] = useTV(0);
  useTVE(() => {
    setIdx(0);
    const id = setInterval(() => setIdx((i) => (i + 1) % steps.length), 1600);
    return () => clearInterval(id);
  }, [type]);

  return (
    <div style={{ paddingLeft: 38, minHeight: 22, display: "flex", alignItems: "center" }}>
      <span key={idx} className="tv-step" style={{ fontSize: 14.5, fontWeight: 480, letterSpacing: "-0.01em" }}>
        {steps[idx]}
      </span>
      <style>{`
        .tv-step{
          background:linear-gradient(90deg,
            rgba(27,36,49,0.30) 0%, rgba(27,36,49,0.30) 38%,
            rgba(27,36,49,0.95) 50%,
            rgba(27,36,49,0.30) 62%, rgba(27,36,49,0.30) 100%);
          background-size:200% 100%;
          -webkit-background-clip:text;background-clip:text;
          color:transparent;
          animation:tvSheen 2s linear infinite, tvStepIn .45s var(--ease-soft);
        }
        @keyframes tvSheen{from{background-position:200% 0}to{background-position:-200% 0}}
        @keyframes tvStepIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
      `}</style>
    </div>
  );
}
window.VelesThinking = VelesThinking;
window.velesDetectType = detectType;
