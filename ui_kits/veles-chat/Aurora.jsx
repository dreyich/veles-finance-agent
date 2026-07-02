window.Aurora = function Aurora() {
  return (
    <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", zIndex: 0 }}>
      <div className="veles-aurora veles-a1" />
      <div className="veles-aurora veles-a2" />
      <div className="veles-aurora veles-a3" />
      <style>{`
        .veles-aurora{position:absolute;border-radius:50%;filter:blur(80px);opacity:.55;mix-blend-mode:screen}
        .veles-a1{width:60vw;height:60vw;background:#12082a;top:-10%;left:-5%;animation:veles-drift1 70s ease-in-out infinite}
        .veles-a2{width:55vw;height:55vw;background:#071a2e;bottom:-15%;right:-5%;animation:veles-drift2 80s ease-in-out infinite}
        .veles-a3{width:40vw;height:40vw;background:#1a0a3a;top:30%;left:35%;animation:veles-drift3 90s ease-in-out infinite}
        @keyframes veles-drift1{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(15%,12%) scale(1.2)}}
        @keyframes veles-drift2{0%,100%{transform:translate(0,0) scale(1.1)}50%{transform:translate(-12%,-10%) scale(1)}}
        @keyframes veles-drift3{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(-18%,15%) scale(1.3)}}
      `}</style>
    </div>
  );
};
