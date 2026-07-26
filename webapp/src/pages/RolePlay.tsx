import { useEffect, useRef, useState } from "react";
import { api, type RoleplayScenario } from "../lib/api";
import { speakText } from "../lib/audio";

interface RolePlayProps {
  onClose: () => void;
}

interface Msg {
  role: "user" | "assistant";
  ar: string;
  uz?: string;
}

const tg = () => window.Telegram?.WebApp;

export default function RolePlay({ onClose }: RolePlayProps) {
  const [scenarios, setScenarios] = useState<RoleplayScenario[] | null>(null);
  const [active, setActive] = useState<RoleplayScenario | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .getRoleplayScenarios()
      .then((r) => setScenarios(r.scenarios))
      .catch(() => setScenarios([]));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const start = async (sc: RoleplayScenario) => {
    setActive(sc);
    setMessages([]);
    setDone(false);
    setLoading(true);
    try {
      const r = await api.roleplayReply(sc.id, []);
      setMessages([{ role: "assistant", ar: r.ar, uz: r.uz }]);
    } catch {
      setMessages([{ role: "assistant", ar: "", uz: "Xatolik. Qayta urinib ko'ring." }]);
    } finally {
      setLoading(false);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || !active || loading || done) return;
    const next: Msg[] = [...messages, { role: "user", ar: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    tg()?.HapticFeedback?.impactOccurred("light");
    try {
      const history = next.map((m) => ({ role: m.role, content: m.ar }));
      const r = await api.roleplayReply(active.id, history);
      setMessages([...next, { role: "assistant", ar: r.ar, uz: r.uz }]);
      if (r.done) setDone(true);
    } catch {
      setMessages([...next, { role: "assistant", ar: "", uz: "Xatolik yuz berdi." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-sand flex flex-col max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-cardline bg-card">
        <div className="min-w-0">
          <div className="text-[11px] font-extrabold tracking-[0.14em] text-ink-soft">
            🗣 JONLI SUHBAT
          </div>
          <div className="font-extrabold truncate">
            {active ? `${active.emoji} ${active.title_uz}` : "Rol o'yini"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-9 h-9 rounded-full bg-cardline text-ink-soft font-extrabold shrink-0"
        >
          ✕
        </button>
      </div>

      {/* Scenario tanlash */}
      {!active && (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          <p className="text-sm text-ink-soft font-semibold">
            Vaziyatni tanlang va Saudiyalik bilan suhbatlashib mashq qiling. Arabcha
            (yoki hijoziy) yozib javob bering.
          </p>
          {scenarios?.map((sc) => (
            <button
              key={sc.id}
              onClick={() => start(sc)}
              className="w-full flex items-center gap-3 rounded-2xl bg-card border border-cardline p-4 text-left active:scale-[0.98] transition-transform"
            >
              <div className="w-12 h-12 shrink-0 rounded-xl bg-gold-soft flex items-center justify-center text-2xl">
                {sc.emoji}
              </div>
              <div className="min-w-0">
                <div className="font-extrabold">{sc.title_uz}</div>
                <div className="text-xs text-ink-soft font-semibold">{sc.desc_uz}</div>
              </div>
            </button>
          ))}
          {scenarios && scenarios.length === 0 && (
            <div className="text-center text-ink-soft font-semibold pt-8">
              Vaziyatlar yuklanmadi.
            </div>
          )}
        </div>
      )}

      {/* Suhbat */}
      {active && (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                    m.role === "user"
                      ? "bg-emerald-deep text-white"
                      : "bg-card border border-cardline"
                  }`}
                >
                  {m.ar && (
                    <div className="font-arabic text-xl leading-snug" dir="rtl">
                      {m.ar}
                    </div>
                  )}
                  {m.uz && (
                    <div
                      className={`text-xs font-semibold mt-1 ${
                        m.role === "user" ? "text-gold-soft" : "text-ink-soft"
                      }`}
                    >
                      {m.uz}
                    </div>
                  )}
                  {m.role === "assistant" && m.ar && (
                    <button
                      onClick={() => speakText(m.ar)}
                      className="mt-1 text-lg active:scale-90 transition-transform"
                      aria-label="Tinglash"
                    >
                      🔊
                    </button>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-card border border-cardline px-4 py-3">
                  <span className="inline-block w-2 h-2 rounded-full bg-ink-soft animate-pulse" />
                </div>
              </div>
            )}
            {done && (
              <div className="text-center py-3">
                <div className="text-2xl">✅</div>
                <p className="text-sm font-bold text-emerald-dark">Suhbat tugadi!</p>
                <button
                  onClick={() => setActive(null)}
                  className="mt-1 text-xs font-bold text-emerald-dark underline"
                >
                  Boshqa vaziyat
                </button>
              </div>
            )}
          </div>

          {/* Kiritish */}
          {!done && (
            <div className="p-3 border-t border-cardline bg-card flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && send()}
                dir="rtl"
                placeholder="جوابك هنا..."
                // min-w-0: flex ichida input'ning tug'ma eni (size≈20) qatorni
                // ekrandan kengaytirib, matn boshini kesib qo'yardi
                className="flex-1 min-w-0 rounded-xl bg-sand border border-cardline px-3 py-2.5 font-arabic text-lg outline-none focus:border-emerald-deep/40"
              />
              <button
                onClick={send}
                disabled={!input.trim() || loading}
                className="w-11 h-11 shrink-0 rounded-xl bg-emerald-deep text-white text-xl font-extrabold active:scale-90 transition-transform disabled:opacity-40"
              >
                ↑
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
