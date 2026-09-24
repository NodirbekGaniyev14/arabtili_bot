/** Oktagon (K25) — jang WebSocket klienti va server xabarlari.
 *
 *  Brauzer WebSocket'ga sarlavha qo'sha olmaydi — Telegram initData birinchi «auth» xabarida
 *  yuboriladi. Jang o'rtasida ulanish uzilsa (Telegram fonga o'tdi) — o'zi qayta ulanadi, server
 *  joriy holatni qayta yuboradi (matched + q, resume). */

import type { Badge, BattleLeague } from "./api";

export interface BattlePlayer {
  name: string;
  points: number;
  league: BattleLeague;
  bot: boolean;
}

export interface BattleMatched {
  t: "matched";
  match: string;
  level: string;
  you: BattlePlayer;
  opp: BattlePlayer;
  n: number;
  seconds: number;
  start_in: number;
  resume: boolean;
  score: { you: number; opp: number };
}

export interface BattleQuestion {
  t: "q";
  i: number;
  n: number;
  type: "ar_uz" | "uz_ar";
  prompt: string;
  options: string[];
  seconds: number;
  double: boolean;
}

export interface BattleRound {
  t: "round";
  i: number;
  answer: string;
  you: { choice: string | null; ok: boolean; pts: number };
  opp: { ok: boolean; pts: number; answered: boolean };
  score: { you: number; opp: number };
}

export interface BattleEnd {
  t: "end";
  result: "win" | "lose" | "draw";
  reason: "done" | "forfeit";
  score: { you: number; opp: number };
  correct: { you: number; opp: number };
  n: number;
  delta?: number;
  points?: number;
  league?: BattleLeague;
  xp?: number;
  new_badges?: Badge[];
}

export type BattleMsg =
  | { t: "hello"; online: number }
  | { t: "pong"; online: number }
  | { t: "queued"; level: string; wait: number; in_queue: number }
  | { t: "cancelled" }
  | BattleMatched
  | BattleQuestion
  | { t: "opp_answered"; i: number }
  | BattleRound
  | BattleEnd
  | { t: "error"; code?: string; msg: string };

export type BattleOut =
  | { t: "join"; level: string }
  | { t: "cancel" }
  | { t: "answer"; i: number; choice: string }
  | { t: "leave" }
  | { t: "ping" };

export class BattleSocket {
  private ws: WebSocket | null = null;
  private pending: BattleOut[] = [];
  private ping: number | null = null;
  private retries = 0;
  private stopped = false;
  /** Jang davom etyaptimi — uzilsa qayta ulanish kerakmi */
  inMatch = false;

  constructor(
    private onMsg: (m: BattleMsg) => void,
    private onState: (s: "open" | "closed" | "reconnecting") => void
  ) {}

  connect(): void {
    if (this.ws || this.stopped) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/battle`);
    this.ws = ws;
    ws.onopen = () => {
      this.retries = 0;
      ws.send(JSON.stringify({ t: "auth", init: window.Telegram?.WebApp?.initData ?? "" }));
      for (const m of this.pending.splice(0)) ws.send(JSON.stringify(m));
      this.onState("open");
      this.ping = window.setInterval(() => this.send({ t: "ping" }), 20000);
    };
    ws.onmessage = (e) => {
      try {
        this.onMsg(JSON.parse(e.data) as BattleMsg);
      } catch {
        /* buzilgan xabar — e'tiborsiz */
      }
    };
    ws.onclose = () => {
      if (this.ping) window.clearInterval(this.ping);
      this.ping = null;
      this.ws = null;
      if (this.stopped) return;
      // Jang o'rtasida uzildi — qayta ulanamiz (server holatni qayta yuboradi)
      if (this.inMatch && this.retries < 5) {
        this.retries += 1;
        this.onState("reconnecting");
        window.setTimeout(() => this.connect(), 800 * this.retries);
        return;
      }
      this.onState("closed");
    };
  }

  send(m: BattleOut): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(m));
      return;
    }
    if (m.t !== "ping") this.pending.push(m);
    this.connect();
  }

  close(): void {
    this.stopped = true;
    this.ws?.close();
    this.ws = null;
  }
}
