from os import getenv
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder


TOKEN_CLIENT = getenv("TOKEN1")
TOKEN_ORDERS = getenv("TOKEN2")
ADMIN_ID = getenv("ADMINID")

bot = Bot(token=TOKEN_CLIENT)
bot_orders = Bot(token=TOKEN_ORDERS)
dp = Dispatcher(storage=MemoryStorage())

booked_slots = {}  
final_records = {} 

class Registration(StatesGroup):
    waiting_for_name = State()



def get_week_dates(week_prefix="curr"):

    today = datetime.now()
    
    
    monday_now = today - timedelta(days=today.weekday())
    
    
    start_of_booking = monday_now
    
    if week_prefix == "next":
        start_date = start_of_booking + timedelta(days=7)
    else:
        start_date = start_of_booking
    
    days_data = [
        ("Пн", "Monday", 0),
        ("Вт", "Tuesday", 1),
        ("Ср", "Wednesday", 2),
        ("Чт", "Thursday", 3),
        ("Пт", "Friday", 4),
        ("Сб", "Saturday", 5),
    ]
    
    formatted_days = []
    for short_name, english_name, offset in days_data:
        day_date = start_date + timedelta(days=offset)
        date_str = day_date.strftime("%d.%m") 
        formatted_days.append({
            "label": f"({date_str}) {short_name}",
            "callback": f"day_{week_prefix}_{english_name}",
            "full_date": date_str
        })
    return formatted_days
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
    
    for day in days:
        builder.button(text=day["label"], callback_data=day["callback"])
    
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
    taken_times = booked_slots.get(week_day_key, [])

    for t in all_times:
        if t in taken_times:
            builder.button(text=f"❌ {t}", callback_data="already_booked")
        else:
            builder.button(text=t, callback_data=f"settime_{week_day_key}_{t}")
    
    builder.adjust(2)
    week_prefix = week_day_key.split("_")[0]
    builder.row(types.InlineKeyboardButton(text="« Назад к дням", callback_data=f"week_{week_prefix}"))
    return builder.as_markup()



@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(f"Здравствуйте, {message.from_user.first_name}!\nВыберите действие 🤗", 
                         reply_markup=main_menu_kb())

@dp.callback_query(F.data == "register")
async def start_reg(callback: types.CallbackQuery, state: FSMContext):
    # Добавь сюда:
    print(f"Пользователь {callback.from_user.id} нажал кнопку 'Записаться'")
    
    await callback.answer()
    await callback.message.delete()
    sent_msg = await callback.message.answer("Введите ваше Имя и Фамилию 😊")
    await state.update_data(msg_to_delete=sent_msg.message_id)
    await state.set_state(Registration.waiting_for_name)

@dp.message(Command("find"))
async def find_user(message: types.Message):
    
    if message.from_user.id != 7498022618:
        return

    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Пожалуйста, введите ID после команды.\nПример: `/find 709843737`", parse_mode="Markdown")
        return

    target_id = args[1]
    
    try:
       
        chat = await bot.get_chat(target_id)
        
       
        username = f"@{chat.username}" if chat.username else "скрыт"
        
        info = (
            f"🔍 Сведения о пользователе {target_id}:\n\n"
            f"👤 Имя: {chat.first_name}\n"
            f"📝 Фамилия: {chat.last_name if chat.last_name else 'не указана'}\n"
            f"📱 Юзернейм: {username}\n"
            f"ℹ️ Bio: {chat.bio if chat.bio else 'отсутствует'}\n"
            f"🔗 Ссылка: [Открыть профиль](tg://user?id={target_id})"
        )
        await message.answer(info, parse_mode="Markdown")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка поиска: {e}\n\n"
                             f"Возможные причины:\n"
                             f"1. ID неверный.\n"
                             f"2. Пользователь заблокировал бота.\n"
                             f"3. Пользователь никогда не писал этому боту.")
        
@dp.message(Registration.waiting_for_name)
async def get_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.delete_message(message.chat.id, data.get("msg_to_delete"))
        await message.delete()
    except: pass

    await state.update_data(name=message.text)
    await message.answer(f"Приятно познакомиться, {message.text}!\nВыберите день недели:", 
                         reply_markup=days_menu_kb("curr"))
    await state.set_state(None)

@dp.callback_query(F.data.startswith("week_"))
async def switch_week(callback: types.CallbackQuery):
    week_prefix = callback.data.split("_")[1]
    label = "ТЕКУЩАЯ" if week_prefix == "curr" else "СЛЕДУЮЩАЯ"
    await callback.message.edit_text(f"📅 Выбрана: {label} неделя\nВыберите день:", 
                                     reply_markup=days_menu_kb(week_prefix))

@dp.callback_query(F.data.startswith("day_"))
async def select_day(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    week_prefix = parts[1]
    day_key = parts[2]
    
    
    dates = get_week_dates(week_prefix)
    day_label = next(d["label"] for d in dates if d["callback"] == callback.data)
    
    await state.update_data(week_prefix=week_prefix, day_label=day_label)
    await callback.message.edit_text(f"📅 Выбрано: {day_label}\nВыберите время:", 
                                     reply_markup=time_menu_kb(f"{week_prefix}_{day_key}"))

@dp.callback_query(F.data.startswith("settime_"))
async def finalize_booking(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    week_prefix, day_key, t_val = parts[1], parts[2], parts[3]
    full_key = f"{week_prefix}_{day_key}"
    
    if full_key in booked_slots and t_val in booked_slots[full_key]:
        await callback.answer("Это время уже занято!", show_alert=True)
        return

    booked_slots.setdefault(full_key, []).append(t_val)
    
    user_data = await state.get_data()
    name = user_data.get("name")
    day_label = user_data.get("day_label")
    username = f"@{callback.from_user.username}" if callback.from_user.username else "скрыт"

    final_records[callback.message.chat.id] = {
        'name': name, 'day_label': day_label, 'full_key': full_key, 'time': t_val
    }

    await callback.message.edit_text(f"✅ Готово!\n👤 {name}\n📅 {day_label}\n⏰ {t_val}", 
                                     reply_markup=last_menu_kb())

    try:
        await bot_orders.send_message(ADMIN_ID, 
            f"🔔 НОВЫЙ ЗАКАЗ!\n👤 {name} ({username})\n📅 {day_label}\n⏰ {t_val}")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "delete_record")
async def delete_booking(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in final_records:
        rec = final_records[chat_id]
        if rec['full_key'] in booked_slots:
            booked_slots[rec['full_key']].remove(rec['time'])
        
        try:
            await bot_orders.send_message(ADMIN_ID, f"❌ ОТМЕНА\n👤 {rec['name']}\n📅 {rec['day_label']} {rec['time']}")
        except: pass

        del final_records[chat_id]
        await callback.message.edit_text("Запись отменена ✅", reply_markup=main_menu_kb())
    else:
        await callback.answer("Записей нет", show_alert=True)

@dp.callback_query(F.data == "check")
async def check_booking(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in final_records:
        rec = final_records[chat_id]
        await callback.message.edit_text(f"Ваша запись:\n👤 {rec['name']}\n📅 {rec['day_label']}\n⏰ {rec['time']}", 
                                         reply_markup=last_menu_kb())
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
    await dp.start_polling(bot)
    

if __name__ == "__main__":
    asyncio.run(main())
