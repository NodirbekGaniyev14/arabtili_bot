/** Oktagon (K25) — 1v1 lug'at jangi.
 *
 *  Lobbi (liga, ball, janglar; onlayn soni, eng zo'rlari, janglarim) → qidiruv (daraja navbati)
 *  → VS → 10 savol × 10 s (ikkalasiga bir xil, tez + to'g'ri = ko'p ball, oxirgisi ×2) → natija
 *  (ball, XP). Jang serverda boshqariladi (lib/battle.ts).
 *
 *  Odam topilmasa server o'zbekcha ismli sun'iy raqib qo'yadi — UI buni HECH QAYERDA ko'rsatmaydi
 *  («bot» so'zi, 🤖 belgisi yo'q; foydalanuvchi qarori, K25.4). Klient farqni bilmaydi ham. */

import { useEffect, useRef, useState } from "react";
import {
  api,
  type Badge,
  type BattleHistoryItem,
  type BattleMe,
  type BattleSeasonData,
  type BattleTopItem,
} from "../lib/api";
import {
  BattleSocket,
  type BattleEnd,
  type BattleMatched,
  type BattleMsg,
  type BattleQuestion,
  type BattleRoom,
  type BattleRound,
} from "../lib/battle";
import BadgeToast from "../components/BadgeToast";

const tg = () => window.Telegram?.WebApp;
const haptic = {
  tap: () => tg()?.HapticFeedback?.impactOccurred("light"),
  hit: () => tg()?.HapticFeedback?.impactOccurred("medium"),
  ok: () => tg()?.HapticFeedback?.notificationOccurred("success"),
  bad: () => tg()?.HapticFeedback?.notificationOccurred("error"),
};

type Stage = "lobby" | "search" | "room" | "vs" | "play" | "end";

function leftLabel(hours: number): string {
  if (hours >= 48) return `${Math.round(hours / 24)} kun qoldi`;
  return `${hours} soat qoldi`;
}

/** `#duel=KOD` — bot xabaridagi «Jangga kirish» tugmasi (K25.2). */
function readDuelCode(): string {
  const m = window.location.hash.match(/^#duel=([A-Za-z0-9]{4,12})$/);
  return m ? m[1].toUpperCase() : "";
}

function clearHash() {
  try {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  } catch {
    /* eski WebView */
  }
}

export default function Battle({ onClose }: { onClose: () => void }) {
  const [me, setMe] = useState<BattleMe | null>(null);
  const [online, setOnline] = useState(0);
  const [level, setLevel] = useState("");
  const [stage, setStage] = useState<Stage>("lobby");
  const [searchSince, setSearchSince] = useState(0);
  const [matched, setMatched] = useState<BattleMatched | null>(null);
  const [q, setQ] = useState<BattleQuestion | null>(null);
  const [qAt, setQAt] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [oppAnswered, setOppAnswered] = useState(false);
  const [round, setRound] = useState<BattleRound | null>(null);
  const [history, setHistory] = useState<boolean[]>([]);
  const [score, setScore] = useState({ you: 0, opp: 0 });
  const [end, setEnd] = useState<BattleEnd | null>(null);
  const [badges, setBadges] = useState<Badge[]>([]);
  const [error, setError] = useState("");
  const [conn, setConn] = useState<"open" | "closed" | "reconnecting">("closed");
  const [sheet, setSheet] = useState<"top" | "history" | "week" | null>(null);
  const [room, setRoom] = useState<BattleRoom | null>(null);
  const [roomAt, setRoomAt] = useState(0);
  const [offer, setOffer] = useState<{ code: string; from: string; level: string; until: number } | null>(null);
  const [info, setInfo] = useState("");
  const sock = useRef<BattleSocket | null>(null);
  const qRef = useRef<BattleQuestion | null>(null);
  // Ref — dev StrictMode effektni ikki marta ishlatganda ham kod yo'qolmasin
  const duelCode = useRef(readDuelCode());

  const loadMe = () =>
    api
      .battleMe()
      .then((m) => {
        setMe(m);
        setOnline(m.online);
        setLevel((l) => l || m.level);
      })
      .catch(() => setError("Yuklanmadi — internetni tekshiring"));

  useEffect(() => {
    loadMe();
    const s = new BattleSocket(onMsg, setConn);
    sock.current = s;
    s.connect();
    if (duelCode.current) {
      s.send({ t: "room_join", code: duelCode.current });
      clearHash();
    }
    return () => s.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onMsg(m: BattleMsg) {
    switch (m.t) {
      case "hello":
      case "pong":
        setOnline(m.online);
        break;
      case "queued":
        setStage("search");
        setSearchSince(Date.now());
        break;
      case "cancelled":
        setStage("lobby");
        break;
      case "room":
        setRoom(m);
        setRoomAt(Date.now());
        setOffer(null);
        setStage("room");
        break;
      case "room_closed":
        setRoom(null);
        if (!m.self) setInfo(m.msg);
        setStage((s) => (s === "room" ? "lobby" : s));
        break;
      case "rematch_offer":
        setOffer({ code: m.code, from: m.from, level: m.level, until: Date.now() + m.expires_in * 1000 });
        haptic.hit();
        break;
      case "matched":
        if (sock.current) sock.current.inMatch = true;
        setRoom(null);
        setOffer(null);
        setInfo("");
        setMatched(m);
        setScore(m.score);
        setEnd(null);
        if (!m.resume) {
          setHistory([]);
          setQ(null);
          qRef.current = null;
          setRound(null);
          setStage("vs");
          haptic.hit();
        } else {
          setStage("play");
        }
        break;
      case "q":
        qRef.current = m;
        setQ(m);
        setQAt(performance.now());
        setPicked(null);
        setOppAnswered(false);
        setRound(null);
        setStage("play");
        break;
      case "opp_answered":
        if (qRef.current && m.i === qRef.current.i) setOppAnswered(true);
        break;
      case "round":
        setRound(m);
        setScore(m.score);
        setHistory((h) => {
          const next = [...h];
          next[m.i] = m.you.ok;
          return next;
        });
        if (m.you.ok) haptic.ok();
        else haptic.bad();
        break;
      case "end":
        if (sock.current) sock.current.inMatch = false;
        setEnd(m);
        setBadges(m.new_badges ?? []);
        setStage("end");
        if (m.result === "win") haptic.ok();
        loadMe();
        break;
      case "error":
        setError(m.msg);
        if (sock.current) sock.current.inMatch = false;
        setRoom(null);
        setStage("lobby");
        break;
    }
  }

  const start = () => {
    if (!level) return;
    haptic.hit();
    setError("");
    sock.current?.send({ t: "join", level });
  };

  const cancel = () => {
    haptic.tap();
    sock.current?.send({ t: "cancel" });
    setStage("lobby");
  };

  const invite = () => {
    if (!level) return;
    haptic.hit();
    setError("");
    setInfo("");
    sock.current?.send({ t: "room_create", level });
  };

  const cancelRoom = () => {
    haptic.tap();
    sock.current?.send({ t: "room_cancel" });
    setRoom(null);
    setStage("lobby");
  };

  const rematch = () => {
    haptic.hit();
    setError("");
    sock.current?.send({ t: "rematch" });
  };

  const acceptOffer = () => {
    if (!offer) return;
    haptic.hit();
    sock.current?.send({ t: "room_join", code: offer.code });
    setOffer(null);
  };

  const declineOffer = () => {
    if (!offer) return;
    sock.current?.send({ t: "room_decline", code: offer.code });
    setOffer(null);
  };

  const answer = (opt: string) => {
    if (!q || picked !== null || round) return;
    haptic.tap();
    setPicked(opt);
    sock.current?.send({ t: "answer", i: q.i, choice: opt });
  };

  const leave = () => {
    const msg = "Jangni tark etasizmi? Mag'lubiyat hisoblanadi.";
    const t = tg();
    const go = () => sock.current?.send({ t: "leave" });
    if (t?.showConfirm && t.isVersionAtLeast?.("6.2")) t.showConfirm(msg, (ok) => ok && go());
    else if (window.confirm(msg)) go();
  };

  const close = () => {
    if (stage === "play" || stage === "vs") {
      leave();
      return;
    }
    if (stage === "search") sock.current?.send({ t: "cancel" });
    if (stage === "room") sock.current?.send({ t: "room_cancel" });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto overflow-hidden">
      <BadgeToast badges={badges} />
      <div className="flex items-center justify-between px-4 pt-3">
        <button
          onClick={close}
          className="w-9 h-9 rounded-full bg-card border border-cardline text-ink-soft font-extrabold active:scale-95"
          aria-label="Yopish"
        >
          {stage === "play" || stage === "vs" ? "⚑" : "✕"}
        </button>
        {conn !== "open" && (
          <span className="rounded-full bg-gold-soft px-2.5 py-1 text-[11px] font-extrabold text-ink-soft">
            {conn === "reconnecting" ? "Qayta ulanmoqda…" : "Ulanish…"}
          </span>
        )}
        <span className="w-9" />
      </div>

      {stage === "lobby" && (
        <Lobby
          me={me}
          online={online}
          level={level}
          setLevel={setLevel}
          error={error}
          info={info}
          onStart={start}
          onInvite={invite}
          onTop={() => setSheet("top")}
          onHistory={() => setSheet("history")}
          onWeek={() => setSheet("week")}
        />
      )}
      {stage === "search" && <Searching level={level} since={searchSince} onCancel={cancel} />}
      {stage === "room" && room && <RoomView room={room} since={roomAt} onCancel={cancelRoom} />}
      {stage === "vs" && matched && <Versus m={matched} />}
      {stage === "play" && matched && (
        <Play
          m={matched}
          q={q}
          qAt={qAt}
          picked={picked}
          oppAnswered={oppAnswered}
          round={round}
          score={score}
          history={history}
          onAnswer={answer}
        />
      )}
      {stage === "end" && end && matched && (
        <EndView
          e={end}
          m={matched}
          onAgain={() => {
            setEnd(null);
            start();
          }}
          onRematch={rematch}
          onLobby={() => setStage("lobby")}
        />
      )}

      {offer && stage !== "play" && stage !== "vs" && (
        <RematchOffer offer={offer} onAccept={acceptOffer} onDecline={declineOffer} />
      )}

      {sheet && <Sheet kind={sheet} onClose={() => setSheet(null)} />}
    </div>
  );
}

// ───────────────────────── Lobbi ─────────────────────────

function Lobby({
  me,
  online,
  level,
  setLevel,
  error,
  info,
  onStart,
  onInvite,
  onTop,
  onHistory,
  onWeek,
}: {
  me: BattleMe | null;
  online: number;
  level: string;
  setLevel: (l: string) => void;
  error: string;
  info: string;
  onStart: () => void;
  onInvite: () => void;
  onTop: () => void;
  onHistory: () => void;
  onWeek: () => void;
}) {
  const limitReached = !!me && me.daily_limit > 0 && me.today >= me.daily_limit;
  const [season, setSeason] = useState<BattleSeasonData | null>(null);
  useEffect(() => {
    api.battleSeason().then(setSeason).catch(() => setSeason(null));
  }, []);
  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div className="mt-1 flex flex-col items-center text-center">
          <div className="w-24 h-24 rounded-full border-4 border-emerald-deep/25 bg-card flex items-center justify-center text-5xl shadow-sm">
            ⚔️
          </div>
          <h1 className="mt-3 text-[28px] font-extrabold tracking-[0.06em]">OKTAGON</h1>
          <div className="text-[11px] font-extrabold tracking-[0.2em] text-ink-soft">1V1 LUG'AT JANGI</div>
          <div className="font-arabic text-lg text-emerald-deep/80" dir="rtl">
            المُبَارَزَة
          </div>
        </div>

        {/* Ko'rsatkichlar */}
        <div className="mt-4 grid grid-cols-3 rounded-3xl bg-card border border-cardline py-3 text-center shadow-sm">
          <div>
            <div className="text-2xl leading-none">{me?.league.icon ?? "🥉"}</div>
            <div className="mt-1 text-[11px] font-extrabold text-ink-soft">{me?.league.title ?? "Bronza"}</div>
          </div>
          <div className="border-x border-cardline">
            <div className="text-[22px] font-extrabold text-emerald-deep leading-none">{me?.points ?? 0}</div>
            <div className="mt-1 text-[11px] font-extrabold text-ink-soft">ball</div>
          </div>
          <div>
            <div className="text-[22px] font-extrabold leading-none">{me?.games ?? 0}</div>
            <div className="mt-1 text-[11px] font-extrabold text-ink-soft">janglar</div>
          </div>
        </div>
        {me && me.league.next_at > 0 && (
          <div className="mt-1.5 text-center text-[11px] font-semibold text-ink-soft">
            {me.league.next_title} ligasigacha {Math.max(0, me.league.next_at - me.points)} ball
            {me.rank > 0 ? ` · reytingda ${me.rank}-o'rin` : ""}
          </div>
        )}

        {/* Mavsum va haftalik sovrin (K25.3) */}
        {season && (
          <button
            onClick={onWeek}
            className="mt-3 w-full rounded-3xl bg-card border border-cardline p-3.5 text-left shadow-sm active:scale-[0.99] transition-transform"
          >
            <div className="flex items-center gap-3">
              <span
                className="w-11 h-11 shrink-0 rounded-2xl flex items-center justify-center text-2xl text-white"
                style={{ backgroundImage: "linear-gradient(135deg, #e0bf55, #c9a227)" }}
              >
                🏅
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-extrabold leading-tight">HAFTALIK OKTAGON</div>
                <div className="truncate text-[11px] font-semibold text-ink-soft">
                  {season.week.me.rank > 0
                    ? `${season.week.label} · siz ${season.week.me.rank}-o'rin, ${season.week.me.points} ball`
                    : `${season.week.label} · jang qiling — jadvalga tushasiz`}
                </div>
              </div>
              <span className="shrink-0 font-extrabold text-ink-soft">›</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 rounded-2xl bg-gold-soft px-3 py-1.5 text-[11px] font-bold">
              <span className="truncate">
                {season.week.top.length > 0
                  ? `🥇 Yetakchi: ${season.week.top[0].name} — ${season.week.top[0].points} ball`
                  : "🥇 Yetakchi hali yo'q"}
              </span>
              <span className="shrink-0 text-ink-soft">{leftLabel(season.week.hours_left)}</span>
            </div>
            <div className="mt-1.5 text-[11px] font-semibold text-ink-soft">
              🗓 Mavsum: <b>{season.season.label}</b> · {season.season.days_left} kun qoldi
            </div>
          </button>
        )}

        {/* Tugmalar */}
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <div className="relative rounded-2xl bg-emerald-deep text-white p-3.5 shadow-sm">
            <span className="absolute -top-2 right-2 inline-flex items-center gap-1 rounded-full bg-gold px-2 py-0.5 text-[10px] font-extrabold text-white shadow">
              <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> {online}
            </span>
            <div className="text-[13px] font-extrabold leading-tight">ONLAYN</div>
            <div className="text-[11px] font-semibold text-white/75">hozir Oktagonda</div>
          </div>
          <button
            onClick={onTop}
            className="rounded-2xl p-3.5 text-left text-white shadow-sm active:scale-[0.98] transition-transform"
            style={{ backgroundImage: "linear-gradient(135deg, #e0bf55, #c9a227)" }}
          >
            <div className="text-[13px] font-extrabold leading-tight">🏆 ENG ZO'RLARI</div>
            <div className="text-[11px] font-semibold text-white/85">reytingni ko'ring</div>
          </button>
          <button
            onClick={onInvite}
            disabled={!me || !level || limitReached}
            className="rounded-2xl bg-card border-2 border-emerald-deep/40 p-3.5 text-left active:scale-[0.98] transition-transform disabled:opacity-50"
          >
            <div className="text-[13px] font-extrabold leading-tight">👥 DO'STNI CHAQIRISH</div>
            <div className="text-[11px] font-semibold text-ink-soft">havola · {level || "—"} daraja</div>
          </button>
          <button
            onClick={onHistory}
            className="rounded-2xl bg-card border border-cardline p-3.5 text-left active:scale-[0.98] transition-transform"
          >
            <div className="text-[13px] font-extrabold leading-tight">📜 MENING JANGLARIM</div>
            <div className="text-[11px] font-semibold text-ink-soft">
              {me ? `${me.wins} g'alaba / ${me.games} jang` : "tarix"}
            </div>
          </button>
        </div>

        {/* Daraja */}
        <div className="mt-4 text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">DARAJA — SAVOLLAR SHU LUG'ATDAN</div>
        <div className="mt-2 grid grid-cols-5 gap-1.5">
          {(me?.levels ?? ["A0", "A1", "A2", "B1", "B2"]).map((lv) => (
            <button
              key={lv}
              onClick={() => {
                haptic.tap();
                setLevel(lv);
              }}
              className={`rounded-xl py-2.5 text-[14px] font-extrabold border-2 transition-colors ${
                level === lv ? "bg-emerald-deep border-emerald-deep text-white" : "bg-card border-cardline text-ink"
              }`}
            >
              {lv}
            </button>
          ))}
        </div>

        <div className="mt-3 rounded-2xl bg-card border border-cardline px-4 py-3 text-[12px] font-semibold text-ink-soft space-y-1">
          <div>⚡ 10 savol · har biriga 10 soniya · ikkalangizga bir xil</div>
          <div>🎯 To'g'ri va tez = ko'p ball (10–20), oxirgi savol ×2</div>
          <div>👥 Raqib tanlangan daraja bo'yicha topiladi</div>
        </div>

        {error && (
          <div className="mt-3 rounded-2xl bg-terracotta/10 border border-terracotta/30 px-4 py-3 text-sm font-semibold">{error}</div>
        )}
        {info && !error && (
          <div className="mt-3 rounded-2xl bg-gold-soft border border-gold/30 px-4 py-3 text-sm font-semibold">{info}</div>
        )}
      </div>

      <div className="px-4 pt-2 pb-4" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        {me && me.daily_limit > 0 && (
          <div className="mb-1.5 text-center text-[11px] font-bold text-ink-soft">
            Bugun: {me.today}/{me.daily_limit} jang{limitReached ? " — ertaga yana (VIP'da cheksiz)" : ""}
          </div>
        )}
        <button
          onClick={onStart}
          disabled={!me || !level || limitReached}
          className="w-full rounded-2xl bg-emerald-deep py-4 text-[16px] font-extrabold tracking-[0.04em] text-white shadow-lg active:scale-[0.98] transition-transform disabled:opacity-50"
        >
          ⚔️ QIDIRISHNI BOSHLASH
        </button>
      </div>
    </>
  );
}

// ───────────────────────── Qidiruv va VS ─────────────────────────

function Searching({ level, since, onCancel }: { level: string; since: number; onCancel: () => void }) {
  const [sec, setSec] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setSec(Math.floor((Date.now() - since) / 1000)), 250);
    return () => window.clearInterval(t);
  }, [since]);
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
      <div className="relative w-40 h-40 flex items-center justify-center">
        <span className="absolute inset-0 rounded-full bg-emerald-deep/15 animate-ping" />
        <span className="absolute inset-4 rounded-full bg-emerald-deep/20 animate-ping [animation-delay:0.4s]" />
        <span className="relative w-24 h-24 rounded-full bg-emerald-deep text-white flex items-center justify-center text-5xl shadow-lg">
          ⚔️
        </span>
      </div>
      <div className="mt-6 text-xl font-extrabold">Raqib qidirilmoqda…</div>
      <div className="mt-1 text-3xl font-extrabold text-emerald-deep tabular-nums">
        0:{String(sec).padStart(2, "0")}
      </div>
      <div className="mt-2 text-[13px] font-semibold text-ink-soft">
        Daraja {level} · mos raqib izlanmoqda
      </div>
      <button
        onClick={onCancel}
        className="mt-8 rounded-2xl bg-card border border-cardline px-8 py-3 font-extrabold text-ink-soft active:scale-95"
      >
        Bekor qilish
      </button>
    </div>
  );
}

function Avatar({ name, you }: { name: string; you?: boolean }) {
  return (
    <span
      className={`w-20 h-20 rounded-full flex items-center justify-center text-3xl font-extrabold shadow-md border-4 ${
        you ? "bg-emerald-deep text-white border-emerald-deep/30" : "bg-gold text-white border-gold/30"
      }`}
    >
      {(name.trim()[0] || "?").toUpperCase()}
    </span>
  );
}

function Versus({ m }: { m: BattleMatched }) {
  const [left, setLeft] = useState(Math.ceil(m.start_in));
  useEffect(() => {
    const t = window.setInterval(() => setLeft((x) => Math.max(0, x - 1)), 1000);
    return () => window.clearInterval(t);
  }, []);
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6">
      <div className="text-[11px] font-extrabold tracking-[0.2em] text-ink-soft">DARAJA {m.level} · {m.n} SAVOL</div>
      <div className="mt-6 flex items-center justify-center gap-5 w-full">
        <div className="flex-1 flex flex-col items-center text-center min-w-0">
          <Avatar name={m.you.name} you />
          <div className="mt-2 font-extrabold truncate max-w-full">{m.you.name}</div>
          <div className="text-[11px] font-bold text-ink-soft">
            {m.you.league.icon} {m.you.points} ball
          </div>
        </div>
        <div className="text-3xl font-extrabold text-terracotta">VS</div>
        <div className="flex-1 flex flex-col items-center text-center min-w-0">
          <Avatar name={m.opp.name} />
          <div className="mt-2 font-extrabold truncate max-w-full">{m.opp.name}</div>
          <div className="text-[11px] font-bold text-ink-soft">
            {m.opp.league.icon} {m.opp.points} ball
          </div>
        </div>
      </div>
      <div className="mt-10 w-20 h-20 rounded-full bg-emerald-deep text-white flex items-center justify-center text-4xl font-extrabold shadow-lg">
        {left > 0 ? left : "⚔️"}
      </div>
      <div className="mt-3 text-[13px] font-semibold text-ink-soft">Tayyorlaning — tez va to'g'ri!</div>
    </div>
  );
}

// ───────────────────────── Jang ─────────────────────────

function Timer({ q, qAt, stopped, total }: { q: BattleQuestion; qAt: number; stopped: boolean; total: number }) {
  const [left, setLeft] = useState(q.seconds);
  useEffect(() => {
    if (stopped) return;
    let raf = 0;
    const tick = () => {
      const l = Math.max(0, q.seconds - (performance.now() - qAt) / 1000);
      setLeft(l);
      if (l > 0) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [q, qAt, stopped]);
  const R = 26;
  const C = 2 * Math.PI * R;
  const frac = Math.max(0, Math.min(1, left / (total || 10)));
  const color = left > 5 ? "var(--color-emerald-deep)" : left > 2.5 ? "var(--color-gold)" : "var(--color-terracotta)";
  return (
    <div className="relative w-16 h-16">
      <svg viewBox="0 0 64 64" className="w-16 h-16 -rotate-90">
        <circle cx="32" cy="32" r={R} fill="none" stroke="var(--color-cardline)" strokeWidth="6" />
        <circle
          cx="32"
          cy="32"
          r={R}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - frac)}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-lg font-extrabold tabular-nums" style={{ color }}>
        {Math.ceil(left)}
      </span>
    </div>
  );
}

function Play({
  m,
  q,
  qAt,
  picked,
  oppAnswered,
  round,
  score,
  history,
  onAnswer,
}: {
  m: BattleMatched;
  q: BattleQuestion | null;
  qAt: number;
  picked: string | null;
  oppAnswered: boolean;
  round: BattleRound | null;
  score: { you: number; opp: number };
  history: boolean[];
  onAnswer: (o: string) => void;
}) {
  const arabicOptions = q?.type === "uz_ar";
  return (
    <div className="flex-1 flex flex-col px-4 pb-4 min-h-0">
      {/* Hisob */}
      <div className="mt-2 flex items-center gap-2">
        <div className="flex-1 min-w-0 rounded-2xl bg-emerald-deep text-white px-3 py-2">
          <div className="text-[11px] font-bold text-white/75 truncate">Siz</div>
          <div className="text-2xl font-extrabold leading-none tabular-nums">
            {score.you}
            {round && round.you.pts > 0 && <span className="ml-1.5 text-[13px] text-gold-soft">+{round.you.pts}</span>}
          </div>
        </div>
        {q && <Timer q={q} qAt={qAt} stopped={!!round} total={m.seconds} />}
        <div className="flex-1 min-w-0 rounded-2xl bg-gold text-white px-3 py-2 text-right">
          <div className="text-[11px] font-bold text-white/85 truncate">
            {m.opp.name}
            {!round && oppAnswered && " · ✓"}
          </div>
          <div className="text-2xl font-extrabold leading-none tabular-nums">
            {round && round.opp.pts > 0 && <span className="mr-1.5 text-[13px] text-white/85">+{round.opp.pts}</span>}
            {score.opp}
          </div>
        </div>
      </div>

      {/* Savollar yo'li */}
      <div className="mt-3 flex justify-center gap-1.5">
        {Array.from({ length: m.n }, (_, i) => (
          <span
            key={i}
            className={`h-2 flex-1 max-w-6 rounded-full ${
              history[i] === true
                ? "bg-emerald-deep"
                : history[i] === false
                  ? "bg-terracotta"
                  : q && i === q.i
                    ? "bg-gold"
                    : "bg-cardline"
            }`}
          />
        ))}
      </div>

      {!q ? (
        <div className="flex-1 flex items-center justify-center text-ink-soft font-semibold">Savol keladi…</div>
      ) : (
        <>
          <div className="mt-4 rounded-3xl bg-card border border-cardline shadow-sm px-4 py-6 text-center">
            <div className="text-[11px] font-extrabold tracking-[0.16em] text-emerald-deep">
              {q.i + 1}/{q.n} · {q.type === "ar_uz" ? "MA'NOSINI TOPING" : "ARABCHASINI TOPING"}
              {q.double && <span className="ml-1.5 rounded-full bg-terracotta px-1.5 py-0.5 text-white">×2</span>}
            </div>
            {q.type === "ar_uz" ? (
              <div className="mt-3 font-arabic text-[52px] leading-[1.35]" dir="rtl">
                {q.prompt}
              </div>
            ) : (
              <div className="mt-4 text-[26px] font-extrabold leading-tight">{q.prompt}</div>
            )}
          </div>

          <div className={`mt-3 ${arabicOptions ? "grid grid-cols-2 gap-2.5" : "space-y-2.5"}`}>
            {q.options.map((o) => {
              const isRight = round && o === round.answer;
              const isMine = o === picked;
              const state = round
                ? isRight
                  ? "bg-emerald-deep/10 border-emerald-deep text-emerald-dark"
                  : isMine
                    ? "bg-terracotta/10 border-terracotta text-terracotta"
                    : "bg-card border-cardline opacity-55"
                : isMine
                  ? "bg-gold-soft border-gold"
                  : picked
                    ? "bg-card border-cardline opacity-55"
                    : "bg-card border-cardline active:scale-[0.98]";
              return (
                <button
                  key={o}
                  disabled={!!picked || !!round}
                  onClick={() => onAnswer(o)}
                  className={`w-full rounded-2xl border-2 px-4 transition-all ${state} ${
                    arabicOptions ? "py-4 font-arabic text-[26px] leading-snug text-center" : "py-3.5 text-left text-[15px] font-bold"
                  }`}
                  dir={arabicOptions ? "rtl" : undefined}
                >
                  {o}
                </button>
              );
            })}
          </div>

          <div className="mt-3 text-center text-[12px] font-bold text-ink-soft min-h-5">
            {round
              ? round.you.ok
                ? `✓ To'g'ri! +${round.you.pts} · raqib: ${round.opp.ok ? `✓ +${round.opp.pts}` : round.opp.answered ? "✗" : "ulgurmadi"}`
                : `✗ ${round.you.choice ? "Xato" : "Vaqt tugadi"} · raqib: ${round.opp.ok ? `✓ +${round.opp.pts}` : round.opp.answered ? "✗" : "ulgurmadi"}`
              : picked
                ? oppAnswered
                  ? "Raqib ham javob berdi…"
                  : "Raqib javobini kutyapmiz…"
                : oppAnswered
                  ? "⚡ Raqib javob berdi — shoshiling!"
                  : ""}
          </div>
        </>
      )}
    </div>
  );
}

// ───────────────────────── Natija ─────────────────────────

function EndView({
  e,
  m,
  onAgain,
  onRematch,
  onLobby,
}: {
  e: BattleEnd;
  m: BattleMatched;
  onAgain: () => void;
  onRematch: () => void;
  onLobby: () => void;
}) {
  const title = e.result === "win" ? "G'ALABA! 🏆" : e.result === "draw" ? "DURANG 🤝" : "MAG'LUBIYAT";
  const sub =
    e.reason === "forfeit"
      ? e.result === "win"
        ? "Raqib jangni tark etdi"
        : "Siz jangni tark etdingiz"
      : e.result === "win"
        ? "Ajoyib! Lug'atingiz kuchli"
        : e.result === "draw"
          ? "Teng kuch — yana bir jang?"
          : "Hechqisi yo'q — keyingisida yutasiz!";
  const delta = e.delta ?? 0;
  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div
          className={`mt-2 rounded-3xl p-5 text-center text-white shadow-lg ${
            e.result === "win" ? "bg-emerald-deep" : e.result === "draw" ? "bg-gold" : "bg-terracotta"
          }`}
        >
          <div className="text-[26px] font-extrabold">{title}</div>
          <div className="text-[13px] font-semibold text-white/85">{sub}</div>
          <div className="mt-4 flex items-center justify-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-bold text-white/75">Siz</div>
              <div className="text-4xl font-extrabold tabular-nums">{e.score.you}</div>
              <div className="text-[11px] font-bold text-white/75">
                {e.correct.you}/{e.n} to'g'ri
              </div>
            </div>
            <div className="text-xl font-extrabold text-white/70">:</div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] font-bold text-white/75 truncate">
                {m.opp.name}
              </div>
              <div className="text-4xl font-extrabold tabular-nums">{e.score.opp}</div>
              <div className="text-[11px] font-bold text-white/75">
                {e.correct.opp}/{e.n} to'g'ri
              </div>
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2.5">
          <div className="rounded-2xl bg-card border border-cardline p-3.5 text-center">
            <div className={`text-2xl font-extrabold ${delta > 0 ? "text-emerald-deep" : delta < 0 ? "text-terracotta" : "text-ink-soft"}`}>
              {delta > 0 ? `+${delta}` : delta}
            </div>
            <div className="text-[11px] font-bold text-ink-soft">
              ball · jami {e.points ?? "—"} {e.league?.icon ?? ""}
            </div>
          </div>
          <div className="rounded-2xl bg-card border border-cardline p-3.5 text-center">
            <div className="text-2xl font-extrabold text-gold">+{e.xp ?? 0}</div>
            <div className="text-[11px] font-bold text-ink-soft">XP</div>
          </div>
        </div>
        {e.league && (
          <div className="mt-2 text-center text-[12px] font-semibold text-ink-soft">
            {e.league.icon} {e.league.title} ligasi
            {e.league.next_at > 0 && e.points !== undefined ? ` · ${e.league.next_title}gacha ${Math.max(0, e.league.next_at - e.points)} ball` : ""}
          </div>
        )}
      </div>
      <div className="px-4 pt-2 pb-4 space-y-2" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        {e.rematch && (
          <button
            onClick={onRematch}
            className="w-full rounded-2xl bg-gold py-4 text-[16px] font-extrabold text-white shadow-lg active:scale-[0.98]"
          >
            🔁 Qayta jang — {m.opp.name} bilan
          </button>
        )}
        <button
          onClick={onAgain}
          className={
            e.rematch
              ? "w-full rounded-2xl bg-card border-2 border-emerald-deep py-3.5 font-extrabold text-emerald-deep active:scale-[0.98]"
              : "w-full rounded-2xl bg-emerald-deep py-4 text-[16px] font-extrabold text-white shadow-lg active:scale-[0.98]"
          }
        >
          ⚔️ {e.rematch ? "Yangi raqib qidirish" : "Yana jang"}
        </button>
        <button onClick={onLobby} className="w-full rounded-2xl bg-card border border-cardline py-3 font-extrabold text-ink-soft">
          Lobbi
        </button>
      </div>
    </>
  );
}

// ───────────────────────── Do'st xonasi / qayta jang (K25.2) ─────────────────────────

function useCountdown(seconds: number, since: number): number {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.round(seconds - (Date.now() - since) / 1000)));
    tick();
    const t = window.setInterval(tick, 500);
    return () => window.clearInterval(t);
  }, [seconds, since]);
  return left;
}

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function RoomView({ room, since, onCancel }: { room: BattleRoom; since: number; onCancel: () => void }) {
  const left = useCountdown(room.expires_in, since);
  const [copied, setCopied] = useState(false);
  const isHost = room.role === "host";
  const share = () => {
    if (!room.link) return;
    haptic.tap();
    const url = `https://t.me/share/url?url=${encodeURIComponent(room.link)}&text=${encodeURIComponent(room.share_text ?? "")}`;
    const t = tg();
    try {
      if (t?.openTelegramLink) {
        t.openTelegramLink(url);
        return;
      }
    } catch {
      /* eski mijoz */
    }
    window.open(url, "_blank");
  };
  const copy = async () => {
    if (!room.link) return;
    try {
      await navigator.clipboard.writeText(room.link);
      setCopied(true);
      haptic.ok();
    } catch {
      setCopied(false);
    }
  };

  return (
    <>
      <div className="flex-1 overflow-y-auto px-5 pb-4 flex flex-col items-center text-center">
        <div className="relative mt-4 w-32 h-32 flex items-center justify-center">
          <span className="absolute inset-0 rounded-full bg-gold/20 animate-ping" />
          <span className="relative w-24 h-24 rounded-full bg-gold text-white flex items-center justify-center text-5xl shadow-lg">
            {room.mode === "rematch" ? "🔁" : "👥"}
          </span>
        </div>
        {isHost && room.mode === "friend" && (
          <>
            <h2 className="mt-5 text-xl font-extrabold">Do'stingizni jangga chaqiring</h2>
            <p className="mt-1 text-[13px] font-semibold text-ink-soft">
              {room.level} daraja · 10 savol × 10 soniya. Havolani yuboring — do'stingiz ochishi bilan jang boshlanadi.
            </p>
            <div className="mt-4 w-full rounded-2xl bg-card border border-cardline px-3 py-2.5 flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-left font-mono text-[12px] text-ink-soft">{room.link}</span>
              <button onClick={copy} className="shrink-0 rounded-xl bg-cardline px-3 py-1.5 text-[12px] font-extrabold">
                {copied ? "✓ Nusxalandi" : "📋 Nusxalash"}
              </button>
            </div>
            <div className="mt-3 w-full rounded-2xl bg-gold-soft border border-gold/30 px-4 py-3 text-[13px] font-bold">
              {room.guest
                ? room.guest.online
                  ? `⚔️ ${room.guest.name} kirdi — jang boshlanmoqda…`
                  : `${room.guest.name} havolani ochdi, lekin hozir ilovada emas`
                : "⏳ Do'stingiz havolani ochishini kutyapmiz…"}
            </div>
          </>
        )}
        {isHost && room.mode === "rematch" && (
          <>
            <h2 className="mt-5 text-xl font-extrabold">Qayta jang taklifi yuborildi</h2>
            <p className="mt-1 text-[13px] font-semibold text-ink-soft">
              {room.guest?.name ?? "Raqib"} javobini kutyapmiz — qabul qilsa, jang darhol boshlanadi.
            </p>
          </>
        )}
        {!isHost && (
          <>
            <h2 className="mt-5 text-xl font-extrabold">{room.host?.name ?? "Do'stingiz"} bilan jang</h2>
            <p className="mt-1 text-[13px] font-semibold text-ink-soft">
              {room.level} daraja · 10 savol × 10 soniya.
              {room.host?.online ? " Jang boshlanmoqda…" : " Do'stingiz hozir ilovada emas — unga Telegram orqali xabar yubordik. U kirishi bilan jang boshlanadi."}
            </p>
          </>
        )}
        <div className="mt-4 text-3xl font-extrabold text-emerald-deep tabular-nums">{mmss(left)}</div>
        <div className="text-[11px] font-bold text-ink-soft">taklif amal qiladi</div>
      </div>
      <div className="px-4 pt-2 pb-4 space-y-2" style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
        {isHost && room.mode === "friend" && (
          <button
            onClick={share}
            className="w-full rounded-2xl bg-emerald-deep py-4 text-[16px] font-extrabold text-white shadow-lg active:scale-[0.98]"
          >
            📤 Telegram orqali yuborish
          </button>
        )}
        <button onClick={onCancel} className="w-full rounded-2xl bg-card border border-cardline py-3 font-extrabold text-ink-soft">
          Bekor qilish
        </button>
      </div>
    </>
  );
}

function RematchOffer({
  offer,
  onAccept,
  onDecline,
}: {
  offer: { code: string; from: string; level: string; until: number };
  onAccept: () => void;
  onDecline: () => void;
}) {
  const [left, setLeft] = useState(Math.max(0, Math.round((offer.until - Date.now()) / 1000)));
  useEffect(() => {
    const t = window.setInterval(() => {
      const l = Math.max(0, Math.round((offer.until - Date.now()) / 1000));
      setLeft(l);
      if (l === 0) onDecline();
    }, 500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offer.until]);
  return (
    <div className="absolute inset-x-3 top-14 z-20 rounded-3xl bg-card border-2 border-gold shadow-xl p-4">
      <div className="flex items-center gap-3">
        <span className="w-12 h-12 shrink-0 rounded-2xl bg-gold text-white flex items-center justify-center text-2xl">🔁</span>
        <div className="min-w-0 flex-1">
          <div className="font-extrabold truncate">{offer.from} qayta jangga chaqiryapti!</div>
          <div className="text-[12px] font-semibold text-ink-soft">
            {offer.level} daraja · {left} soniya ichida javob bering
          </div>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button onClick={onDecline} className="rounded-2xl bg-cardline py-3 font-extrabold text-ink-soft active:scale-95">
          Rad etish
        </button>
        <button onClick={onAccept} className="rounded-2xl bg-emerald-deep py-3 font-extrabold text-white active:scale-95">
          ⚔️ Qabul qilish
        </button>
      </div>
    </div>
  );
}

// ───────────────────────── Reyting / tarix ─────────────────────────

function Sheet({ kind, onClose }: { kind: "top" | "history" | "week"; onClose: () => void }) {
  const [top, setTop] = useState<{ items: BattleTopItem[]; me: { rank: number; points: number } } | null>(null);
  const [hist, setHist] = useState<BattleHistoryItem[] | null>(null);
  const [season, setSeason] = useState<BattleSeasonData | null>(null);
  useEffect(() => {
    if (kind === "top") api.battleTop().then(setTop).catch(() => setTop({ items: [], me: { rank: 0, points: 0 } }));
    else if (kind === "week") api.battleSeason().then(setSeason).catch(() => setSeason(null));
    else api.battleHistory().then((r) => setHist(r.items)).catch(() => setHist([]));
  }, [kind]);
  return (
    <div className="absolute inset-0 z-10 bg-ink/40 flex items-end" onClick={onClose}>
      <div
        className="w-full max-h-[80%] rounded-t-3xl bg-sand flex flex-col"
        onClick={(ev) => ev.stopPropagation()}
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-2">
          <div className="text-lg font-extrabold">
            {kind === "top" ? "🏆 Eng zo'rlari" : kind === "week" ? "🏅 Haftalik Oktagon" : "📜 Mening janglarim"}
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-full bg-cardline text-ink-soft font-extrabold">
            ✕
          </button>
        </div>
        <div className="overflow-y-auto px-4 pb-4 space-y-2">
          {kind === "top" &&
            (top === null ? (
              <div className="py-8 text-center text-ink-soft font-semibold">Yuklanmoqda…</div>
            ) : top.items.length === 0 ? (
              <div className="py-8 text-center text-ink-soft font-semibold">Hali janglar yo'q — birinchi bo'ling!</div>
            ) : (
              <>
                {top.me.rank > 0 && (
                  <div className="text-center text-[12px] font-bold text-ink-soft">
                    Siz: {top.me.rank}-o'rin · {top.me.points} ball
                  </div>
                )}
                {top.items.map((x) => (
                  <div key={x.user_id} className="flex items-center gap-3 rounded-2xl bg-card border border-cardline px-3.5 py-2.5">
                    <span className="w-7 text-center font-extrabold text-ink-soft">
                      {x.rank <= 3 ? ["🥇", "🥈", "🥉"][x.rank - 1] : x.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="font-extrabold truncate">{x.name}</div>
                      <div className="text-[11px] font-semibold text-ink-soft">
                        {x.league.icon} {x.league.title} · {x.wins}/{x.games} g'alaba
                      </div>
                    </div>
                    <span className="font-extrabold text-emerald-deep tabular-nums">{x.points}</span>
                  </div>
                ))}
              </>
            ))}
          {kind === "week" && <WeekBoard s={season} />}
          {kind === "history" &&
            (hist === null ? (
              <div className="py-8 text-center text-ink-soft font-semibold">Yuklanmoqda…</div>
            ) : hist.length === 0 ? (
              <div className="py-8 text-center text-ink-soft font-semibold">Hali jang qilmagansiz</div>
            ) : (
              hist.map((h) => (
                <div key={h.id} className="flex items-center gap-3 rounded-2xl bg-card border border-cardline px-3.5 py-2.5">
                  <span
                    className={`w-9 h-9 shrink-0 rounded-xl flex items-center justify-center text-sm font-extrabold text-white ${
                      h.result === "win" ? "bg-emerald-deep" : h.result === "draw" ? "bg-gold" : "bg-terracotta"
                    }`}
                  >
                    {h.result === "win" ? "G" : h.result === "draw" ? "D" : "M"}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-extrabold truncate">
                      {h.opp}
                      {h.forfeit ? " · tark etildi" : ""}
                    </div>
                    <div className="text-[11px] font-semibold text-ink-soft">
                      {h.level} · {h.at}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-extrabold tabular-nums">
                      {h.you}:{h.them}
                    </div>
                    <div className={`text-[11px] font-extrabold ${h.delta > 0 ? "text-emerald-deep" : h.delta < 0 ? "text-terracotta" : "text-ink-soft"}`}>
                      {h.delta > 0 ? `+${h.delta}` : h.delta}
                    </div>
                  </div>
                </div>
              ))
            ))}
        </div>
      </div>
    </div>
  );
}

/** K25.3 — haftalik Oktagon jadvali, sovrinlar va mavsum holati. */
function WeekBoard({ s }: { s: BattleSeasonData | null }) {
  if (s === null) return <div className="py-8 text-center font-semibold text-ink-soft">Yuklanmoqda…</div>;
  const enough = s.week.top.length >= s.week.min_players;
  return (
    <>
      <div className="rounded-2xl bg-card border border-cardline px-4 py-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-extrabold">{s.week.label}</span>
          <span className="text-[11px] font-bold text-ink-soft">{leftLabel(s.week.hours_left)}</span>
        </div>
        <div className="mt-1 text-[12px] font-semibold text-ink-soft">
          Ball — shu haftada janglarda to'plangan sof ball (mag'lubiyat minus).
        </div>
        <div className="mt-2 text-[12px] font-semibold text-ink-soft">
          Yakunda top-3 e'lon qilinadi va tarixda qoladi. Sovrin yo'q — faqat sharaf va o'rin 🥇
        </div>
        {!enough && (
          <div className="mt-2 rounded-xl bg-gold-soft px-3 py-1.5 text-[11px] font-bold">
            G'olib e'lon qilinishi uchun haftada kamida {s.week.min_players} jangchi kerak
          </div>
        )}
      </div>

      {s.week.top.length === 0 ? (
        <div className="py-6 text-center font-semibold text-ink-soft">
          Bu hafta hali jang bo'lmadi — birinchi bo'ling!
        </div>
      ) : (
        s.week.top.map((x) => (
          <div key={x.user_id} className="flex items-center gap-3 rounded-2xl bg-card border border-cardline px-3.5 py-2.5">
            <span className="w-7 text-center font-extrabold text-ink-soft">
              {x.rank <= 3 ? ["🥇", "🥈", "🥉"][x.rank - 1] : x.rank}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-extrabold">{x.name}</div>
              <div className="text-[11px] font-semibold text-ink-soft">
                {x.wins}/{x.games} g'alaba
                {enough && x.rank <= 3 ? " · 🏅 g'olib o'rin" : ""}
              </div>
            </div>
            <span
              className={`font-extrabold tabular-nums ${
                x.points > 0 ? "text-emerald-deep" : x.points < 0 ? "text-terracotta" : "text-ink-soft"
              }`}
            >
              {x.points > 0 ? `+${x.points}` : x.points}
            </span>
          </div>
        ))
      )}

      {s.last_week.length > 0 && (
        <div className="rounded-2xl bg-card border border-cardline px-4 py-3">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">O'TGAN HAFTA G'OLIBLARI</div>
          {s.last_week.map((w) => (
            <div key={w.rank} className="mt-1 flex items-center gap-2 text-[13px] font-bold">
              <span>{["🥇", "🥈", "🥉"][w.rank - 1] ?? "🏅"}</span>
              <span className="min-w-0 flex-1 truncate">{w.name}</span>
              <span className="tabular-nums text-ink-soft">{w.points}</span>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-2xl bg-emerald-deep px-4 py-3 text-white">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-extrabold">🗓 Mavsum · {s.season.label}</span>
          <span className="text-[11px] font-bold text-white/75">{s.season.days_left} kun qoldi</span>
        </div>
        <div className="mt-1 text-[12px] font-semibold text-white/85">
          {s.season.ends_at} kuni mavsum yakunlanadi: top-3 e'lon qilinadi, so'ng hamma ballning{" "}
          {s.season.keep_pct}% i qoladi — ligalar qaytadan bellashuvga ochiladi. Janglar va
          g'alabalar soni saqlanadi.
        </div>
        {s.last_season.length > 0 && (
          <div className="mt-2 border-t border-white/20 pt-2 text-[12px] font-semibold text-white/85">
            O'tgan mavsum: {s.last_season.map((w) => `${["🥇", "🥈", "🥉"][w.rank - 1] ?? "🏅"} ${w.name}`).join(" · ")}
          </div>
        )}
      </div>
    </>
  );
}
