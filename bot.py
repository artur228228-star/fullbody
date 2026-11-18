"""
FullBody Bot v2 — Telegram-бот для фуллбади-тренировок с визуальными гайдами.

Что умеет:
  • 8 мышечных групп × 2 упражнения, отдых 60–90 с с живым таймером;
  • к КАЖДОМУ упражнению присылает GIF-анимацию (старт ⇄ финиш) или фото-карточку
    «Старт → Финиш» — как в Fitbod / Strong / Hevy; в подписи техника и ошибки;
  • замена упражнения на альтернативу, экспресс-режим, журнал подходов «60x10»,
    прогресс, рекорды, «прошлый раз» прямо в карточке;
  • библиотека упражнений с картинками по группам мышц.

Стек: Python 3.10+, aiogram 3, Pillow, SQLite. Лицензия MIT.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, FSInputFile, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv не обязателен
    pass

import db
import media
from exercises import ALL, GROUPS, Exercise, alternatives, build_plan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gymbot")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
REST_CHOICES = (60, 75, 90)
SET_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[xх×\*]\s*(\d+)\s*$|^\s*(\d+)\s*$")

router = Router()


# ---------------------------------------------------------------- состояние тренировки
@dataclass
class Session:
    mode: str
    plan: List[Exercise]
    idx: int = 0
    set_no: int = 1
    done_sets: int = 0
    volume: float = 0.0
    logged: Dict[str, List[str]] = field(default_factory=dict)
    timer: Optional[asyncio.Task] = None

    @property
    def ex(self) -> Exercise:
        return self.plan[self.idx]


SESSIONS: Dict[int, Session] = {}


# ---------------------------------------------------------------- клавиатуры
def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🏋️ Начать тренировку")],
        [KeyboardButton(text="📚 Упражнения"), KeyboardButton(text="📊 Прогресс")],
        [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="❓ Помощь")],
    ])


def ikb(rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows])


def exercise_kb(s: Session) -> InlineKeyboardMarkup:
    ex = s.ex
    last = s.idx == len(s.plan) - 1
    return ikb([
        [(f"✅ Подход {s.set_no}/{ex.sets} сделан", "set:done")],
        [("🔁 Заменить", "swap"), ("ℹ️ Техника", f"tech:{ex.key}")],
        [("🏁 Завершить" if last else "➡️ Следующее", "next"), ("⏹ Стоп", "stop")],
    ])


# ---------------------------------------------------------------- тексты
def caption_for(ex: Exercise, s: Optional[Session] = None, user_id: Optional[int] = None) -> str:
    n = f"{s.idx + 1}/{len(s.plan)} · " if s else ""
    txt = (f"<b>{n}{ex.name}</b>\n{GROUPS[ex.group]} · {ex.equipment}\n"
           f"🎯 <b>{ex.sets} × {ex.reps}</b>")
    if s:
        txt += f" · подход <b>{s.set_no}</b>"
        prev = db.last_result(user_id, ex.key) if user_id else None
        if prev:
            txt += f"\n📈 Прошлый раз: {prev[0]:g} кг × {prev[1]}"
        if s.logged.get(ex.key):
            txt += "\n📝 Сегодня: " + ", ".join(s.logged[ex.key])
    txt += "\n\n🧠 <b>Техника:</b>\n" + "\n".join(f"• {t}" for t in ex.tips[:3])
    if s:
        txt += "\n\n✍️ После подхода напиши <code>60x10</code> (вес × повторы) или нажми ✅"
    return txt


def technique_text(ex: Exercise) -> str:
    t = f"<b>{ex.name}</b> — {GROUPS[ex.group]}\n\n✅ <b>Как делать:</b>\n" + \
        "\n".join(f"{i + 1}. {x}" for i, x in enumerate(ex.tips))
    if ex.mistakes:
        t += "\n\n❌ <b>Частые ошибки:</b>\n" + "\n".join(f"• {x}" for x in ex.mistakes)
    return t


# ---------------------------------------------------------------- отправка медиа
async def send_exercise(bot: Bot, chat_id: int, user_id: int, ex: Exercise, caption: str,
                        kb: Optional[InlineKeyboardMarkup] = None) -> Message:
    """Шлёт GIF / фото-карточку (по настройке пользователя) с подписью; кеширует file_id."""
    mode = db.get_user(user_id).get("media_mode", "gif")
    if mode != "text":
        kind = "gif" if mode == "gif" else "card"
        cache_key = f"{ex.key}:{kind}"
        file_id = db.get_file_id(cache_key)
        src = file_id
        if not src:
            path = await media.ensure_media(ex, kind)
            src = FSInputFile(path) if path else None
        if src is not None:
            try:
                if kind == "gif":
                    msg = await bot.send_animation(chat_id, src, caption=caption, reply_markup=kb)
                    fid = msg.animation.file_id if msg.animation else (
                        msg.document.file_id if msg.document else None)
                else:
                    msg = await bot.send_photo(chat_id, src, caption=caption, reply_markup=kb)
                    fid = msg.photo[-1].file_id if msg.photo else None
                if fid and not file_id:
                    db.put_file_id(cache_key, fid)
                return msg
            except TelegramBadRequest as e:
                log.warning("media send failed (%s): %s", ex.key, e)
        # запасной вариант: картинка по прямой ссылке из free-exercise-db
        try:
            return await bot.send_photo(chat_id, ex.image_urls[0], caption=caption, reply_markup=kb)
        except TelegramBadRequest:
            pass
    return await bot.send_message(chat_id, caption, reply_markup=kb)


async def show_current(bot: Bot, chat_id: int, user_id: int) -> None:
    s = SESSIONS[user_id]
    await send_exercise(bot, chat_id, user_id, s.ex, caption_for(s.ex, s, user_id), exercise_kb(s))


# ---------------------------------------------------------------- таймер отдыха
async def rest_timer(bot: Bot, chat_id: int, seconds: int) -> None:
    msg = await bot.send_message(chat_id, f"⏱ Отдых: <b>{seconds}</b> сек")
    left = seconds
    try:
        while left > 0:
            step = 5 if left > 10 else left
            await asyncio.sleep(step)
            left -= step
            if left > 0:
                k = round(10 * left / seconds)
                try:
                    await msg.edit_text(f"⏱ Отдых: <b>{left}</b> сек\n" + "🟩" * k + "⬜" * (10 - k))
                except TelegramBadRequest:
                    pass
        await msg.edit_text("🔔 <b>Отдых окончен — следующий подход!</b>")
    except asyncio.CancelledError:
        try:
            await msg.edit_text("⏭ Таймер пропущен")
        except TelegramBadRequest:
            pass
        raise


def start_timer(s: Session, bot: Bot, chat_id: int, seconds: int) -> None:
    if s.timer and not s.timer.done():
        s.timer.cancel()
    s.timer = asyncio.create_task(rest_timer(bot, chat_id, seconds))


# ================================================================ ХЕНДЛЕРЫ
@router.message(CommandStart())
async def cmd_start(m: Message) -> None:
    db.ensure_user(m.from_user.id, m.from_user.full_name)
    await m.answer(
        f"Привет, <b>{m.from_user.first_name}</b>! Я FullBody Bot 🏋️\n\n"
        "Веду тебя по фуллбади-тренировке: <b>8 групп мышц × 2 упражнения</b>, "
        "отдых 60–90 сек с таймером.\n\n"
        "К каждому упражнению присылаю <b>GIF-анимацию «старт → финиш»</b> "
        "или фото-карточку — видно, как делать, а не только текст.\n\n"
        "Жми «🏋️ Начать тренировку» или загляни в «📚 Упражнения».",
        reply_markup=main_kb())


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def cmd_help(m: Message) -> None:
    await m.answer(
        "<b>Команды</b>\n"
        "/workout — начать тренировку (полная или экспресс)\n"
        "/exercises — библиотека упражнений с картинками\n"
        "/progress — статистика и личные рекорды\n"
        "/settings — отдых 60/75/90 с, формат картинок\n"
        "/stop — прервать тренировку\n\n"
        "<b>Во время тренировки</b>\n"
        "✅ — подход выполнен, запускается таймер отдыха\n"
        "<code>60x10</code> — записать вес × повторы (или просто <code>10</code> — повторы)\n"
        "🔁 — заменить упражнение на альтернативу\n"
        "ℹ️ — подробная техника и типичные ошибки\n\n"
        "Картинки: открытая база free-exercise-db (800+ упражнений).")


# ---------------------------------------------------------------- тренировка
@router.message(Command("workout"))
@router.message(F.text == "🏋️ Начать тренировку")
async def cmd_workout(m: Message) -> None:
    db.ensure_user(m.from_user.id, m.from_user.full_name)
    await m.answer(
        "Выбери режим:\n\n"
        "💪 <b>Фуллбади</b> — 8 групп × 2 упражнения, ~60–70 мин\n"
        "⚡ <b>Экспресс</b> — 8 групп × 1 упражнение, ~35 мин",
        reply_markup=ikb([[("💪 Фуллбади (16 упр.)", "start:full")],
                          [("⚡ Экспресс (8 упр.)", "start:express")]]))


@router.callback_query(F.data.startswith("start:"))
async def cb_start(c: CallbackQuery, bot: Bot) -> None:
    mode = c.data.split(":")[1]
    SESSIONS[c.from_user.id] = Session(mode=mode, plan=build_plan(mode))
    rest = db.get_user(c.from_user.id)["rest_sec"]
    await c.message.edit_text(f"🔥 Поехали! Отдых между подходами: <b>{rest} с</b>.\n"
                              "Разминка 5 минут — и первое упражнение 👇")
    await show_current(bot, c.message.chat.id, c.from_user.id)
    await c.answer()


@router.callback_query(F.data == "set:done")
async def cb_set_done(c: CallbackQuery, bot: Bot) -> None:
    s = SESSIONS.get(c.from_user.id)
    if not s:
        return await c.answer("Тренировка не запущена: /workout", show_alert=True)
    await _complete_set(c, bot, s)


async def _complete_set(c: CallbackQuery, bot: Bot, s: Session) -> None:
    ex = s.ex
    s.done_sets += 1
    if s.set_no < ex.sets:
        s.set_no += 1
        rest = db.get_user(c.from_user.id)["rest_sec"]
        try:
            await c.message.edit_reply_markup(reply_markup=exercise_kb(s))
        except TelegramBadRequest:
            pass
        start_timer(s, bot, c.message.chat.id, rest)
        await c.answer(f"Подход записан. Отдых {rest} с ⏱")
    else:
        await c.answer("Упражнение выполнено ✅")
        await _advance(c, bot, s)


async def _advance(c: CallbackQuery, bot: Bot, s: Session) -> None:
    if s.timer and not s.timer.done():
        s.timer.cancel()
    if s.idx + 1 >= len(s.plan):
        return await _finish(c.from_user.id, c.message.chat.id, bot)
    s.idx += 1
    s.set_no = 1
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await show_current(bot, c.message.chat.id, c.from_user.id)


@router.callback_query(F.data == "next")
async def cb_next(c: CallbackQuery, bot: Bot) -> None:
    s = SESSIONS.get(c.from_user.id)
    if not s:
        return await c.answer("Тренировка не запущена: /workout", show_alert=True)
    await c.answer()
    await _advance(c, bot, s)


@router.callback_query(F.data == "swap")
async def cb_swap(c: CallbackQuery) -> None:
    s = SESSIONS.get(c.from_user.id)
    if not s:
        return await c.answer("Тренировка не запущена", show_alert=True)
    alts = [e for e in alternatives(s.ex.group, s.ex.key) if e not in s.plan]
    if not alts:
        return await c.answer("Замены нет", show_alert=True)
    await c.message.answer("Выбери замену:",
                           reply_markup=ikb([[(f"{e.name} ({e.equipment})", f"swapto:{e.key}")] for e in alts]
                                            + [[("↩️ Оставить", "swapcancel")]]))
    await c.answer()


@router.callback_query(F.data.startswith("swapto:"))
async def cb_swapto(c: CallbackQuery, bot: Bot) -> None:
    s = SESSIONS.get(c.from_user.id)
    key = c.data.split(":", 1)[1]
    if not s or key not in ALL:
        return await c.answer("Ошибка", show_alert=True)
    s.plan[s.idx] = ALL[key]
    s.set_no = 1
    await c.message.delete()
    await show_current(bot, c.message.chat.id, c.from_user.id)
    await c.answer("Заменено 🔁")


@router.callback_query(F.data == "swapcancel")
async def cb_swapcancel(c: CallbackQuery) -> None:
    await c.message.delete()
    await c.answer()


@router.callback_query(F.data.startswith("tech:"))
async def cb_tech(c: CallbackQuery) -> None:
    ex = ALL.get(c.data.split(":", 1)[1])
    if ex:
        await c.message.answer(technique_text(ex))
    await c.answer()


@router.callback_query(F.data == "stop")
@router.message(Command("stop"))
async def cb_stop(event, bot: Bot) -> None:
    uid = event.from_user.id
    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    if uid in SESSIONS:
        await _finish(uid, chat_id, bot, aborted=True)
    else:
        await bot.send_message(chat_id, "Активной тренировки нет.", reply_markup=main_kb())
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _finish(uid: int, chat_id: int, bot: Bot, aborted: bool = False) -> None:
    s = SESSIONS.pop(uid, None)
    if not s:
        return
    if s.timer and not s.timer.done():
        s.timer.cancel()
    done_ex = s.idx + (0 if aborted else 1)
    db.finish_workout(uid, s.mode, done_ex, s.done_sets, s.volume)
    title = "⏹ Тренировка прервана" if aborted else "🏆 Тренировка завершена!"
    await bot.send_message(
        chat_id,
        f"<b>{title}</b>\n\n"
        f"Упражнений: <b>{done_ex}/{len(s.plan)}</b>\nПодходов: <b>{s.done_sets}</b>\n"
        f"Тоннаж: <b>{s.volume:g} кг</b>\n\n"
        "Заминка 5 минут, вода, белок. Следующая фуллбади — через 48 ч 💤",
        reply_markup=main_kb())


@router.message(F.text.regexp(SET_RE))
async def msg_log_set(m: Message, bot: Bot) -> None:
    """Пользователь пишет «60x10» или «10» — записываем подход и запускаем таймер."""
    s = SESSIONS.get(m.from_user.id)
    if not s:
        return await m.answer("Чтобы записывать подходы, начни тренировку: /workout")
    g = SET_RE.match(m.text).groups()
    weight = float(g[0].replace(",", ".")) if g[0] else 0.0
    reps = int(g[1] or g[2])
    ex = s.ex
    db.log_set(m.from_user.id, ex.key, s.set_no, weight, reps)
    s.volume += weight * reps
    s.logged.setdefault(ex.key, []).append(f"{weight:g}×{reps}" if weight else f"×{reps}")
    s.done_sets += 1
    if s.set_no < ex.sets:
        s.set_no += 1
        rest = db.get_user(m.from_user.id)["rest_sec"]
        await m.answer(f"📝 {ex.name}: <b>{weight:g} кг × {reps}</b> записано. "
                       f"Следующий подход {s.set_no}/{ex.sets}.",
                       reply_markup=ikb([[(f"✅ Подход {s.set_no}/{ex.sets} сделан", "set:done")],
                                         [("➡️ Следующее упражнение", "next")]]))
        start_timer(s, bot, m.chat.id, rest)
    else:
        await m.answer(f"📝 Записано. <b>{ex.name}</b> выполнено ✅")
        if s.idx + 1 >= len(s.plan):
            return await _finish(m.from_user.id, m.chat.id, bot)
        s.idx += 1
        s.set_no = 1
        await show_current(bot, m.chat.id, m.from_user.id)


# ---------------------------------------------------------------- библиотека
@router.message(Command("exercises"))
@router.message(F.text == "📚 Упражнения")
async def cmd_exercises(m: Message) -> None:
    rows = [[(name, f"grp:{key}")] for key, name in GROUPS.items()]
    await m.answer("📚 <b>Библиотека упражнений</b>\nВыбери группу мышц — пришлю GIF и технику:",
                   reply_markup=ikb(rows))


@router.callback_query(F.data.startswith("grp:"))
async def cb_group(c: CallbackQuery) -> None:
    from exercises import EXERCISES
    g = c.data.split(":")[1]
    if g == "back":
        await c.answer()
        return await c.message.edit_text(
            "📚 <b>Библиотека упражнений</b>\nВыбери группу мышц — пришлю GIF и технику:",
            reply_markup=ikb([[(name, f"grp:{key}")] for key, name in GROUPS.items()]))
    rows = [[(f"{'⭐ ' if i < 2 else ''}{e.name}", f"ex:{e.key}")] for i, e in enumerate(EXERCISES[g])]
    rows.append([("⬅️ Группы", "grp:back")])
    await c.message.edit_text(f"{GROUPS[g]} — ⭐ основные, остальные — замены:", reply_markup=ikb(rows))
    await c.answer()


@router.callback_query(F.data.startswith("ex:"))
async def cb_exercise(c: CallbackQuery, bot: Bot) -> None:
    ex = ALL.get(c.data.split(":", 1)[1])
    if not ex:
        return await c.answer("Не найдено", show_alert=True)
    await c.answer("Готовлю картинку…")
    await send_exercise(bot, c.message.chat.id, c.from_user.id, ex, caption_for(ex),
                        ikb([[("ℹ️ Техника и ошибки", f"tech:{ex.key}")]]))


# ---------------------------------------------------------------- прогресс
@router.message(Command("progress"))
@router.message(F.text == "📊 Прогресс")
async def cmd_progress(m: Message) -> None:
    st = db.stats(m.from_user.id)
    if not st["total"]:
        return await m.answer("Пока нет тренировок. Начни первую: /workout 💪")
    txt = (f"📊 <b>Прогресс</b>\n\nТренировок всего: <b>{st['total']}</b> · за 7 дней: <b>{st['week']}</b>\n"
           f"Подходов: <b>{st['sets']}</b> · тоннаж: <b>{st['volume']:g} кг</b>\n\n<b>Последние:</b>\n")
    for w in st["last"]:
        txt += f"• {w['date']} — {'фуллбади' if w['mode'] == 'full' else 'экспресс'}, " \
               f"{w['exercises']} упр., {w['sets']} подх., {w['volume']:g} кг\n"
    prs = db.personal_records(m.from_user.id)[:8]
    if prs:
        txt += "\n🏅 <b>Рекорды:</b>\n" + "\n".join(
            f"• {ALL[k].name if k in ALL else k}: {w:g} кг × {r}" for k, w, r in prs)
    await m.answer(txt)


# ---------------------------------------------------------------- настройки
def settings_kb(u: Dict) -> InlineKeyboardMarkup:
    rest = [(("✅ " if u["rest_sec"] == r else "") + f"{r} с", f"rest:{r}") for r in REST_CHOICES]
    modes = [("gif", "🎞 GIF"), ("card", "🖼 Фото-карточка"), ("text", "📝 Только текст")]
    media_row = [(("✅ " if u["media_mode"] == k else "") + t, f"media:{k}") for k, t in modes]
    return ikb([rest, media_row])


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def cmd_settings(m: Message) -> None:
    db.ensure_user(m.from_user.id, m.from_user.full_name)
    await m.answer("⚙️ <b>Настройки</b>\n\n⏱ Отдых между подходами:\n🖼 Формат показа упражнений:",
                   reply_markup=settings_kb(db.get_user(m.from_user.id)))


@router.callback_query(F.data.startswith("rest:"))
async def cb_rest(c: CallbackQuery) -> None:
    db.set_rest(c.from_user.id, int(c.data.split(":")[1]))
    await c.message.edit_reply_markup(reply_markup=settings_kb(db.get_user(c.from_user.id)))
    await c.answer("Сохранено")


@router.callback_query(F.data.startswith("media:"))
async def cb_media(c: CallbackQuery) -> None:
    db.set_media_mode(c.from_user.id, c.data.split(":")[1])
    await c.message.edit_reply_markup(reply_markup=settings_kb(db.get_user(c.from_user.id)))
    await c.answer("Сохранено")


@router.message()
async def fallback(m: Message) -> None:
    await m.answer("Не понял 🤔 Нажми кнопку меню или /help", reply_markup=main_kb())


# ================================================================ ЗАПУСК
async def main() -> None:
    if not TOKEN:
        print("Нет BOT_TOKEN. Создай .env (см. .env.example) или export BOT_TOKEN=...", file=sys.stderr)
        sys.exit(1)
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands([
        BotCommand(command="workout", description="Начать тренировку"),
        BotCommand(command="exercises", description="Библиотека упражнений"),
        BotCommand(command="progress", description="Прогресс и рекорды"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="stop", description="Прервать тренировку"),
    ])
    media.build_all()
    log.info("FullBody Bot v2 запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
