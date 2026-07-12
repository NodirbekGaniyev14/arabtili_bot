interface HeaderProps {
  streak: number;
}

export default function Header({ streak }: HeaderProps) {
  return (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-2.5">
        <div className="w-10 h-10 rounded-xl bg-emerald-deep flex items-center justify-center shadow-sm">
          <span className="font-arabic text-2xl text-sand leading-none pt-1">
            ع
          </span>
        </div>
        <span className="text-xl font-extrabold tracking-tight">Arabiy</span>
      </div>

      <div className="flex items-center gap-1.5 rounded-full bg-gold-soft border border-gold/30 px-3.5 py-1.5">
        <span className="text-base leading-none">🔥</span>
        <span className="text-sm font-bold text-ink">{streak} kun</span>
      </div>
    </header>
  );
}
