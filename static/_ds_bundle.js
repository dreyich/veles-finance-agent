/* @ds-bundle: {"format":3,"namespace":"VelesDesignSystem_1bfbc8","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"},{"name":"Switch","sourcePath":"components/core/Switch.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"3104e486d22a","components/core/Badge.jsx":"eb855b408140","components/core/Button.jsx":"59143eb9bb30","components/core/Card.jsx":"3ca489ca2bac","components/core/IconButton.jsx":"e1b989a01a30","components/core/Input.jsx":"1299f3066aba","components/core/Switch.jsx":"0cf6e21eaa69","ui_kits/veles-chat/Aurora.jsx":"21944581d9bb","ui_kits/veles-chat/ChatScreen.jsx":"f96687576164","ui_kits/veles-chat/RightPanel.jsx":"bcbc3dfb86ce","ui_kits/veles-chat/Sidebar.jsx":"392d39d7083a","ui_kits/veles-chat/ThinkingViz.jsx":"398c74526d4d"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.VelesDesignSystem_1bfbc8 = window.VelesDesignSystem_1bfbc8 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
/** Round avatar. Pass `src`, or `label` for initials, or `ai` for the rainbow analyst mark. */
function Avatar({
  src,
  label = "",
  ai = false,
  size = 36,
  style = {}
}) {
  const base = {
    width: size,
    height: size,
    borderRadius: "999px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-sans)",
    fontWeight: 600,
    fontSize: size * 0.4,
    color: "var(--text-primary)",
    flexShrink: 0,
    overflow: "hidden",
    ...style
  };
  if (ai) {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        ...base,
        padding: "2px",
        background: "var(--rainbow)",
        boxShadow: "var(--shadow-glow)"
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        width: "100%",
        height: "100%",
        borderRadius: "999px",
        background: "rgba(10,10,15,0.92)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: size * 0.42
      }
    }, "V"));
  }
  if (src) return /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: label,
    style: {
      ...base,
      objectFit: "cover"
    }
  });
  return /*#__PURE__*/React.createElement("span", {
    style: {
      ...base,
      background: "rgba(255,255,255,0.10)",
      border: "1px solid rgba(255,255,255,0.14)"
    }
  }, label.slice(0, 2).toUpperCase());
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Small status / category label. */
function Badge({
  children,
  tone = "neutral",
  style = {},
  ...rest
}) {
  const tones = {
    neutral: {
      color: "var(--text-secondary)",
      border: "rgba(255,255,255,0.16)",
      bg: "rgba(255,255,255,0.05)"
    },
    success: {
      color: "#4dff9b",
      border: "rgba(77,255,155,0.35)",
      bg: "rgba(77,255,155,0.10)"
    },
    info: {
      color: "#3da5ff",
      border: "rgba(61,165,255,0.35)",
      bg: "rgba(61,165,255,0.10)"
    },
    warning: {
      color: "#ffc24d",
      border: "rgba(255,194,77,0.35)",
      bg: "rgba(255,194,77,0.10)"
    },
    danger: {
      color: "#ff5d6c",
      border: "rgba(255,93,108,0.35)",
      bg: "rgba(255,93,108,0.10)"
    }
  };
  const t = tones[tone] || tones.neutral;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: "6px",
      fontFamily: "var(--font-sans)",
      fontSize: "12px",
      fontWeight: 500,
      lineHeight: 1,
      padding: "5px 10px",
      borderRadius: "999px",
      color: t.color,
      background: t.bg,
      border: `1px solid ${t.border}`,
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Veles primary action. Glass by default; `rainbow` variant gets the animated
 * conic-gradient ring for key moments.
 */
function Button({
  children,
  variant = "primary",
  size = "md",
  disabled = false,
  icon = null,
  style = {},
  ...rest
}) {
  const sizes = {
    sm: {
      padding: "8px 14px",
      fontSize: "13px",
      radius: "10px"
    },
    md: {
      padding: "11px 20px",
      fontSize: "15px",
      radius: "12px"
    },
    lg: {
      padding: "15px 28px",
      fontSize: "17px",
      radius: "14px"
    }
  };
  const s = sizes[size] || sizes.md;
  const base = {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    fontFamily: "var(--font-sans)",
    fontWeight: 500,
    lineHeight: 1,
    padding: s.padding,
    fontSize: s.fontSize,
    borderRadius: s.radius,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.4 : 1,
    transition: "all var(--dur-fast) var(--ease-soft)",
    border: "1px solid transparent",
    color: "var(--text-primary)",
    whiteSpace: "nowrap"
  };
  const variants = {
    primary: {
      background: "rgba(255,255,255,0.10)",
      border: "1px solid rgba(255,255,255,0.18)",
      backdropFilter: "blur(16px)",
      WebkitBackdropFilter: "blur(16px)"
    },
    secondary: {
      background: "rgba(255,255,255,0.05)",
      border: "1px solid rgba(255,255,255,0.10)",
      backdropFilter: "blur(16px)",
      WebkitBackdropFilter: "blur(16px)",
      color: "var(--text-secondary)"
    },
    ghost: {
      background: "transparent",
      color: "var(--text-secondary)"
    },
    rainbow: {
      background: "rgba(20,20,30,0.7)",
      backgroundImage: "linear-gradient(rgba(20,20,30,0.85),rgba(20,20,30,0.85)), var(--rainbow)",
      backgroundOrigin: "border-box",
      backgroundClip: "padding-box, border-box",
      border: "1.5px solid transparent",
      boxShadow: "var(--shadow-glow)"
    }
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    disabled: disabled,
    style: {
      ...base,
      ...(variants[variant] || variants.primary),
      ...style
    }
  }, rest), icon, children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Glassmorphism container — the base surface for everything in Veles. */
function Card({
  children,
  padding = "20px",
  glow = false,
  style = {},
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: "linear-gradient(180deg, rgba(255,255,255,0.09), rgba(255,255,255,0.035))",
      backdropFilter: "blur(22px) saturate(180%)",
      WebkitBackdropFilter: "blur(22px) saturate(180%)",
      border: "1px solid rgba(255,255,255,0.12)",
      borderRadius: "20px",
      boxShadow: glow ? "var(--shadow-card), var(--shadow-glow), inset 0 1px 0 rgba(255,255,255,0.18)" : "var(--shadow-card), inset 0 1px 0 rgba(255,255,255,0.16)",
      padding,
      color: "var(--text-primary)",
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/** Circular glass icon button. Pass a Lucide icon element as children. */
function IconButton({
  children,
  size = 40,
  active = false,
  style = {},
  ...rest
}) {
  return /*#__PURE__*/React.createElement("button", _extends({
    style: {
      width: size,
      height: size,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "999px",
      cursor: "pointer",
      color: active ? "var(--text-primary)" : "var(--text-secondary)",
      background: active ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.05)",
      border: "1px solid rgba(255,255,255,0.10)",
      backdropFilter: "blur(16px)",
      WebkitBackdropFilter: "blur(16px)",
      transition: "all var(--dur-fast) var(--ease-soft)",
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const {
  useState
} = React;
/**
 * Glass input. On focus, an animated rainbow conic-gradient ring activates.
 */
function Input({
  value,
  onChange,
  placeholder = "",
  multiline = false,
  style = {},
  ...rest
}) {
  const [focused, setFocused] = useState(false);
  const wrap = {
    position: "relative",
    borderRadius: "16px",
    padding: "1.5px",
    background: focused ? "var(--rainbow)" : "rgba(255,255,255,0.10)",
    transition: "background var(--dur-med) var(--ease-soft)",
    boxShadow: focused ? "var(--shadow-glow)" : "none"
  };
  const field = {
    width: "100%",
    boxSizing: "border-box",
    fontFamily: "var(--font-sans)",
    fontSize: "15px",
    color: "var(--text-primary)",
    background: "rgba(20,20,30,0.75)",
    backdropFilter: "blur(20px)",
    WebkitBackdropFilter: "blur(20px)",
    border: "none",
    outline: "none",
    borderRadius: "15px",
    padding: "13px 16px",
    resize: "none",
    lineHeight: 1.5,
    ...style
  };
  const common = {
    value,
    onChange,
    placeholder,
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
    style: field,
    ...rest
  };
  return /*#__PURE__*/React.createElement("div", {
    style: wrap
  }, multiline ? /*#__PURE__*/React.createElement("textarea", _extends({
    rows: 3
  }, common)) : /*#__PURE__*/React.createElement("input", common));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// components/core/Switch.jsx
try { (() => {
/** Toggle switch. */
function Switch({
  checked = false,
  onChange,
  style = {}
}) {
  return /*#__PURE__*/React.createElement("button", {
    role: "switch",
    "aria-checked": checked,
    onClick: () => onChange && onChange(!checked),
    style: {
      width: 44,
      height: 26,
      borderRadius: "999px",
      border: "1px solid rgba(255,255,255,0.14)",
      background: checked ? "var(--rainbow)" : "rgba(255,255,255,0.08)",
      position: "relative",
      cursor: "pointer",
      transition: "background var(--dur-med) var(--ease-soft)",
      padding: 0,
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 2,
      left: checked ? 20 : 2,
      width: 20,
      height: 20,
      borderRadius: "999px",
      background: "#fff",
      transition: "left var(--dur-med) var(--ease-soft)"
    }
  }));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Switch.jsx", error: String((e && e.message) || e) }); }

// ui_kits/veles-chat/Aurora.jsx
try { (() => {
window.Aurora = function Aurora() {
  return /*#__PURE__*/React.createElement("div", {
    "aria-hidden": "true",
    style: {
      position: "absolute",
      inset: 0,
      overflow: "hidden",
      zIndex: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "veles-aurora veles-a1"
  }), /*#__PURE__*/React.createElement("div", {
    className: "veles-aurora veles-a2"
  }), /*#__PURE__*/React.createElement("div", {
    className: "veles-aurora veles-a3"
  }), /*#__PURE__*/React.createElement("style", null, `
        .veles-aurora{position:absolute;border-radius:50%;filter:blur(80px);opacity:.55;mix-blend-mode:screen}
        .veles-a1{width:60vw;height:60vw;background:#12082a;top:-10%;left:-5%;animation:veles-drift1 70s ease-in-out infinite}
        .veles-a2{width:55vw;height:55vw;background:#071a2e;bottom:-15%;right:-5%;animation:veles-drift2 80s ease-in-out infinite}
        .veles-a3{width:40vw;height:40vw;background:#1a0a3a;top:30%;left:35%;animation:veles-drift3 90s ease-in-out infinite}
        @keyframes veles-drift1{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(15%,12%) scale(1.2)}}
        @keyframes veles-drift2{0%,100%{transform:translate(0,0) scale(1.1)}50%{transform:translate(-12%,-10%) scale(1)}}
        @keyframes veles-drift3{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-18%,15%) scale(1.3)}}
      `));
};
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/veles-chat/Aurora.jsx", error: String((e && e.message) || e) }); }

// ui_kits/veles-chat/ChatScreen.jsx
try { (() => {
const {
  useState,
  useRef,
  useEffect
} = React;
function Composer({
  onSend,
  thinking
}) {
  const [val, setVal] = useState("");
  const [focused, setFocused] = useState(false);
  const send = () => {
    if (val.trim()) {
      onSend(val.trim());
      setVal("");
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      padding: thinking ? "2px" : "1px",
      borderRadius: "26px",
      background: thinking ? "conic-gradient(from var(--rainbow-angle), rgba(255,255,255,0.10) 0deg, rgba(255,255,255,0.10) 210deg, #3da5ff 250deg, #8a4dff 285deg, #ff2d9b 315deg, #ff8a3d 345deg, rgba(255,255,255,0.10) 360deg)" : focused ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.10)",
      boxShadow: thinking ? "var(--shadow-island), 0 0 26px rgba(138,77,255,0.22)" : "var(--shadow-island)",
      transition: "padding var(--dur-med) var(--ease-soft)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      overflow: "hidden",
      background: thinking ? "rgba(14,14,20,0.86)" : "rgba(36,38,48,0.42)",
      backdropFilter: "blur(40px) saturate(200%) brightness(1.12)",
      WebkitBackdropFilter: "blur(40px) saturate(200%) brightness(1.12)",
      borderRadius: "24px",
      padding: "16px 18px",
      boxShadow: "inset 0 1.5px 0.5px rgba(255,255,255,0.45), inset 0 0 0 0.5px rgba(255,255,255,0.10), inset 0 -10px 22px rgba(0,0,0,0.35)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    "aria-hidden": "true",
    style: {
      position: "absolute",
      inset: 0,
      borderRadius: "24px",
      pointerEvents: "none",
      background: "linear-gradient(150deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.04) 22%, rgba(255,255,255,0) 45%)"
    }
  }), /*#__PURE__*/React.createElement("textarea", {
    value: val,
    rows: 1,
    onChange: e => setVal(e.target.value),
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
    onKeyDown: e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    },
    placeholder: "Ask follow up\u2026",
    style: {
      width: "100%",
      border: "none",
      outline: "none",
      resize: "none",
      background: "transparent",
      color: "var(--text-primary)",
      fontFamily: "var(--font-sans)",
      fontSize: "16px",
      lineHeight: 1.5
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      marginTop: "12px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("button", {
    style: pillBtn
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "paperclip",
    style: {
      width: 16,
      height: 16
    }
  }), " Attach report"), /*#__PURE__*/React.createElement("button", {
    style: {
      ...pillBtn,
      padding: 9,
      borderRadius: "999px"
    },
    "aria-label": "Voice input"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "mic",
    style: {
      width: 16,
      height: 16
    }
  }))), /*#__PURE__*/React.createElement("button", {
    onClick: send,
    style: {
      width: 44,
      height: 44,
      borderRadius: "999px",
      border: "none",
      cursor: "pointer",
      background: "#fff",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": thinking ? "square" : "arrow-up",
    style: {
      width: 18,
      height: 18,
      color: "#0a0a0f"
    }
  })))));
}
const pillBtn = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "9px 16px",
  borderRadius: "999px",
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.05)",
  color: "var(--text-secondary)",
  fontFamily: "var(--font-sans)",
  fontSize: "14px",
  cursor: "pointer"
};
function Bubble({
  role,
  children
}) {
  const {
    Avatar,
    Card
  } = window.VelesDesignSystem_1bfbc8;
  const ai = role === "ai";
  const text = /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: "15px",
      lineHeight: 1.6,
      color: "var(--text-primary)",
      fontFamily: ai ? "'Inter', sans-serif" : "var(--font-sans)",
      letterSpacing: ai ? "-0.011em" : "normal"
    }
  }, children);
  if (ai) {
    return /*#__PURE__*/React.createElement("div", {
      style: {
        maxWidth: "84%"
      }
    }, text);
  }
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: "14px",
      alignItems: "flex-start",
      flexDirection: "row-reverse"
    }
  }, /*#__PURE__*/React.createElement(Avatar, {
    label: "JD",
    size: 34
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: "76%"
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: "14px 18px",
    style: {
      borderRadius: "20px 6px 20px 20px",
      background: "rgba(255,255,255,0.09)"
    }
  }, text)));
}
function Thinking() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      gap: "5px",
      alignItems: "center"
    }
  }, [0, 1, 2].map(i => /*#__PURE__*/React.createElement("span", {
    key: i,
    style: {
      width: 7,
      height: 7,
      borderRadius: "50%",
      background: "#fff",
      opacity: 0.85,
      animation: `veles-pulse 1.2s ${i * 0.18}s ease-in-out infinite`
    }
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 8,
      color: "var(--text-tertiary)",
      fontSize: 13
    }
  }, "Analyzing\u2026")), /*#__PURE__*/React.createElement("style", null, `@keyframes veles-pulse{0%,100%{opacity:.25;transform:translateY(0)}50%{opacity:1;transform:translateY(-3px)}}`));
}
const STARTER = [{
  role: "user",
  text: "Run due diligence on Northwind Robotics — focus on revenue and risks."
}, {
  role: "ai",
  text: "Analyzed 3 years of filings. Revenue is growing (CAGR 34%), but customer concentration is high: top-2 = 58% of revenue. Key metrics below."
}];
function ChatScreen() {
  const {
    Badge
  } = window.VelesDesignSystem_1bfbc8;
  const [msgs, setMsgs] = useState(STARTER);
  const [thinking, setThinking] = useState(false);
  const [thinkType, setThinkType] = useState("diligence");
  const [title, setTitle] = useState("Northwind Robotics — DD");
  const [sbOpen, setSbOpen] = useState(true);
  const [rpOpen, setRpOpen] = useState(true);
  const scrollRef = useRef(null);
  useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  });
  useEffect(() => {
    const sc = scrollRef.current;
    if (!sc) return;
    sc.scrollTop = sc.scrollHeight;
    const t = setTimeout(() => {
      sc.scrollTop = sc.scrollHeight;
    }, 120);
    return () => clearTimeout(t);
  }, [msgs, thinking, thinkType]);
  const send = text => {
    setMsgs(m => [...m, {
      role: "user",
      text
    }]);
    setThinkType(window.velesDetectType ? window.velesDetectType(text) : "diligence");
    setThinking(true);
    setTimeout(() => {
      setThinking(false);
      setMsgs(m => [...m, {
        role: "ai",
        text: "Preparing an expanded analysis for your request — building a competitor comparison and a risk assessment."
      }]);
    }, 4800);
  };
  const select = t => {
    if (t === "__new") {
      setMsgs([]);
      setTitle("New chat");
    } else setTitle(t);
  };
  const iconBtn = {
    width: 38,
    height: 38,
    borderRadius: "50%",
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    color: "var(--text-secondary)",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.10)"
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      zIndex: 1,
      height: "100%",
      display: "flex"
    }
  }, sbOpen && /*#__PURE__*/React.createElement(window.VelesSidebar, {
    active: title,
    onSelect: select
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      height: "100%"
    }
  }, /*#__PURE__*/React.createElement("header", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "16px 28px",
      borderBottom: "1px solid rgba(255,255,255,0.07)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("button", {
    style: iconBtn,
    "aria-label": "Toggle chats",
    onClick: () => setSbOpen(v => !v)
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": sbOpen ? "panel-left-close" : "panel-left-open",
    style: {
      width: 16,
      height: 16
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 600,
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--text-tertiary)"
    }
  }, "Financial analyst \xB7 Due diligence"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: "neutral"
  }, "Pro"), /*#__PURE__*/React.createElement("button", {
    style: iconBtn,
    "aria-label": "Share"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "share-2",
    style: {
      width: 16,
      height: 16
    }
  })), /*#__PURE__*/React.createElement("button", {
    style: iconBtn,
    "aria-label": "Model settings"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "sliders-horizontal",
    style: {
      width: 16,
      height: 16
    }
  })), /*#__PURE__*/React.createElement("button", {
    style: iconBtn,
    "aria-label": "Toggle analysis panel",
    onClick: () => setRpOpen(v => !v)
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": rpOpen ? "panel-right-close" : "panel-right-open",
    style: {
      width: 16,
      height: 16
    }
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minHeight: 0,
      display: "flex",
      flexDirection: "column",
      maxWidth: 760,
      margin: "0 auto",
      width: "100%",
      padding: "0 24px",
      boxSizing: "border-box"
    }
  }, /*#__PURE__*/React.createElement("div", {
    ref: scrollRef,
    style: {
      flex: 1,
      overflowY: "auto",
      display: "flex",
      flexDirection: "column",
      gap: 18,
      padding: "24px 0 20px"
    }
  }, msgs.map((m, i) => /*#__PURE__*/React.createElement(Bubble, {
    key: i,
    role: m.role === "ai" ? "ai" : "user"
  }, m.text)), thinking && /*#__PURE__*/React.createElement(window.VelesThinking, {
    type: thinkType
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      paddingBottom: 24
    }
  }, /*#__PURE__*/React.createElement(Composer, {
    onSend: send,
    thinking: thinking
  })))), rpOpen && /*#__PURE__*/React.createElement(window.VelesRightPanel, null));
}
window.ChatScreenWrap = ChatScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/veles-chat/ChatScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/veles-chat/RightPanel.jsx
try { (() => {
const rpPanel = {
  width: 320,
  flexShrink: 0,
  height: "100%",
  boxSizing: "border-box",
  display: "flex",
  flexDirection: "column",
  gap: 20,
  padding: "20px 18px",
  overflowY: "auto",
  background: "rgba(7,7,10,0.66)",
  backdropFilter: "blur(30px) saturate(150%)",
  WebkitBackdropFilter: "blur(30px) saturate(150%)",
  borderLeft: "1px solid rgba(255,255,255,0.06)"
};
const rpHead = {
  fontSize: 11,
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  color: "var(--text-tertiary)",
  marginBottom: 10
};
const rpTile = {
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 12,
  padding: "12px 14px"
};
const SOURCES = [{
  name: "Northwind_10-K_2025.pdf",
  meta: "PDF · 84 pages"
}, {
  name: "Q3_Financials.xlsx",
  meta: "Excel · 12 sheets"
}, {
  name: "Customer_Contracts.pdf",
  meta: "PDF · 31 pages"
}];
const METRICS = [{
  k: "Revenue (TTM)",
  v: "$23.8M",
  d: "+34%",
  up: true
}, {
  k: "Gross margin",
  v: "61%",
  d: "+4pp",
  up: true
}, {
  k: "Customer concentration",
  v: "58%",
  d: "top-2",
  up: false
}, {
  k: "Net burn / mo",
  v: "$420K",
  d: "−12%",
  up: true
}];
function VelesRightPanel() {
  const {
    Badge
  } = window.VelesDesignSystem_1bfbc8;
  return /*#__PURE__*/React.createElement("aside", {
    style: rpPanel
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: rpHead
  }, "Sources analyzed"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, SOURCES.map(s => /*#__PURE__*/React.createElement("div", {
    key: s.name,
    style: {
      ...rpTile,
      display: "flex",
      alignItems: "center",
      gap: 11
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 32,
      height: 32,
      borderRadius: 8,
      flexShrink: 0,
      background: "rgba(255,255,255,0.07)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      color: "var(--text-secondary)"
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": s.name.endsWith("xlsx") ? "sheet" : "file-text",
    style: {
      width: 16,
      height: 16
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 500,
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis"
    }
  }, s.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11.5,
      color: "var(--text-tertiary)"
    }
  }, s.meta)))))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: rpHead
  }, "Key metrics extracted"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 8
    }
  }, METRICS.map(m => /*#__PURE__*/React.createElement("div", {
    key: m.k,
    style: {
      ...rpTile,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between"
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--text-secondary)"
    }
  }, m.k), /*#__PURE__*/React.createElement("div", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: 19,
      fontWeight: 500,
      marginTop: 2
    }
  }, m.v)), /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--font-mono)",
      fontSize: 12,
      padding: "3px 8px",
      borderRadius: 999,
      color: "var(--text-secondary)",
      background: "rgba(255,255,255,0.07)"
    }
  }, m.d))))), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: rpHead
  }, "Export"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 8
    }
  }, [["file-down", "PDF"], ["sheet", "Excel"]].map(([ic, lbl]) => /*#__PURE__*/React.createElement("button", {
    key: lbl,
    style: {
      flex: 1,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 8,
      padding: "10px 0",
      borderRadius: 11,
      cursor: "pointer",
      color: "var(--text-primary)",
      background: "rgba(255,255,255,0.06)",
      border: "1px solid rgba(255,255,255,0.12)",
      fontFamily: "var(--font-sans)",
      fontSize: 13.5,
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": ic,
    style: {
      width: 15,
      height: 15
    }
  }), " ", lbl)))));
}
window.VelesRightPanel = VelesRightPanel;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/veles-chat/RightPanel.jsx", error: String((e && e.message) || e) }); }

// ui_kits/veles-chat/Sidebar.jsx
try { (() => {
const {
  useState: useStateSB
} = React;
const sbPanel = {
  width: 272,
  flexShrink: 0,
  height: "100%",
  boxSizing: "border-box",
  display: "flex",
  flexDirection: "column",
  gap: 14,
  padding: "18px 14px",
  background: "rgba(7,7,10,0.66)",
  backdropFilter: "blur(30px) saturate(150%)",
  WebkitBackdropFilter: "blur(30px) saturate(150%)",
  borderRight: "1px solid rgba(255,255,255,0.06)"
};
const sbSearch = {
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid rgba(255,255,255,0.10)",
  background: "rgba(255,255,255,0.05)",
  borderRadius: 12,
  padding: "9px 12px 9px 34px",
  color: "var(--text-primary)",
  fontFamily: "var(--font-sans)",
  fontSize: 13.5,
  outline: "none"
};
const SB_SECTIONS = [{
  label: "Today",
  items: ["Northwind Robotics — DD", "Q3 revenue breakdown"]
}, {
  label: "Yesterday",
  items: ["SaaS market sizing", "Helios Energy valuation"]
}, {
  label: "Last week",
  items: ["Competitor margins", "Term sheet review", "Cap table analysis"]
}];
function VelesSidebar({
  active = "Northwind Robotics — DD",
  onSelect
}) {
  const [q, setQ] = useStateSB("");
  return /*#__PURE__*/React.createElement("aside", {
    style: sbPanel
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "2px 6px 6px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 26,
      height: 26,
      borderRadius: 8,
      padding: 1.5,
      background: "var(--rainbow)",
      display: "inline-flex"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: "100%",
      height: "100%",
      borderRadius: 7,
      background: "#0c0c10",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontWeight: 700,
      fontSize: 13
    }
  }, "V")), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      fontSize: 15
    }
  }, "Veles")), /*#__PURE__*/React.createElement("button", {
    onClick: () => onSelect && onSelect("__new"),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 9,
      width: "100%",
      boxSizing: "border-box",
      padding: "11px 14px",
      borderRadius: 12,
      cursor: "pointer",
      color: "var(--text-primary)",
      background: "rgba(255,255,255,0.10)",
      border: "1px solid rgba(255,255,255,0.14)",
      fontFamily: "var(--font-sans)",
      fontSize: 14,
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "plus",
    style: {
      width: 16,
      height: 16
    }
  }), " New chat"), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative"
    }
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "search",
    style: {
      width: 15,
      height: 15,
      position: "absolute",
      left: 12,
      top: 10,
      color: "var(--text-tertiary)"
    }
  }), /*#__PURE__*/React.createElement("input", {
    value: q,
    onChange: e => setQ(e.target.value),
    placeholder: "Search chats",
    style: sbSearch
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: "auto",
      display: "flex",
      flexDirection: "column",
      gap: 16,
      marginTop: 4
    }
  }, SB_SECTIONS.map(sec => {
    const items = sec.items.filter(t => t.toLowerCase().includes(q.toLowerCase()));
    if (!items.length) return null;
    return /*#__PURE__*/React.createElement("div", {
      key: sec.label,
      style: {
        display: "flex",
        flexDirection: "column",
        gap: 2
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 11,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: "var(--text-tertiary)",
        padding: "2px 10px 6px"
      }
    }, sec.label), items.map(t => {
      const on = t === active;
      return /*#__PURE__*/React.createElement("button", {
        key: t,
        onClick: () => onSelect && onSelect(t),
        style: {
          display: "flex",
          alignItems: "center",
          gap: 9,
          width: "100%",
          boxSizing: "border-box",
          textAlign: "left",
          padding: "9px 10px",
          borderRadius: 9,
          cursor: "pointer",
          border: "none",
          background: on ? "rgba(255,255,255,0.09)" : "transparent",
          color: on ? "var(--text-primary)" : "var(--text-secondary)",
          fontFamily: "var(--font-sans)",
          fontSize: 13.5,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis"
        }
      }, /*#__PURE__*/React.createElement("i", {
        "data-lucide": "message-square",
        style: {
          width: 14,
          height: 14,
          flexShrink: 0,
          opacity: 0.7
        }
      }), /*#__PURE__*/React.createElement("span", {
        style: {
          overflow: "hidden",
          textOverflow: "ellipsis"
        }
      }, t));
    }));
  })), /*#__PURE__*/React.createElement("button", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "8px 10px",
      borderRadius: 10,
      cursor: "pointer",
      border: "none",
      background: "transparent",
      color: "var(--text-secondary)",
      fontFamily: "var(--font-sans)",
      fontSize: 13.5
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 26,
      height: 26,
      borderRadius: "50%",
      background: "rgba(255,255,255,0.10)",
      border: "1px solid rgba(255,255,255,0.14)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 11,
      fontWeight: 600
    }
  }, "JD"), "Jordan Davies"));
}
window.VelesSidebar = VelesSidebar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/veles-chat/Sidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/veles-chat/ThinkingViz.jsx
try { (() => {
// Contextual Thinking Visualization — Veles draws a mini-viz matched to the question type.
const {
  useState: useTV,
  useEffect: useTVE
} = React;
const ACCENT = "#cdb7ff"; // soft lilac — calm, premium
const tvText = {
  fontFamily: "var(--font-sans)",
  fontSize: 13.5,
  color: "var(--text-secondary)",
  letterSpacing: "-0.01em"
};

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
  market: ["Fetching price history…", "Building candles…", "Reading momentum…", "Detecting trend…"]
};

// ===== Viz 1: Due-diligence dashboard =====
function VizDiligence() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 16,
      alignItems: "stretch"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "190",
    height: "92",
    viewBox: "0 0 190 92",
    style: {
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("line", {
    x1: "6",
    y1: "78",
    x2: "184",
    y2: "78",
    stroke: "rgba(255,255,255,0.12)"
  }), /*#__PURE__*/React.createElement("polyline", {
    className: "tv-draw",
    points: "8,70 38,58 64,62 92,40 120,46 150,22 182,14",
    fill: "none",
    stroke: ACCENT,
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round"
  }), [[8, 70], [38, 58], [64, 62], [92, 40], [120, 46], [150, 22], [182, 14]].map(([x, y], i) => /*#__PURE__*/React.createElement("circle", {
    key: i,
    cx: x,
    cy: y,
    r: "2.6",
    fill: ACCENT,
    className: "tv-dot",
    style: {
      animationDelay: `${0.5 + i * 0.12}s`
    }
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      display: "flex",
      flexDirection: "column",
      justifyContent: "center",
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: "var(--text-tertiary)",
      marginBottom: 5
    }
  }, "Risk exposure"), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 6,
      borderRadius: 99,
      background: "rgba(255,255,255,0.08)",
      overflow: "hidden"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "tv-meter",
    style: {
      height: "100%",
      background: ACCENT,
      borderRadius: 99
    }
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      gap: 6
    }
  }, ["NW", "Hx", "Vl", "Kr"].map((c, i) => /*#__PURE__*/React.createElement("span", {
    key: c,
    className: "tv-chip",
    style: {
      animationDelay: `${1.4 + i * 0.18}s`,
      width: 28,
      height: 28,
      borderRadius: 8,
      background: "rgba(255,255,255,0.07)",
      border: "1px solid rgba(255,255,255,0.12)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 11,
      color: "var(--text-secondary)",
      fontFamily: "var(--font-mono)"
    }
  }, c)))));
}

// ===== Viz 2: Risk radar =====
function VizRisk() {
  const cx = 95,
    cy = 70,
    R = 54;
  const pts = [[0, -1], [0.95, -0.31], [0.59, 0.81], [-0.59, 0.81], [-0.95, -0.31]];
  const poly = pts.map(([x, y]) => `${cx + x * R * 0.78},${cy + y * R * 0.78}`).join(" ");
  return /*#__PURE__*/React.createElement("svg", {
    width: "190",
    height: "140",
    viewBox: "0 0 190 140"
  }, [0.4, 0.7, 1].map((r, gi) => /*#__PURE__*/React.createElement("polygon", {
    key: gi,
    points: pts.map(([x, y]) => `${cx + x * R * r},${cy + y * R * r}`).join(" "),
    fill: "none",
    stroke: "rgba(255,255,255,0.10)"
  })), pts.map(([x, y], i) => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: cx,
    y1: cy,
    x2: cx + x * R,
    y2: cy + y * R,
    stroke: "rgba(255,255,255,0.08)"
  })), /*#__PURE__*/React.createElement("polygon", {
    className: "tv-radar",
    points: poly,
    fill: ACCENT + "33",
    stroke: ACCENT,
    strokeWidth: "2"
  }), pts.map(([x, y], i) => /*#__PURE__*/React.createElement("circle", {
    key: i,
    cx: cx + x * R * 0.78,
    cy: cy + y * R * 0.78,
    r: "3",
    fill: ACCENT,
    className: "tv-dot",
    style: {
      animationDelay: `${0.6 + i * 0.22}s`
    }
  })));
}

// ===== Viz 3: Valuation DCF table =====
function VizValuation() {
  const rows = [["Yr1", "2.1"], ["Yr2", "2.9"], ["Yr3", "3.8"], ["TV", "18.4"]];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "grid",
      gridTemplateColumns: "repeat(2, 1fr)",
      gap: 6,
      width: 200
    }
  }, rows.map(([k, v], i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: k
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: "var(--text-tertiary)",
      display: "flex",
      alignItems: "center",
      padding: "6px 8px",
      background: "rgba(255,255,255,0.04)",
      borderRadius: 7
    }
  }, k), /*#__PURE__*/React.createElement("div", {
    className: "tv-cell",
    style: {
      animationDelay: `${0.3 + i * 0.25}s`,
      fontFamily: "var(--font-mono)",
      fontSize: 14,
      color: "var(--text-primary)",
      padding: "6px 8px",
      background: "rgba(255,255,255,0.06)",
      borderRadius: 7,
      textAlign: "right"
    }
  }, "$", v, "M"))));
}

// ===== Viz 4: Market candlesticks =====
function VizMarket() {
  const candles = [[60, 18, 1], [52, 22, 0], [58, 16, 1], [64, 20, 1], [55, 24, 0], [68, 18, 1], [62, 26, 0], [72, 16, 1], [78, 20, 1], [70, 22, 0], [82, 18, 1], [90, 24, 1]];
  return /*#__PURE__*/React.createElement("svg", {
    width: "220",
    height: "100",
    viewBox: "0 0 220 100"
  }, candles.map(([h, wick, up], i) => {
    const x = 12 + i * 16,
      top = 86 - h,
      col = up ? "#9fe6c4" : "#e6a8a8";
    return /*#__PURE__*/React.createElement("g", {
      key: i,
      className: "tv-candle",
      style: {
        animationDelay: `${0.2 + i * 0.13}s`,
        transformOrigin: `${x + 3}px 86px`
      }
    }, /*#__PURE__*/React.createElement("line", {
      x1: x + 3,
      y1: top - wick / 2,
      x2: x + 3,
      y2: 86 - h + h + wick / 2 - h,
      stroke: col,
      strokeWidth: "1",
      opacity: "0.6"
    }), /*#__PURE__*/React.createElement("line", {
      x1: x + 3,
      y1: top - 6,
      x2: x + 3,
      y2: top + h * 0.0,
      stroke: col,
      strokeWidth: "1",
      opacity: "0.5"
    }), /*#__PURE__*/React.createElement("rect", {
      x: x,
      y: top,
      width: "7",
      height: h * 0.5,
      rx: "1.5",
      fill: col
    }));
  }));
}
const VIZ = {
  diligence: VizDiligence,
  risk: VizRisk,
  valuation: VizValuation,
  market: VizMarket
};
function VelesThinking({
  type = "diligence"
}) {
  const steps = STEPS[type] || STEPS.diligence;
  const [idx, setIdx] = useTV(0);
  useTVE(() => {
    const id = setInterval(() => setIdx(i => (i + 1) % steps.length), 1100);
    return () => clearInterval(id);
  }, [type]);
  useTVE(() => {
    if (window.lucide) window.lucide.createIcons();
  }, [type]);
  const Viz = VIZ[type] || VizDiligence;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 460
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      overflow: "hidden",
      borderRadius: 18,
      padding: "16px 18px",
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.09)",
      backdropFilter: "blur(20px) saturate(160%)",
      WebkitBackdropFilter: "blur(20px) saturate(160%)",
      boxShadow: "inset 0 1px 0 rgba(255,255,255,0.10)"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "tv-shimmer",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: 92,
      display: "flex",
      alignItems: "center"
    }
  }, /*#__PURE__*/React.createElement(Viz, null))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      marginTop: 10,
      paddingLeft: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "tv-spark"
  }, /*#__PURE__*/React.createElement("i", {
    "data-lucide": "sparkles",
    style: {
      width: 14,
      height: 14,
      color: ACCENT
    }
  })), /*#__PURE__*/React.createElement("span", {
    key: idx,
    className: "tv-fadein",
    style: tvText
  }, steps[idx])), /*#__PURE__*/React.createElement("style", null, `
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
      `));
}
window.VelesThinking = VelesThinking;
window.velesDetectType = detectType;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/veles-chat/ThinkingViz.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Switch = __ds_scope.Switch;

})();
