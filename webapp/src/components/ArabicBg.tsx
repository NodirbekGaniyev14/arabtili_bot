/** Fon: islimiy girih naqsh + suzuvchi shaffof arab harflari */

const LETTERS: Array<{
  ch: string;
  style: React.CSSProperties;
}> = [
  {
    ch: "ع",
    style: { top: "4%", right: "-4%", fontSize: 190, opacity: 0.055, animationDelay: "0s" },
  },
  {
    ch: "م",
    style: { top: "36%", left: "-7%", fontSize: 150, opacity: 0.05, animationDelay: "-5s" },
  },
  {
    ch: "ب",
    style: { bottom: "20%", right: "1%", fontSize: 140, opacity: 0.05, animationDelay: "-9s" },
  },
  {
    ch: "ن",
    style: { bottom: "2%", left: "6%", fontSize: 115, opacity: 0.045, animationDelay: "-3s" },
  },
];

export default function ArabicBg() {
  return (
    <>
      <div className="girih-bg fixed inset-0 z-0 pointer-events-none" />
      {LETTERS.map((l) => (
        <span key={l.ch} className="floating-letter" style={l.style}>
          {l.ch}
        </span>
      ))}
    </>
  );
}
