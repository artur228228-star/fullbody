import os
import sqlite3
import random
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import telebot
from telebot import types

# === 1. ВЕБ-СЕРВЕР ДЛЯ БЕСПЛАТНОГО ТАРИФА RENDER (WEB SERVICE) ===
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# === 2. ТОКЕН БОТА ===
# Берётся из переменной окружения Render (BOT_TOKEN) или прямо из кода
TOKEN = os.environ.get("BOT_TOKEN", "9078700609:AAFNdTFFQ9tZ7bC__Pjp5x8LiPjH8fLnkc0")
bot = telebot.TeleBot(TOKEN)

# === 3. БАЗА УПРАЖНЕНИЙ ПО 7 СЕКЦИЯМ (ИЗ README.MD) ===
EXERCISES_DB = {
    "chest": [
        {"name": "Жим штанги лёжа", "type": "base", "tip": "Стопы на полу, лопатки сведены, локти 45-70°. 2 сек опускай."},
        {"name": "Жим гантелей на наклонной", "type": "base", "tip": "Угол 30°, жми мощно вверх, не своди гантели со звоном."},
        {"name": "Сведения в тренажёре (Бабочка)", "type": "iso", "tip": "Локти согнуты, прожимай грудь 1 сек в конечной точке."},
        {"name": "Отжимания от пола / брусьев", "type": "base", "tip": "Корпус ровный, опускайся до 90° в локтях."}
    ],
    "back": [
        {"name": "Тяга верхнего блока", "type": "base", "tip": "Тяни ЛОКТЯМИ к верху груди, своди лопатки."},
        {"name": "Тяга штанги/Т-грифа в наклоне", "type": "base", "tip": "Спина прямая 45°, тяни к поясу, пауза вверху."},
        {"name": "Горизонтальная тяга блока", "type": "iso", "tip": "Спина неподвижна, тяни к низу живота."},
        {"name": "Kelso-шраги на скамье", "type": "iso", "tip": "Лёжа 45°, своди лопатки назад БЕЗ сгиба локтей."}
    ],
    "shoulders": [
        {"name": "Жим гантелей вверх сидя", "type": "base", "tip": "Опускай до ушей, пресс напряжён, не прогибай поясницу."},
        {"name": "Махи гантелями в стороны", "type": "iso", "tip": "Подъём строго дельтами до уровня плеч, без раскачки."},
        {"name": "Махи в кроссовере / канат", "type": "iso", "tip": "Постоянная нагрузка, пауза в верхней точке."}
    ],
    "arms": [
        {"name": "Сгибания на бицепс с гантелями", "type": "biceps", "tip": "Локти прижаты к ребрам, разворачивай кисть (супинация)."},
        {"name": "Сгибания хватом «Молот» / Пронация", "type": "biceps", "tip": "Качает брахиалис и предплечья для объёма рук."},
        {"name": "Разгибания на трицепс в блоке", "type": "triceps", "tip": "Локти неподвижны, разводи канат внизу."},
        {"name": "Французский жим / Из-за головы", "type": "triceps", "tip": "Максимально грузит длинную головку трицепса."}
    ],
    "legs": [
        {"name": "Приседания со штангой / Гакк", "type": "base", "tip": "Таз назад, колени по носкам, глубина ниже параллели."},
        {"name": "Жим ногами в тренажёре", "type": "base", "tip": "Пятки плотно, колени не заваливай внутрь."},
        {"name": "Разгибания ног сидя", "type": "iso", "tip": "Полное разгибание, пауза 1 сек вверху."}
    ],
    "posterior": [
        {"name": "Румынская тяга (RDL)", "type": "base", "tip": "Таз назад, спина идеально прямая. Растягивай бицепс бедра."},
        {"name": "Сгибания ног лежа/сидя", "type": "iso", "tip": "Пятки к ягодицам, не отрывай таз от скамьи."},
        {"name": "Подъёмы на икры стоя", "type": "iso", "tip": "Колени прямые, пауза 1-2 сек в верхней точке."}
    ],
    "core": [
        {"name": "Скручивания с канатом в блоке", "type": "iso", "tip": "Округляй спину, движение от груди к коленям."},
        {"name": "Подъёмы ног в висе / скамье", "type": "iso", "tip": "Подкручивай таз вверх, работай прессом."}
    ]
}

SECTIONS_RU = {
    "chest": "Грудь", "back": "Спина", "shoulders": "Плечи", 
    "arms": "Руки", "legs": "Ноги", "posterior": "Задняя цепь", "core": "Кор/Пресс"
}

# === 4. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ SQLite ===
def init_db():
    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            user_name TEXT,
            rest_time INTEGER DEFAULT 75,
            level TEXT DEFAULT 'medium'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exercise_name TEXT,
            weight_reps TEXT,
            weight_val REAL DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()
user_active_workouts = {}

# === 5. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def generate_workout(mode="full"):
    # Режимы: full = 7 секций × 2 упражнения = 14; quick = 4 секции × 2 = 8
    target_sections = ["chest", "back", "shoulders", "arms", "legs", "posterior", "core"]
    if mode == "quick":
        target_sections = ["chest", "back", "legs", "core"]
        
    workout_plan = []
    for sec in target_sections:
        pool = EXERCISES_DB[sec].copy()
        selected = random.sample(pool, min(2, len(pool)))
        for ex in selected:
            workout_plan.append({"section": SECTIONS_RU[sec], "name": ex["name"], "tip": ex["tip"]})
    return workout_plan

# === 6. ОБРАБОТЧИКИ КОМАНД БОТА ===
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, user_name) VALUES (?, ?)", 
                   (message.from_user.id, message.from_user.first_name))
    conn.commit()
    conn.close()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🏋️ /workout (14 упражнений)", "⚡ /quick (8 упражнений)")
    markup.add("📊 /stats", "📜 /history", "⚙️ /settings")
    
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "💪 *FullBody Bot* — твой персональный генератор фуллбади-тренировок!\n\n"
        "📌 *Что умеет бот:*\n"
        "• **14 упражнений** (7 секций × 2 упражнения) на каждую тренировку\n"
        "• **Умный расчёт прогресса:** подсказывает прошлый вес + 2.5 кг\n"
        "• **Запись веса и повторов** + история и статистика\n"
        "• **Таймер отдыха:** 60–90 секунд между подходами\n\n"
        "Жми любую кнопку в меню ниже:"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['workout'])
@bot.message_handler(func=lambda msg: "14 упражнений" in msg.text)
def start_full_workout(message):
    plan = generate_workout(mode="full")
    user_active_workouts[message.from_user.id] = {"plan": plan, "index": 0}
    
    text = f"📅 *Новая Фуллбади Тренировка (14 упражнений)*\n\n"
    for i, ex in enumerate(plan, 1):
        text += f"{i}. [{ex['section']}] *{ex['name']}*\n"
    text += "\n⏱ *Отдых между подходами:* 75 сек (3 подхода × 8–12 повторов)\n\nНажмите кнопку ниже:"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("▶️ Начать тренировку", callback_data="next_ex"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(commands=['quick'])
@bot.message_handler(func=lambda msg: "8 упражнений" in msg.text)
def start_quick_workout(message):
    plan = generate_workout(mode="quick")
    user_active_workouts[message.from_user.id] = {"plan": plan, "index": 0}
    
    text = f"⚡ *Быстрая Тренировка (8 упражнений)*\n\n"
    for i, ex in enumerate(plan, 1):
        text += f"{i}. [{ex['section']}] *{ex['name']}*\n"
    text += "\n⏱ *Отдых между подходами:* 75 сек\n\nНажмите кнопку ниже:"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("▶️ Начать тренировку", callback_data="next_ex"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "next_ex")
def show_current_exercise(call):
    uid = call.from_user.id
    if uid not in user_active_workouts:
        bot.send_message(call.message.chat.id, "Тренировка не найдена. Начни новую через /workout")
        return
        
    session = user_active_workouts[uid]
    index = session["index"]
    plan = session["plan"]
    
    if index >= len(plan):
        bot.send_message(call.message.chat.id, "🎉 *Тренировка окончена!* Отличная работа! 💪", parse_mode="Markdown")
        del user_active_workouts[uid]
        return
        
    ex = plan[index]
    
    # Достаем прошлый результат из БД
    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT weight_reps, weight_val FROM logs WHERE user_id=? AND exercise_name=? ORDER BY id DESC LIMIT 1",
        (uid, ex["name"])
    )
    last_log = cursor.fetchone()
    conn.close()
    
    if last_log:
        last_str = last_log[0]
        target_val = last_log[1] + 2.5 if last_log[1] > 0 else "N/A"
        prog_text = f"📈 *Прошлый раз:* `{last_str}` ➔ 🎯 *Цель:* `+{target_val} kg`"
    else:
        prog_text = "📌 *Прошлый раз:* нет записей ➔ 🎯 *Цель:* подбери комфортный вес"
        
    msg = (
        f"🏋️ *Упражнение {index + 1}/{len(plan)}:* [{ex['section']}]\n"
        f"💪 *{ex['name']}*\n\n"
        f"💡 *Техника:* {ex['tip']}\n\n"
        f"{prog_text}\n\n"
        "Введи подход (например: `80 10 10 9` или `60kg x 8`):"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭ Пропустить упражнение", callback_data="skip_ex"))
    markup.add(types.InlineKeyboardButton("⏹ Завершить тренировку", callback_data="finish_workout"))
    
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "skip_ex")
def skip_exercise(call):
    uid = call.from_user.id
    if uid in user_active_workouts:
        user_active_workouts[uid]["index"] += 1
        show_current_exercise(call)

@bot.callback_query_handler(func=lambda call: call.data == "finish_workout")
def finish_workout_early(call):
    uid = call.from_user.id
    if uid in user_active_workouts:
        del user_active_workouts[uid]
    bot.send_message(call.message.chat.id, "🏁 Тренировка завершена досрочно!")

@bot.message_handler(func=lambda msg: msg.from_user.id in user_active_workouts)
def save_set_log(message):
    uid = message.from_user.id
    session = user_active_workouts[uid]
    ex = session["plan"][session["index"]]
    
    weight_reps = message.text.strip()
    
    # Извлекаем число для расчета прогрессии (+2.5кг)
    weight_val = 0.0
    try:
        first_num = ''.join(c for c in weight_reps.split()[0] if c.isdigit() or c == '.')
        if first_num:
            weight_val = float(first_num)
    except Exception:
        weight_val = 0.0

    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (user_id, exercise_name, weight_reps, weight_val) VALUES (?, ?, ?, ?)",
        (uid, ex["name"], weight_reps, weight_val)
    )
    conn.commit()
    conn.close()
    
    session["index"] += 1
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➡️ Следующее упражнение", callback_data="next_ex"))
    
    bot.send_message(
        message.chat.id,
        f"✅ *Записано:* {ex['name']} ➔ `{weight_reps}`\n\n"
        "⏳ *Отдых 75 секунд!* Переведи дыхание перед следующим упражнением.",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda msg: "stats" in msg.text.lower())
def show_stats(message):
    uid = message.from_user.id
    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT exercise_name) FROM logs WHERE user_id=?", (uid,))
    total_sets, unique_ex = cursor.fetchone()
    conn.close()
    
    text = (
        f"📊 *Твоя статистика тренировок:*\n\n"
        f"🏋️ Записано подходов: *{total_sets}*\n"
        f"🎯 Уникальных упражнений: *{unique_ex}*\n"
        f"🔥 Серия недель: *Активна*\n"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['history'])
@bot.message_handler(func=lambda msg: "history" in msg.text.lower())
def show_history(message):
    uid = message.from_user.id
    conn = sqlite3.connect("fullbody.sqlite3")
    cursor = conn.cursor()
    cursor.execute("SELECT exercise_name, weight_reps, timestamp FROM logs WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        bot.send_message(message.chat.id, "История подходов пока пуста.")
        return
        
    text = "📜 *Последние 10 записанных подходов:*\n\n"
    for r in rows:
        text += f"🔹 *{r[0]}*: `{r[1]}` _({r[2][:16]})_\n"
        
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['settings'])
@bot.message_handler(func=lambda msg: "settings" in msg.text.lower())
def show_settings(message):
    text = (
        "⚙️ *Настройки бота:*\n\n"
        "⏱ *Отдых по умолчанию:* 75 сек (диапазон 60–90 сек)\n"
        "🏋️ *Оборудование:* Полный зал / Гантели\n"
        "🌐 *Язык:* Русский\n"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

bot.polling(none_stop=True)
