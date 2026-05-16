import { useEffect, useRef, useState } from "react";

const STORAGE_KEY = "qr-terminal-height";
const TTYD_URL = "http://localhost:7681";
const MIN_HEIGHT = 120;
const HANDLE_HEIGHT = 6;

interface Props {
  visible: boolean;
  onClose: () => void;
}

function loadHeight(): number {
  if (typeof window === "undefined") return 320;
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved) {
    const n = Number(saved);
    if (Number.isFinite(n) && n >= MIN_HEIGHT) return n;
  }
  return Math.floor(window.innerHeight / 3);
}

export function TerminalPanel({ visible, onClose }: Props) {
  const [height, setHeight] = useState(loadHeight);
  const dragging = useRef(false);

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (!dragging.current) return;
      const max = window.innerHeight - 80;
      const newH = Math.max(MIN_HEIGHT, Math.min(max, window.innerHeight - e.clientY));
      setHeight(newH);
    }
    function onUp() {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.localStorage.setItem(STORAGE_KEY, String(height));
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
  }, [height]);

  if (!visible) return null;

  return (
    <div
      style={{ height }}
      className="shrink-0 border-t border-border bg-panel relative flex flex-col"
    >
      <div
        onMouseDown={() => {
          dragging.current = true;
          document.body.style.cursor = "ns-resize";
          document.body.style.userSelect = "none";
        }}
        style={{ height: HANDLE_HEIGHT }}
        className="cursor-ns-resize hover:bg-accent transition flex items-center justify-center shrink-0"
        title="Drag to resize"
      >
        <div className="h-0.5 w-12 rounded bg-border" />
      </div>
      <div className="flex justify-between items-center px-3 py-1 text-xs border-b border-border shrink-0">
        <span className="font-medium">Claude Code terminal</span>
        <div className="flex gap-3 text-muted">
          <a href={TTYD_URL} target="_blank" rel="noreferrer" className="hover:text-text">
            open in new tab ↗
          </a>
          <button type="button" onClick={onClose} className="hover:text-text">
            close ✕
          </button>
        </div>
      </div>
      <iframe
        src={TTYD_URL}
        title="Claude Code"
        className="flex-1 w-full border-0"
      />
    </div>
  );
}
