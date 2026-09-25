interface TelegramWebAppUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  photo_url?: string;
}

interface TelegramWebApp {
  ready(): void;
  expand(): void;
  close(): void;
  initData: string;
  initDataUnsafe: {
    user?: TelegramWebAppUser;
    start_param?: string;
  };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  /** Bot API 6.1+: Telegram to'lov oynasi (Payme/Click) — K18.5 */
  openInvoice?(url: string, callback?: (status: "paid" | "cancelled" | "failed" | "pending") => void): void;
  openTelegramLink?(url: string): void;
  /** Bot API 7.8+: rasmni Telegram story'ga joylash (K21.5) */
  shareToStory?(media_url: string, params?: { text?: string; widget_link?: { url: string; name?: string } }): void;
  isVersionAtLeast?(version: string): boolean;
  /** Bot API 6.2+: tasdiqlash oynasi */
  showConfirm?(message: string, callback?: (ok: boolean) => void): void;
  version?: string;
  onEvent?(event: string, handler: () => void): void;
  offEvent?(event: string, handler: () => void): void;
  /** Bot API 6.1+: sarlavhadagi «orqaga» tugmasi (K26 ichki sahifalar) */
  BackButton?: {
    show?(): void;
    hide?(): void;
    onClick?(cb: () => void): void;
    offClick?(cb: () => void): void;
  };
  HapticFeedback?: {
    impactOccurred(
      style: "light" | "medium" | "heavy" | "rigid" | "soft"
    ): void;
    notificationOccurred(type: "error" | "success" | "warning"): void;
  };
}

interface Window {
  Telegram?: {
    WebApp: TelegramWebApp;
  };
}

/** vite.config.ts define — package.json versiyasi (K26) */
declare const __APP_VERSION__: string;
