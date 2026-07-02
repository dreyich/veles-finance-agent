# Veles Chat — UI Kit

Full-screen recreation of the Veles analyst chat. Dark aurora background, glass message
bubbles, and the floating composer island with an animated rainbow conic-gradient ring
that activates on focus and during the AI thinking state.

## Files
- `index.html` — interactive entry. Type a message, press Enter → user bubble, thinking
  dots, then an AI reply. The composer ring lights up rainbow on focus.
- `Aurora.jsx` — animated drifting mesh-gradient background (`window.Aurora`).
- `ChatScreen.jsx` — header, scroll feed, bubbles, thinking indicator, composer
  (`window.ChatScreenWrap`).

Composes design-system primitives: `Avatar` (with `ai` rainbow mark), `Card` (glass
bubbles), `Badge`. Icons via Lucide CDN.
