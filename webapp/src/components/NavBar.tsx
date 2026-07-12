export type Tab = "home" | "lessons" | "review" | "rating" | "profile";

const TABS: Array<{ id: Tab; ar: string; label: string }> = [
  { id: "home", ar: "بيت", label: "Asosiy" },
  { id: "lessons", ar: "درس", label: "Darslar" },
  { id: "review", ar: "كرر", label: "Takror" },
  { id: "rating", ar: "نجم", label: "Reyting" },
  { id: "profile", ar: "أنا", label: "Profil" },
];

interface NavBarProps {
  tab: Tab;
  onChange: (tab: Tab) => void;
  reviewBadge?: number;
}

export default function NavBar({ tab, onChange, reviewBadge = 0 }: NavBarProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-20 bg-card/95 backdrop-blur border-t border-cardline"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="flex">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => {
                window.Telegram?.WebApp.HapticFeedback?.impactOccurred("light");
                onChange(t.id);
              }}
              className={`flex-1 flex flex-col items-center gap-0.5 pt-2 pb-1.5 transition-colors ${
                active ? "text-emerald-deep" : "text-ink-soft"
              }`}
            >
              <span className="relative">
                <span className="font-arabic text-[22px] leading-none">
                  {t.ar}
                </span>
                {t.id === "review" && reviewBadge > 0 && (
                  <span className="absolute -top-1.5 -right-3.5 min-w-4 h-4 px-1 rounded-full bg-terracotta text-white text-[9px] font-extrabold flex items-center justify-center">
                    {reviewBadge > 9 ? "9+" : reviewBadge}
                  </span>
                )}
              </span>
              <span
                className={`text-[10px] ${active ? "font-extrabold" : "font-semibold"}`}
              >
                {t.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
