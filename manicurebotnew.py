import sqlite3
from os import getenv
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
TOKEN_CLIENT = getenv("TOKEN1")
TOKEN_ORDERS = getenv("TOKEN2")
try:
    ADMIN_ID = int(getenv("ADMINID"))
except:
    ADMIN_ID = 0

bot = Bot(token=TOKEN_CLIENT)
bot_orders = Bot(token=TOKEN_ORDERS)
dp = Dispatcher(storage=MemoryStorage())

# --- ЛОГИРОВАНИЕ В КОНСОЛЬ (MIDDLEWARE) ---
# Этот блок будет срабатывать ПРИ ЛЮБОМ действии пользователя
@dp.update.outer_middleware()
async def user_logging_middleware(handler, event, data):
    user = data.get("event_from_user")
    if user:
        last_name = user.last_name if user.last_name else "—"
        first_name = user.first_name if user.first_name else "—"
        print(f"--- [LOG] ID: {user.id} | Name: {first_name} | Last Name: {last_name} | @{user.username} ---")
    return await handler(event, data)

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---

def init_db():
    conn = sqlite3.connect("booking_system.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS booked_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_key TEXT,
            time_slot TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_records (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            day_label TEXT,
            full_key TEXT,
            time_slot TEXT
        )
    """)
    conn.commit()
    conn.close()

def db_add_booking(user_id, name, day_label, full_key, time_slot):
    conn = sqlite3.connect("booking_system.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO booked_slots (full_key, time_slot) VALUES (?, ?)", (full_key, time_slot))
    cursor.execute("""
        INSERT OR REPLACE INTO user_records (user_id, name, day_label, full_key, time_slot) 
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, name, day_label, full_key, time_slot))
    conn.commit()
    conn.close()

def db_get_taken_slots(full_key):
    conn = sqlite3.connect("booking_system.db")
    cursor = conn.cursor()
    cursor.execute("SELECT time_slot FROM booked_slots WHERE full_key = ?", (full_key,))
    slots = [row[0] for row in cursor.fetchall()]
    conn.close()
    return slots

def db_get_user_record(user_id):
    conn = sqlite3.connect("booking_system.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, day_label, full_key, time_slot FROM user_records WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def db_delete_booking(user_id):
    record = db_get_user_record(user_id)
    if record:
        full_key, time_slot = record[2], record[3]
        conn = sqlite3.connect("booking_system.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM booked_slots WHERE full_key = ? AND time_slot = ?", (full_key, time_slot))
        cursor.execute("DELETE FROM user_records WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        return record
    return None

# --- ЛОГИКА ДАТ ---

def get_week_dates(week_prefix="curr"):
    today = datetime.now()
    # Понедельник текущей календарной недели (05.01)
    monday_now = today - timedelta(days=today.weekday())
    # Сдвиг на неделю вперед (12.01)
    start_of_booking = monday_now + timedelta(days=7)
    
    if week_prefix == "next":
        start_date = start_of_booking + timedelta(days=7)
    else:
        start_date = start_of_booking

    days_data = [("Пн", "Monday", 0), ("Вт", "Tuesday", 1), ("Ср", "Wednesday", 2),
                 ("Чт", "Thursday", 3), ("Пт", "Friday", 4), ("Сб", "Saturday", 5)]
    
    formatted_days = []
    for short_name, english_name, offset in days_data:
        day_date = start_date + timedelta(days=offset)
        date_str = day_date.strftime("%d.%m") 
        formatted_days.append({"label": f"({date_str}) {short_name}", "callback": f"day_{week_prefix}_{english_name}"})
    return formatted_days

# --- КЛАВИАТУРЫ ---

def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Записаться 📝", callback_data="register"))
    builder.row(types.InlineKeyboardButton(text="Посмотреть запись 👀", callback_data="check"))
    return builder.as_markup()

def last_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Отменить запись ❌", callback_data="delete_record"))
    builder.row(types.InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_main"))
    return builder.as_markup()

def days_menu_kb(week_prefix="curr"):
    builder = InlineKeyboardBuilder()
    days = get_week_dates(week_prefix)
    for d in days: builder.button(text=d["label"], callback_data=d["callback"])
    builder.adjust(2)
    if week_prefix == "curr":
        builder.row(types.InlineKeyboardButton(text="Следующая неделя ➡️", callback_data="week_next"))
    else:
        builder.row(types.InlineKeyboardButton(text="⬅️ Текущая неделя", callback_data="week_curr"))
    builder.row(types.InlineKeyboardButton(text="« Назад в меню", callback_data="back_to_main"))
    return builder.as_markup()

def time_menu_kb(week_day_key):
    builder = InlineKeyboardBuilder()
    all_times = ["11:00", "13:00", "15:00", "17:00"]
    taken_times = db_get_taken_slots(week_day_key)

    for t in all_times:
        if t in taken_times:
            builder.button(text=f"❌ {t}", callback_data="already_booked")
        else:
            builder.button(text=t, callback_data=f"settime_{week_day_key}_{t}")
    builder.adjust(2)
    week_prefix = week_day_key.split("_")[0]
    builder.row(types.InlineKeyboardButton(text="« Назад к дням", callback_data=f"week_{week_prefix}"))
    return builder.as_markup()

# --- СОСТОЯНИЯ ---
class Registration(StatesGroup):
    waiting_for_name = State()

# --- ОБРАБОТЧИКИ ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Используем HTML разметку для жирного шрифта
    full_name = message.from_user.first_name
    welcome_text = (
        f"Рады видеть вас, {full_name}! ✨\n\n"
        f"Пожалуйста, выберите действие в меню:"
    )
    
    # Кнопки с эмодзи в начале
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📝 Записаться", callback_data="register"))
    builder.row(types.InlineKeyboardButton(text="🔎 Моя запись", callback_data="check"))
    
    await message.answer(welcome_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "register")
async def start_reg(callback: types.CallbackQuery, state: FSMContext):
    if db_get_user_record(callback.from_user.id):
        await callback.answer("У вас уже есть активная запись!", show_alert=True)
        return
    await callback.message.delete()
    sent_msg = await callback.message.answer("Введите ваше Имя и Фамилию 😊")
    await state.update_data(msg_to_delete=sent_msg.message_id)
    await state.set_state(Registration.waiting_for_name)

@dp.message(Registration.waiting_for_name)
async def get_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try: await bot.delete_message(message.chat.id, data.get("msg_to_delete"))
    except: pass
    await message.delete()
    await state.update_data(name=message.text)
    await message.answer(f"Приятно познакомиться! Выберите день:", reply_markup=days_menu_kb("curr"))
    await state.set_state(None)

@dp.callback_query(F.data.startswith("week_"))
async def switch_week(callback: types.CallbackQuery):
    week_prefix = callback.data.split("_")[1]
    await callback.message.edit_text("Выберите день:", reply_markup=days_menu_kb(week_prefix))

@dp.callback_query(F.data.startswith("day_"))
async def select_day(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    week_prefix, day_key = parts[1], parts[2]
    dates = get_week_dates(week_prefix)
    day_label = next(d["label"] for d in dates if d["callback"] == callback.data)
    await state.update_data(week_prefix=week_prefix, day_label=day_label)
    await callback.message.edit_text(f"📅 {day_label}\nВремя:", reply_markup=time_menu_kb(f"{week_prefix}_{day_key}"))

@dp.callback_query(F.data.startswith("settime_"))
async def finalize_booking(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    week_prefix, day_key, t_val = parts[1], parts[2], parts[3]
    full_key = f"{week_prefix}_{day_key}"
    
    if t_val in db_get_taken_slots(full_key):
        await callback.answer("Это время уже занято!", show_alert=True)
        return

    user_data = await state.get_data()
    name = user_data.get("name", "Клиент")
    day_label = user_data.get("day_label")
    
    db_add_booking(callback.from_user.id, name, day_label, full_key, t_val)

    await callback.message.edit_text(f"✅ Готово!\n👤 {name}\n📅 {day_label}\n⏰ {t_val}", reply_markup=main_menu_kb())

    username = f"@{callback.from_user.username}" if callback.from_user.username else "скрыт"
    try:
        await bot_orders.send_message(ADMIN_ID, f"🔔 НОВЫЙ ЗАКАЗ!\n👤 {name} ({username})\n📅 {day_label}\n⏰ {t_val}")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "delete_record")
async def delete_booking(callback: types.CallbackQuery):
    record = db_delete_booking(callback.from_user.id)
    if record:
        name, day_label, _, time_slot = record
        try:
            await bot_orders.send_message(ADMIN_ID, f"❌ ОТМЕНА\n👤 {name}\n📅 {day_label} {time_slot}")
        except: pass
        await callback.message.edit_text("Запись отменена ✅", reply_markup=main_menu_kb())
    else:
        await callback.answer("Записей нет", show_alert=True)

@dp.callback_query(F.data == "check")
async def check_booking(callback: types.CallbackQuery):
    record = db_get_user_record(callback.from_user.id)
    if record:
        name, day_label, _, time_slot = record
        await callback.message.edit_text(f"Ваша запись:\n👤 {name}\n📅 {day_label}\n⏰ {time_slot}", reply_markup=last_menu_kb())
    else:
        await callback.answer("Вы еще не записаны", show_alert=True)

@dp.callback_query(F.data == "back_to_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите действие 🤗", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "already_booked")
async def already_booked_info(callback: types.CallbackQuery):
    await callback.answer("Это время уже занято!", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
