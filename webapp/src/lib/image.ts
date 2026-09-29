/** Surat yuklashdan oldin telefonda tayyorlash — ✍️ yozuv mashqi va dars YOZISH fazasi (K28).
 *
 *  Kichraytiriladi (mobil internet, AI narxi) va JPEG'ga o'tkaziladi (#F84: telefon HEIC/WebP bersa ham
 *  serverga JPEG boradi; dekod bo'lmasa asl fayl — server o'zi o'qiydi va kichraytiradi).
 *  K28: EXIF burilishi aniq qo'llanadi (`imageOrientation: "from-image"`) — aks holda eski WebView'da
 *  telefon surati yonboshlab ketadi, JPEG'ga qayta yozilganda EXIF yo'qoladi va AI yon turgan
 *  qo'lyozmani o'qiy olmasdi. */

const MAX_SIDE = 1600;

/** Brauzer dekod qila olmagan formatlar (Android'da HEIC) uchun <img> orqali urinish (<img> EXIF'ni qo'llaydi). */
function decodeViaImg(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("decode"));
    };
    img.src = url;
  });
}

export async function shrinkImage(file: File, maxSide = MAX_SIDE): Promise<Blob> {
  try {
    let src: ImageBitmap | HTMLImageElement;
    try {
      src = await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
      src = await decodeViaImg(file);
    }
    const w = "naturalWidth" in src ? src.naturalWidth : src.width;
    const h = "naturalHeight" in src ? src.naturalHeight : src.height;
    const scale = Math.min(1, maxSide / Math.max(w, h));
    const isJpeg = file.type === "image/jpeg" || file.type === "image/png";
    if (scale === 1 && file.size < 1_500_000 && isJpeg) return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve) => canvas.toBlob((b) => resolve(b ?? file), "image/jpeg", 0.85));
  } catch {
    return file; // eski WebView / HEIC — server o'zi o'qiydi va kichraytiradi
  }
}
