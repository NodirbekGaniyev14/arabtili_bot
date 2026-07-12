let current: HTMLAudioElement | null = null;

/** /audio/ papkasidan talaffuzni ijro etadi */
export function playAudio(file?: string) {
  if (!file) return;
  current?.pause();
  current = new Audio(`/audio/${file}`);
  current.play().catch(() => {});
}
