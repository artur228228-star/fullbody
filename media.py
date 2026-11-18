"""
Визуальные гайды упражнений.

Из двух кадров free-exercise-db (старт / финиш) бот собирает:
  • GIF-анимацию (кадры чередуются, как в Fitbod / ExerciseDB) — media/<key>.gif
  • фото-карточку «Старт → Финиш» с подписями — media/<key>.jpg

Файлы кешируются на диске, а после первой отправки в Telegram — ещё и file_id
(в SQLite), поэтому повторные отправки мгновенные и без трафика.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

import requests
from PIL import Image, ImageDraw, ImageFont

from exercises import ALL, Exercise

log = logging.getLogger(__name__)

MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1 — шрифт без системных зависимостей
    except TypeError:
        return ImageFont.load_default()


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _label(img: Image.Image, text: str, color=(255, 255, 255), bg=(20, 20, 20)) -> Image.Image:
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    f = _font(max(22, img.width // 24))
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    pad = 10
    d.rounded_rectangle((12, 12, 12 + w + 2 * pad, 12 + h + 2 * pad), radius=10, fill=bg)
    d.text((12 + pad, 12 + pad - box[1]), text, font=f, fill=color)
    return img


def frames_for(ex: Exercise) -> List[Path]:
    raw_dir = MEDIA_DIR / "raw" / ex.key
    raw_dir.mkdir(parents=True, exist_ok=True)
    return [_download(u, raw_dir / f"{i}.jpg") for i, u in enumerate(ex.image_urls)]


def build_gif(ex: Exercise, force: bool = False) -> Path:
    """GIF: старт ⇄ финиш с подписями, 1.1 сек на кадр."""
    out = MEDIA_DIR / f"{ex.key}.gif"
    if out.exists() and not force:
        return out
    paths = frames_for(ex)
    imgs = [Image.open(p) for p in paths]
    w = min(i.width for i in imgs); h = min(i.height for i in imgs)
    frames = []
    for i, (img, text) in enumerate(zip(imgs, ["1 • Старт", "2 • Финиш"])):
        img = img.resize((w, h))
        img = _label(img, f"{text}  |  {ex.name}", bg=(220, 60, 60) if i else (40, 120, 220))
        frames.append(img.convert("P", palette=Image.ADAPTIVE, colors=128))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=1100, loop=0, optimize=True)
    return out


def build_card(ex: Exercise, force: bool = False) -> Path:
    """Фото-карточка: два кадра рядом со стрелкой и названием."""
    out = MEDIA_DIR / f"{ex.key}.jpg"
    if out.exists() and not force:
        return out
    paths = frames_for(ex)
    a, b = [Image.open(p).convert("RGB") for p in paths]
    h = 480
    a = a.resize((int(a.width * h / a.height), h)); b = b.resize((int(b.width * h / b.height), h))
    gap, top = 60, 70
    card = Image.new("RGB", (a.width + b.width + gap, h + top), (255, 255, 255))
    card.paste(a, (0, top)); card.paste(b, (a.width + gap, top))
    d = ImageDraw.Draw(card)
    d.text((16, 14), ex.name, font=_font(34), fill=(20, 20, 20))
    cx, cy = a.width + gap // 2, top + h // 2
    d.polygon([(cx - 22, cy - 18), (cx + 18, cy), (cx - 22, cy + 18)], fill=(220, 60, 60))
    f = _font(24)
    d.text((12, top + 10), "СТАРТ", font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(40, 120, 220))
    d.text((a.width + gap + 12, top + 10), "ФИНИШ", font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(220, 60, 60))
    card.save(out, "JPEG", quality=88)
    return out


def build_all(force: bool = False) -> None:
    """Собрать медиа для всех упражнений (запускается `python media.py` или при PREFETCH_MEDIA=1)."""
    for key, ex in ALL.items():
        try:
            build_gif(ex, force); build_card(ex, force)
            log.info("media ok: %s", key)
        except Exception as e:  # noqa: BLE001
            log.warning("media fail %s: %s", key, e)


async def ensure_media(ex: Exercise, kind: str) -> Optional[Path]:
    """Неблокирующая сборка в пуле потоков. kind: 'gif' | 'card'."""
    fn = build_gif if kind == "gif" else build_card
    try:
        return await asyncio.get_running_loop().run_in_executor(None, fn, ex)
    except Exception as e:  # noqa: BLE001
        log.warning("media error for %s: %s", ex.key, e)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    build_all(force="--force" in __import__("sys").argv)
    print(f"Готово: {MEDIA_DIR}")
