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
