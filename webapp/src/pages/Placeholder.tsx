interface PlaceholderProps {
  ar: string;
  title: string;
  note: string;
}

/** Keyingi bosqichlarda to'ldiriladigan sahifalar uchun vaqtinchalik ekran */
export default function Placeholder({ ar, title, note }: PlaceholderProps) {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center gap-3 px-8 text-center">
      <div className="w-20 h-20 rounded-3xl bg-gold-soft flex items-center justify-center">
        <span className="font-arabic text-4xl text-emerald-dark leading-none pt-1">
          {ar}
        </span>
      </div>
      <h2 className="text-xl font-extrabold">{title}</h2>
      <p className="text-sm text-ink-soft font-semibold max-w-60">{note}</p>
    </div>
  );
}
