// WebSocket-driven hooks. The dashboard receives live data over WebSocket
// (server push) rather than polling — the terminal tails logs, the header
// streams runtime status.

import { useEffect, useRef, useState } from "react";
import { type LogRecord, type Status, wsUrl } from "./api/client";

const MAX_LOG_LINES = 1000;

export function useTerminal(): { lines: LogRecord[]; connected: boolean } {
  const [lines, setLines] = useState<LogRecord[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket(wsUrl("/ws/terminal"));
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as { type: string; records: LogRecord[] };
        setLines((prev) => {
          const next =
            msg.type === "snapshot" ? msg.records : [...prev, ...msg.records];
          return next.slice(-MAX_LOG_LINES);
        });
      };
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, []);

  return { lines, connected };
}

export function useLiveStatus(): Status | null {
  const [status, setStatus] = useState<Status | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const ws = new WebSocket(wsUrl("/ws/status"));
      wsRef.current = ws;
      ws.onmessage = (ev) => setStatus(JSON.parse(ev.data) as Status);
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, []);

  return status;
}
