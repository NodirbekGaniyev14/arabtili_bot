/** Mavzu (K19.3): yorug' / qorong'i / avto.
 *
 *  Ranglar Tailwind tokenlari (index.css @theme) — qorong'i rejim `:root[data-theme="dark"]`
 *  ostida o'sha tokenlarni almashtiradi, komponentlar o'zgarmaydi. «Avto» —
 *  Telegram'ning colorScheme'i (mijoz mavzusi), undan tashqarida prefers-color-scheme.
 *  Tanlov localStorage'da; Telegram sarlavha/fon rangi ham mavzuga moslanadi. */

export type ThemeMode = "auto" | "light" | "dark";
export type Resolved = "light" | "dark";

const KEY = "arabiy_theme";
const BG: Record<Resolved, string> = { light: "#faf6ee", dark: "#151917" };

const tg = () => window.Telegram?.WebApp;

export function getMode(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "auto") return v;
  } catch {
    /* jim */
  }
  return "auto";
}

export function systemScheme(): Resolved {
  const t = tg();
  if (t?.colorScheme === "dark" || t?.colorScheme === "light") return t.colorScheme;
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function resolve(mode: ThemeMode): Resolved {
  return mode === "auto" ? systemScheme() : mode;
}

export function current(): Resolved {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(mode: ThemeMode = getMode()): Resolved {
  const r = resolve(mode);
  const root = document.documentElement;
  root.dataset.theme = r;
  root.style.colorScheme = r;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = BG[r];
  try {
    tg()?.setHeaderColor?.(BG[r]);
    tg()?.setBackgroundColor?.(BG[r]);
  } catch {
    /* eski mijoz */
  }
  return r;
}

export function setMode(mode: ThemeMode): Resolved {
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    /* jim */
  }
  return applyTheme(mode);
}

/** Ilova ochilganda: saqlangan mavzu + tizim/Telegram mavzusi o'zgarsa (avto rejimda) qayta qo'llash. */
export function initTheme(): void {
  applyTheme(getMode());
  const onChange = () => {
    if (getMode() === "auto") applyTheme("auto");
  };
  try {
    tg()?.onEvent?.("themeChanged", onChange);
  } catch {
    /* jim */
  }
  try {
    window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", onChange);
  } catch {
    /* jim */
  }
}
