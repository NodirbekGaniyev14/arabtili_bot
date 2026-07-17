let current: HTMLAudioElement | null = null;

const SOUND_KEY = "arabiy_sound_off";

export function isSoundOn(): boolean {
  return localStorage.getItem(SOUND_KEY) !== "1";
}

export function setSoundOn(on: boolean): void {
  if (on) localStorage.removeItem(SOUND_KEY);
  else localStorage.setItem(SOUND_KEY, "1");
}

/** /audio/ papkasidan talaffuzni ijro etadi (sozlamada o'chirilgan bo'lsa jim) */
export function playAudio(file?: string) {
  if (!file || !isSoundOn()) return;
  current?.pause();
  current = new Audio(`/audio/${file}`);
  current.play().catch(() => {});
}
