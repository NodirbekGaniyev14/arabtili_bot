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

/** playAudio kabi, lekin ijro tugaganda (yoki boshqa audio boshlanganda) `onEnd` chaqiriladi —
 *  «🎵 Chalinmoqda» holati uchun (K24 lug'at). Ovoz o'chiq yoki fayl yo'q bo'lsa false. */
export function playAudioWatch(file: string | undefined, onEnd: () => void): boolean {
  if (!file || !isSoundOn()) return false;
  current?.pause();
  const a = new Audio(`/audio/${file}`);
  current = a;
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    onEnd();
  };
  a.addEventListener("ended", finish);
  a.addEventListener("error", finish);
  a.addEventListener("pause", finish);
  a.play().catch(finish);
  return true;
}

/** Serverdagi mp3 URL'ni ijro etadi (AI ustoz javobi). Muvaffaqiyat = true;
 *  false qaytsa chaqiruvchi brauzer TTS'ga (speakText) tushadi. */
export async function playUrl(url?: string, retries = 4): Promise<boolean> {
  if (!url || !isSoundOn()) return false;
  current?.pause();
  window.speechSynthesis?.cancel();
  // Server mp3'ni fonda tayyorlaydi — 404 bo'lsa biroz kutib qayta urinamiz
  for (let i = 0; i <= retries; i++) {
    const a = new Audio(url);
    current = a;
    try {
      await a.play();
      return true;
    } catch (e) {
      // Avtoijro taqiqlangan (foydalanuvchi bosmagan) — qayta urinish foydasiz
      if ((e as DOMException)?.name === "NotAllowedError") return false;
      if (i < retries) await new Promise((r) => setTimeout(r, 1200));
    }
  }
  return false;
}

/** Matnni brauzer TTS bilan aytadi (audio fayl yo'q dinamik matnlar uchun — rol o'yini). */
export function speakText(text?: string, lang = "ar-SA") {
  if (!text || !isSoundOn()) return;
  const synth = window.speechSynthesis;
  if (!synth) return;
  try {
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = 0.85;
    synth.speak(u);
  } catch {
    /* qo'llab-quvvatlanmasa — jim */
  }
}
