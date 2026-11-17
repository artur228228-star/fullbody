import sqlite3
import telebot
from telebot import types

TOKEN = "9078700609:AAFNdTFFQ9tZ7bC__Pjp5x8LiPjH8fLnkc0"
bot = telebot.TeleBot(TOKEN)

EXERCISES = [
    "1. Грудь (Жим лёжа / сведения)",
    "2. Широчайшие (Тяга верхнего блока / Горизонтальная)",
    "3. Верх спины (Тяга Т-грифа / Kelso-шраги)",
    "4. Плечи (Жим вверх / Махи в стороны)",
    "5. Бицепс (Сгибания супинированные / пронированные)",
    "6. Трицепс (Разгибания в блоке / Брусья)",
    "7. Задняя дельта (Бабочка / Канат)",
    "8. Квадрицепс (Присед / Разгибания ног)",
    "9. Бицепс бедра (RDL / Сгибания ног)",
    "10. Приводящие / Отводящие (Сведение / Разведение)",
    "11. Пресс (Скручивания на блоке / скамье)",
    "12. Икры (Подъёмы на носки)"
]

TECHNIQUE_TIPS = {
    "1. Грудь (Жим лёжа / сведения)": "Лопатки сведены, локти 45-70°. Представь, что «ломаешь» гриф наружу. 2 сек вниз.",
    "2. Широчайшие (Тяга верхнего блока / Горизонтальная)": "Тяни локтями, а не руками. Грудь вперёд, своди лопатки.",
    "3. Верх спины (Тяга Т-грифа / Kelso-шраги)": "Наклон ~45°, пауза 1 сек вверху. Kelso: своди лопатки без сгиба локтей.",
    "4. Плечи (Жим вверх / Махи в стороны)": "Не прогибай поясницу. Махи: большие пальцы слегка вниз, подъём только дельтами.",
    "5. Бицепс (Сгибания супинированные / пронированные)": "Локти прижаты. Пронация качает брахиалис и предплечья.",
    "6. Трицепс (Разгибания в блоке / Брусья)": "Из-за головы — лучшая нагрузка на длинную головку. Брусья: корпус прямо.",
    "7. Задняя дельта (Бабочка / Канат)": "Микро-веса, контроль движения. Важно для осанки и суставов.",
    "8. Квадрицепс (Присед / Разгибания ног)": "Присед: таз назад, колени по носкам, глубина ниже параллели.",
    "9. Бицепс бедра (RDL / Сгибания ног)": "RDL: таз назад, спина идеально прямая. Растяжение в бицепсе бедра.",
    "10. Приводящие / Отводящие (Сведение / Разведение)": "В конечной точке сжатие 1-2 сек. Контроль важнее веса.",
    "11. Пресс (Скручивания на блоке / скамье)": "Округляй спину, движение от груди, а не от бёдер. Медленный темп.",
    "12. Икры (Подъёмы на носки)": "Прямые колени, полная амплитуда, пауза 1-2 сек вверху."
}

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
user_states = {}

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🏋️ Начать FullBody тренировку", "📊 Прошлые результаты")
    bot.send_message(
        message.chat.id, 
        f"Привет, {message.from_user.first_name}! Это твой бесплатный дневник тренировок Full Body.\nВыбирай действие:", 
        reply_markup=markup
    )

@bot.message_handler(func=lambda msg: msg.text == "🏋️ Начать FullBody тренировку")
def show_exercises(message):
    markup = types.InlineKeyboardMarkup()
    for ex in EXERCISES:
        markup.add(types.InlineKeyboardButton(text=ex, callback_data=f"ex_{EXERCISES.index(ex)}"))
    bot.send_message(message.chat.id, "Выбери упражнение:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ex_"))
def handle_exercise_select(call):
    ex_index = int(call.data.split("_")[1])
    ex_name = EXERCISES[ex_index]
    user_states[call.from_user.id] = ex_name
    
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT weight_reps, timestamp FROM logs WHERE user_id=? AND exercise=? ORDER BY id DESC LIMIT 1",
        (call.from_user.id, ex_name)
    )
    last_log = cursor.fetchone()
    conn.close()
    
    last_info = f"\n\n📌 *Прошлый результат:* {last_log[0]}" if last_log else "\n\n📌 *Прошлый результат:* нет записей"
    tip = TECHNIQUE_TIPS.get(ex_name, "")
    
    bot.send_message(
        call.message.chat.id, 
        f"💪 *{ex_name}*\n\n💡 *Техника:* {tip}{last_info}\n\nВведи веса и повторы (напр: `80кг 10 10 9`):",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.from_user.id in user_states)
def save_weight_reps(message):
    user_id = message.from_user.id
    ex_name = user_states[user_id]
    weight_reps = message.text
    user_name = message.from_user.first_name
    
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (user_id, user_name, exercise, weight_reps) VALUES (?, ?, ?, ?)",
        (user_id, user_name, ex_name, weight_reps)
    )
    conn.commit()
    conn.close()
    
    del user_states[user_id]
    bot.send_message(
        message.chat.id, 
        f"✅ Сохранено!\nУпражнение: *{ex_name}*\nРезультат: `{weight_reps}`\n\n⏱️ Отдых: 60-90 сек (изоляция) / 90-150 сек (база).",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "📊 Прошлые результаты")
def show_history(message):
    conn = sqlite3.connect("gym_workout.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_name, exercise, weight_reps, timestamp FROM logs ORDER BY id DESC LIMIT 10"
    )
    logs = cursor.fetchall()
    conn.close()
    
    if not logs:
        bot.send_message(message.chat.id, "История пока пуста.")
        return
        
    res_text = "📋 *Последние 10 подходов (ваши и кента):*\n\n"
    for log in logs:
        res_text += f"👤 *{log[0]}* | {log[1]}\n➡️ `{log[2]}`\n\n"
        
    bot.send_message(message.chat.id, res_text, parse_mode="Markdown")

bot.polling(none_stop=True)
