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

// Serverless GPU worker cold starts take 10-30s+ (model download + SGLang
// boot) before the first token comes back. Without this, the analytical
// steps above cycle forever and look identical to a normal fast response —
// the user has no way to tell "still thinking" from "actually stuck", which
// is what made a slow-but-working cold start look like a hang. Past this
// threshold, tell them what's actually happening instead of pretending it's
// analysis.
const WARMUP_THRESHOLD_MS = 7000;
const WARMUP_STEPS = [
  "Waking up the model on the server…",
  "Cold start — this is rare, but happens…",
  "Almost there, model is nearly ready…",
];

function VelesThinking({ type = "diligence" }) {
  const steps = STEPS[type] || STEPS.diligence;
  const [idx, setIdx] = useTV(0);
  const [warmingUp, setWarmingUp] = useTV(false);
  useTVE(() => {
    setIdx(0);
    setWarmingUp(false);
    const id = setInterval(() => setIdx((i) => (i + 1) % steps.length), 1600);
    const warmupTimer = setTimeout(() => setWarmingUp(true), WARMUP_THRESHOLD_MS);
    return () => { clearInterval(id); clearTimeout(warmupTimer); };
  }, [type]);

  const activeSteps = warmingUp ? WARMUP_STEPS : steps;
  const activeIdx = idx % activeSteps.length;

  return (
    <div style={{ paddingLeft: 38, minHeight: 22, display: "flex", alignItems: "center" }}>
      <span key={`${warmingUp}-${activeIdx}`} className="tv-step" style={{ fontSize: 14.5, fontWeight: 480, letterSpacing: "-0.01em" }}>
        {activeSteps[activeIdx]}
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
