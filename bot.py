import os
import sqlite3
import random
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import telebot
from telebot import types

# === 1. ВЕБ-СЕРВЕР ДЛЯ РЕНДЕРА (БЕСПЛАТНЫЙ WEB SERVICE) ===
def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# === 2. ИНИЦИАЛИЗАЦИЯ БОТА ===
TOKEN = os.environ.get("BOT_TOKEN", "8823184074:AAFMQTqjoByD50vB8qZLYDLEdci98G5y_Ko")
bot = telebot.TeleBot(TOKEN)

# === 3. БАЗА УПРАЖНЕНИЙ С ССЫЛКАМИ НА ИЛЛЮСТРАЦИИ ("img") ===
EXERCISE_POOL = {
    "Грудь": [
        {
            "name": "Жим штанги лёжа",
            "tip": "Лопатки сведены, локти 45–70°. Представь, что «ломаешь» гриф наружу.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Bench-press-1.svg/500px-Bench-press-1.svg.png"
        },
        {
            "name": "Жим гантелей на наклонной скамье",
            "tip": "Угол 30°, мощный выжим вверх, не сбивай гантели вверху.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/01/Incline-dumbbell-press-1.svg/500px-Incline-dumbbell-press-1.svg.png"
        },
        {
            "name": "Сведения в тренажёре (Бабочка)",
            "tip": "Локти слегка согнуты, прожимай грудь 1 сек в конечной точке.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c2/Butterfly-machine-1.svg/500px-Butterfly-machine-1.svg.png"
        }
    ],
    "Спина": [
        {
            "name": "Тяга верхнего блока широким хватом",
            "tip": "Тяни ЛОКТЯМИ к верху груди, своди лопатки, грудь вперёд.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Lat-pulldown-1.svg/500px-Lat-pulldown-1.svg.png"
        },
        {
            "name": "Тяга Т-грифа / Гантели в наклоне",
            "tip": "Наклон ~45°, спина прямая, тяни к поясу, пауза вверху.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Bent-over-row-1.svg/500px-Bent-over-row-1.svg.png"
        },
        {
            "name": "Kelso-шраги на наклонной скамье",
            "tip": "Лёжа 45°, своди лопатки назад БЕЗ сгибания локтей.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Incline-dumbbell-row-1.svg/500px-Incline-dumbbell-row-1.svg.png"
        }
    ],
    "Плечи": [
        {
            "name": "Жим гантелей вверх сидя",
            "tip": "Локти слегка вперёд, опускай до уровня ушей, пресс напряжен.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/Seated-dumbbell-press-1.svg/500px-Seated-dumbbell-press-1.svg.png"
        },
        {
            "name": "Махи гантелями в стороны",
            "tip": "Локти согнуты, мизинцы чуть вверх, подъём строго дельтами.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/Dumbbell-lateral-raise-1.svg/500px-Dumbbell-lateral-raise-1.svg.png"
        }
    ],
    "Руки": [
        {
            "name": "Сгибания на бицепс с гантелями (супинация)",
            "tip": "Локти прижаты к корпусу, разворачивай кисть вверху.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Bicep-curl-1.svg/500px-Bicep-curl-1.svg.png"
        },
        {
            "name": "Разгибания на трицепс в блоке (канат)",
            "tip": "Локти неподвижны, разводи концы каната в нижней точке.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Triceps-pushdown-1.svg/500px-Triceps-pushdown-1.svg.png"
        }
    ],
    "Квадрицепс": [
        {
            "name": "Приседания со штангой / Гакк-присед",
            "tip": "Таз назад, колени по носкам, глубина ≥ параллели, не заваливай колени.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Squat-1.svg/500px-Squat-1.svg.png"
        },
        {
            "name": "Разгибания ног в тренажёре",
            "tip": "Зафиксируй таз, пауза 1 сек в верхней точке, контролируй опускание.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Leg-extension-1.svg/500px-Leg-extension-1.svg.png"
        }
    ],
    "Задняя цепь": [
        {
            "name": "Румынская тяга (RDL) со штангой/гантелями",
            "tip": "Таз назад, спина идеально прямая. Чувствуй растяжение бицепса бедра.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/Romanian-deadlift-1.svg/500px-Romanian-deadlift-1.svg.png"
        },
        {
            "name": "Сгибания ног в тренажёре",
            "tip": "Пятки к ягодицам, не отрывай бёдра, фиксация 1 сек в сжатии.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/Leg-curl-1.svg/500px-Leg-curl-1.svg.png"
        }
    ],
    "Пресс / Кор": [
        {
            "name": "Скручивания с канатом в блоке (Молитва)",
            "tip": "Округляй спину, движение от ГРУДИ к коленям, а не от бёдер.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/07/Cable-crunch-1.svg/500px-Cable-crunch-1.svg.png"
        },
        {
            "name": "Подъёмы ног в висе / на брусьях",
            "tip": "Подкручивай таз вверх, не раскачивайся за счёт инерции.",
            "img": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Hanging-leg-raise-1.svg/500px-Hanging-leg-raise-1.svg.png"
        }
    ]
}

# === 4. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ===
def init_db():
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            exercise TEXT,
            weight_reps TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()
user_sessions = {}

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🏋️ Сгенерировать FullBody", "📊 Моя статистика")
    markup.add("📜 Последние подходы")
    return markup

# === 5. ХЕНДЛЕРЫ КОМАНД ===
@bot.message_handler(commands=['start', 'help', 'cancel'])
def start_cmd(message):
    if message.from_user.id in user_sessions:
        del user_sessions[message.from_user.id]
        
    bot.send_message(
        message.chat.id, 
        f"Здорово, {message.from_user.first_name}! Это твой генератор FullBody тренировок с картинками техники.\n\n"
        "• **14 упражнений** с фото-иллюстрациями\n"
        "• **2-3 подхода** по 8-15 повторов\n"
        "• **90 секунд** отдых между подходами", 
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "🏋️ Сгенерировать FullBody" or msg.text == "/workout")
def generate_random_workout(message):
    uid = message.from_user.id
    
    workout_plan = []
    for section, exercises in EXERCISE_POOL.items():
        selected = random.sample(exercises, min(2, len(exercises)))
        for ex in selected:
            workout_plan.append({"section": section, "name": ex["name"], "tip": ex["tip"], "img": ex.get("img")})
            
    user_sessions[uid] = {"plan": workout_plan, "step": 0}
    send_exercise_card(message.chat.id, uid)

def send_exercise_card(chat_id, user_id):
    session = user_sessions.get(user_id)
    if not session:
        return

    step = session["step"]
    plan = session["plan"]

    if step >= len(plan):
        bot.send_message(chat_id, "🎉 *Тренировка полностью закрыта!* Отличный объём! 💪", parse_mode="Markdown", reply_markup=main_keyboard())
        del user_sessions[user_id]
        return

    ex = plan[step]

    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT weight_reps FROM logs WHERE user_id=? AND exercise=? ORDER BY id DESC LIMIT 1",
        (user_id, ex["name"])
    )
    last_log = cursor.fetchone()
    conn.close()

    last_str = f"`{last_log[0]}`" if last_log else "_нет записей_"

    caption_text = (
        f"📋 *Упражнение {step + 1} из {len(plan)}* [{ex['section']}]\n"
        f"💪 *{ex['name']}*\n\n"
        f"🎯 *Цель:* 2-3 подхода × 8-15 повторов\n"
        f"💡 *Техника:* {ex['tip']}\n\n"
        f"📌 *Твой прошлый вес:* {last_str}\n\n"
        f"✍️ Напиши вес и повторы (напр: `80 10 10`):"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭ Пропустить упражнение", callback_data="skip_step"))
    markup.add(types.InlineKeyboardButton("❌ Завершить тренировку", callback_data="cancel_workout"))

    # ЕСЛИ ЕСТЬ ССЫЛКА НА ИЛЛЮСТРАЦИЮ — ОТПРАВЛЯЕМ ФОТО С ТЕКСТОМ
    img_url = ex.get("img")
    if img_url:
        try:
            bot.send_photo(chat_id, photo=img_url, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
            return
        except Exception:
            pass # Если ссылка не открылась — отправит обычный текст

    bot.send_message(chat_id, caption_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["skip_step", "cancel_workout"])
def handle_inline_actions(call):
    uid = call.from_user.id
    if call.data == "cancel_workout":
        if uid in user_sessions:
            del user_sessions[uid]
        bot.send_message(call.message.chat.id, "⏹ Тренировка остановлена.", reply_markup=main_keyboard())
        return

    if call.data == "skip_step":
        if uid in user_sessions:
            user_sessions[uid]["step"] += 1
            send_exercise_card(call.message.chat.id, uid)

@bot.message_handler(func=lambda msg: msg.from_user.id in user_sessions)
def save_weight_input(message):
    uid = message.from_user.id
    text = message.text.strip()

    if text.startswith("/") or text in ["🏋️ Сгенерировать FullBody", "📊 Моя статистика", "📜 Последние подходы"]:
        del user_sessions[uid]
        if text == "📊 Моя статистика" or text == "/stats":
            show_stats(message)
        elif text == "📜 Последние подходы" or text == "/history":
            show_history(message)
        elif text == "🏋️ Сгенерировать FullBody" or text == "/workout":
            generate_random_workout(message)
        return

    step = user_sessions[uid]["step"]
    ex = user_sessions[uid]["plan"][step]
    user_name = message.from_user.first_name

    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (user_id, user_name, exercise, weight_reps) VALUES (?, ?, ?, ?)",
        (uid, user_name, ex["name"], text)
    )
    conn.commit()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"✅ *Записано:* {ex['name']} ➔ `{text}`\n⏱ *Отдых: 90 секунд!* Набирайся сил.",
        parse_mode="Markdown"
    )

    user_sessions[uid]["step"] += 1
    send_exercise_card(message.chat.id, uid)

@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda msg: msg.text == "📊 Моя статистика")
def show_stats(message):
    uid = message.from_user.id
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT exercise) FROM logs WHERE user_id=?", (uid,))
    total_sets, unique_ex = cursor.fetchone()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"📊 *Твоя статистика:*\n\n"
        f"🏋️ Записано подходов: *{total_sets}*\n"
        f"🎯 Упражнений опробовано: *{unique_ex}*",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['history'])
@bot.message_handler(func=lambda msg: msg.text == "📜 Последние подходы")
def show_history(message):
    uid = message.from_user.id
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute("SELECT exercise, weight_reps, timestamp FROM logs WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id, "История пока пуста.")
        return

    text = "📜 *Последние 10 записанных подходов:*\n\n"
    for r in rows:
        text += f"🔹 *{r[0]}*: `{r[1]}` _({r[2][5:16]})_\n"

    bot.send_message(message.chat.id, text, parse_mode="Markdown")

bot.polling(none_stop=True)
