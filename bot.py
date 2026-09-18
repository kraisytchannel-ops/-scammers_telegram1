import asyncio
import json
import logging
import os
import re
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
import aiohttp

# Берём токен из переменных окружения Render (безопасно!)
TOKEN = os.getenv("BOT_TOKEN", "8186611679:AAH2IXX-uATInkuTO3qrzP8df3bJdoxr6hU")
MODERATOR_CHAT_ID = -5453392098
ADMIN_IDS = {7346241328, 1753821033}
DATA_FILE = "bot_data.json"

router = Router()

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (
                    data.get("bot_stats", {"approved": 0, "rejected": 0, "total": 0}),
                    set(data.get("all_users", [])),
                    {int(k): v for k, v in data.get("user_reports_count", {}).items()}
                )
        except Exception:
            pass
    return {"approved": 0, "rejected": 0, "total": 0}, set(), {}

def save_data():
    data = {
        "bot_stats": bot_stats,
        "all_users": list(all_users),
        "user_reports_count": user_reports_count
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")

bot_stats, all_users, user_reports_count = load_data()

class ReportStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_link = State()
    waiting_for_reason = State()
    waiting_for_screenshots = State()

class AdminPostStates(StatesGroup):
    waiting_for_content = State()

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Действие отменено. Напиши /start для возврата в меню.")

# НОРМАЛЬНАЯ АДМИН-ПАНЕЛЬ ПО КОМАНДЕ /admin
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast_help")],
        [InlineKeyboardButton(text="📝 Создать пост в канал", callback_data="admin_post_help")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
    ])
    await message.answer("👑 **Панель управления администратора**\n\nВыбери нужный раздел:", reply_markup=keyboard)

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    
    stats_text = (
        f"📊 **Статистика бота:**\n\n"
        f"👥 Всего пользователей: {len(all_users)}\n"
        f"📥 Всего заявок: {bot_stats['total']}\n"
        f"✅ Одобрено: {bot_stats['approved']}\n"
        f"❌ Отклонено: {bot_stats['rejected']}"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="back_to_admin")]
    ])
    await callback.message.edit_text(stats_text, reply_markup=back_kb)
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast_help")
async def admin_broadcast_help(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "📢 **Как сделать рассылку:**\n\n"
        "Просто отправь в чат команду в формате:\n`/broadcast Текст твоей рассылки`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="back_to_admin")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "admin_post_help")
async def admin_post_help(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "📝 **Как создать пост:**\n\n"
        "Отправь команду `/post`, а затем следуй инструкциям бота (отправь фото с текстом).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в админку", callback_data="back_to_admin")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast_help")],
        [InlineKeyboardButton(text="📝 Создать пост в канал", callback_data="admin_post_help")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text("👑 **Панель управления администратора**\n\nВыбери нужный раздел:", reply_markup=keyboard)
    await callback.answer()

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        return
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Напиши текст рассылки после команды.")
        return
    
    formatted_text = (
        f"‼️ ВАЖНО ‼️\n\n"
        f"{text_to_send}\n\n"
        f"———————————————\n"
        f"🤖 Отправить скамера — @SendTheScammerBot\n"
        f"📢 Новости — @scammers_telegram1 | Подпишись!"
    )
    
    count = 0
    for uid in all_users:
        try:
            await bot.send_message(uid, formatted_text)
            count += 1
        except Exception:
            pass
    await message.answer(f"✅ Рассылка завершена. Доставлено: {count}")

@router.message(Command("post"))
async def cmd_post(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("📸 Отправь мне фото вместе с текстом (одним сообщением), которое нужно оформить для канала.")
    await state.set_state(AdminPostStates.waiting_for_content)

@router.message(AdminPostStates.waiting_for_content, F.photo)
async def process_admin_post(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user_text = message.caption or ""
    photo_id = message.photo[-1].file_id

    formatted_caption = (
        "‼️ ВАЖНО ‼️\n\n"
        f"{user_text}\n\n"
        "———————————————\n"
        "🤖 Отправить скамера — @SendTheScammerBot\n"
        "📢 Новости — @scammers_telegram1 | Подпишись!"
    )

    await message.answer("👇 Вот готовый пост. Можешь переслать его в канал:")
    await message.answer_photo(photo=photo_id, caption=formatted_caption)
    await state.clear()

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    all_users.add(user_id)
    save_data()
    
    if user_id == 7346241328:
        await message.answer("Привет Даня!")
    elif user_id == 1753821033:
        await message.answer("Привет Настя!")

    if user_id in ADMIN_IDS:
        await message.answer("👑 Привет, босс! Доступна админ-панель: /admin")

    await show_main_menu(message)

async def show_main_menu(message: Message):
    main_menu_text = (
        "👋 Главное меню системы безопасности!\n"
        "Здесь ты можешь безопасно сообщить о мошенниках или спамерах.\n\n"
        "👇 Выбери действие ниже:"
    )
    photo_path = r"C:\Users\asust\Desktop\telebot\бот.jpg"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚨 Отправить жалобу", callback_data="menu_report")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="📜 Правила / Инфо", callback_data="menu_rules")]
    ])

    if os.path.exists(photo_path):
        await message.answer_photo(photo=FSInputFile(photo_path), caption=main_menu_text, reply_markup=keyboard)
    else:
        await message.answer(main_menu_text, reply_markup=keyboard)

@router.callback_query(F.data == "menu_rules")
async def show_rules(callback: CallbackQuery):
    rules_text = (
        "📜 Правила сервиса:\n\n"
        "1. Не отправляй ложные жалобы.\n"
        "2. Прикладывай скриншоты для быстрого рассмотрения модераторами.\n"
        "3. Все данные проверяются автоматически.\n\n"
        "Нажми кнопку ниже, чтобы вернуться в меню."
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
    ])
    if callback.message.photo:
        await callback.message.edit_caption(caption=rules_text, reply_markup=back_kb)
    else:
        await callback.message.edit_text(text=rules_text, reply_markup=back_kb)
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def show_profile(callback: CallbackQuery):
    user = callback.from_user
    reports_sent = user_reports_count.get(user.id, 0)
    profile_text = (
        "👤 Твой профиль:\n\n"
        f"🆔 ID: {user.id}\n"
        f"👤 Имя: {user.full_name}\n"
        f"🚨 Отправлено жалоб: {reports_sent}\n"
        f"💎 Telegram Premium: {'Есть ✨' if getattr(user, 'is_premium', False) else 'Нет ❌'}"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_menu")]
    ])
    if callback.message.photo:
        await callback.message.edit_caption(caption=profile_text, reply_markup=back_kb)
    else:
        await callback.message.edit_text(text=profile_text, reply_markup=back_kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_main_menu(callback.message)
    await callback.answer()

@router.callback_query(F.data == "menu_report")
async def start_report_flow(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Скам на Телеграм-подарки", callback_data="cat_gifts")],
        [InlineKeyboardButton(text="🤖 Спам-бот / Рассылка", callback_data="cat_spam")],
        [InlineKeyboardButton(text="📂 Другое мошенничество", callback_data="cat_other")],
        [InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_menu")]
    ])
    text = "📂 Выбери категорию нарушения:"
    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=keyboard)
    else:
        await callback.message.edit_text(text=text, reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_category)
    await callback.answer()

@router.callback_query(ReportStates.waiting_for_category, F.data.startswith("cat_"))
async def process_category(callback: CallbackQuery, state: FSMContext):
    categories = {
        "cat_gifts": "🎁 Скам на Телеграм-подарки",
        "cat_spam": "🤖 Спам-бот",
        "cat_other": "📂 Другое"
    }
    cat_name = categories.get(callback.data, "📂 Другое")
    await state.update_data(category=cat_name)
    
    text = f"Категория: {cat_name}\n\n🔗 Шаг 2: Отправь ссылку на аккаунт, канал или сайт (например: @username или t.me/...):"
    if callback.message.photo:
        await callback.message.edit_caption(caption=text, reply_markup=None)
    else:
        await callback.message.edit_text(text=text, reply_markup=None)
    await callback.answer()
    await state.set_state(ReportStates.waiting_for_link)

async def check_url_accessibility(url: str) -> str:
    if not url.startswith("http") and not url.startswith("t.me") and not url.startswith("@"):
        return "⚠️ Формат ссылки необычный."
    if url.startswith("http"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=3) as resp:
                    return "🟢 Сайт доступен в сети." if resp.status < 400 else f"🟡 Код ответа сайта: {resp.status}"
        except Exception:
            return "🔴 Сайт не отвечает."
    return "ℹ️ Telegram-аккаунт/канал."

@router.message(ReportStates.waiting_for_link, F.text)
async def process_link(message: Message, state: FSMContext):
    text = message.text.strip()
    if "t.me/" not in text and "@" not in text and "http" not in text:
        await message.answer("⚠️ Пожалуйста, отправь корректную ссылку или юзернейм с @:")
        return

    status_ping = await check_url_accessibility(text)
    await state.update_data(scammer_link=text, link_status=status_ping)
    await message.answer(f"{status_ping}\n\n💬 Шаг 3: Опиши подробно, что произошло (текст или голосовое):")
    await state.set_state(ReportStates.waiting_for_reason)

@router.message(ReportStates.waiting_for_reason, F.text | F.voice)
async def process_reason(message: Message, state: FSMContext):
    if message.voice:
        await state.update_data(scammer_reason="[Голосовое описание]", voice_id=message.voice.file_id)
    else:
        await state.update_data(scammer_reason=message.text.strip(), voice_id=None)
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово, отправить жалобу", callback_data="finish_report")],
        [InlineKeyboardButton(text="⏩ Пропустить скриншоты", callback_data="skip_screenshots")]
    ])
    await message.answer("📸 Шаг 4: Отправь скриншоты-доказательства.\nКогда закончишь, нажми кнопку ниже:", reply_markup=keyboard)
    await state.set_state(ReportStates.waiting_for_screenshots)

@router.message(ReportStates.waiting_for_screenshots, F.photo)
async def collect_screenshots(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"📸 Скриншот успешно добавлен ({len(photos)}). Отправь еще или нажми «Готово».")

@router.callback_query(ReportStates.waiting_for_screenshots, F.data.in_({"finish_report", "skip_screenshots"}))
async def finish_report_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    
    category = data.get("category")
    link = data.get("scammer_link")
    reason = data.get("scammer_reason")
    link_status = data.get("link_status", "")
    voice_id = data.get("voice_id")
    photos = data.get("photos", [])

    bot_stats["total"] += 1
    user = callback.from_user
    user_reports_count[user.id] = user_reports_count.get(user.id, 0) + 1
    
    save_data()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔎 Взять на проверку", callback_data="take_check"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data="reject")
        ]
    ])

    has_premium = "✨ Есть" if getattr(user, "is_premium", False) else "❌ Нет"

    report_text = (
        f"🚨 Новая жалоба (#{bot_stats['total']})\n\n"
        f"📂 Категория: {category}\n"
        f"🔗 Ссылка: {link}\n"
        f"🔍 Статус: {link_status}\n"
        f"💬 Причина: {reason}\n\n"
        f"👤 Отправитель: {user.full_name} (ID: {user.id})\n"
        f"💎 Telegram Premium: {has_premium}"
    )

    if voice_id:
        await bot.send_voice(chat_id=MODERATOR_CHAT_ID, voice=voice_id, caption="Голосовое описание")

    if len(photos) > 1:
        media = [InputMediaPhoto(media=photos[0], caption=report_text)]
        for p_id in photos[1:]:
            media.append(InputMediaPhoto(media=p_id))
        await bot.send_media_group(chat_id=MODERATOR_CHAT_ID, media=media)
        await bot.send_message(chat_id=MODERATOR_CHAT_ID, text=f"Управление жалобой #{bot_stats['total']}:", reply_markup=keyboard)
    elif len(photos) == 1:
        await bot.send_photo(chat_id=MODERATOR_CHAT_ID, photo=photos[0], caption=report_text, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id=MODERATOR_CHAT_ID, text=report_text, reply_markup=keyboard)

    await state.clear()
    await callback.message.answer("✅ Жалоба успешно отправлена модераторам! Спасибо за помощь сообществу.")
    await show_main_menu(callback.message)

@router.callback_query(F.data == "take_check")
async def take_to_check(callback: CallbackQuery, bot: Bot):
    try:
        message_to_edit = callback.message
        text = message_to_edit.text or message_to_edit.caption
        if not text or "ID:" not in text:
            await callback.answer("ID не найден.", show_alert=True)
            return

        id_match = re.search(r"ID:\s*(\d+)", text)
        user_id = int(id_match.group(1))
        
        bot_stats["approved"] += 1
        save_data()
        
        await bot.send_message(user_id, "ℹ️ Твоя заявка рассмотрена модераторами и взята в работу!")
        
        new_suffix = f"\n\nStatus: 🔎 Одобрено\n👨‍💻 Админ: {callback.from_user.full_name}"
        if message_to_edit.photo:
            await message_to_edit.edit_caption(caption=text + new_suffix, reply_markup=None)
        else:
            await message_to_edit.edit_text(text=text + new_suffix, reply_markup=None)

        await callback.answer("Готово!")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

@router.callback_query(F.data == "reject")
async def reject_report(callback: CallbackQuery):
    try:
        message_to_edit = callback.message
        text = message_to_edit.text or message_to_edit.caption
        bot_stats["rejected"] += 1
        save_data()
        
        new_suffix = f"\n\nStatus: ❌ Отклонено\n👨‍💻 Админ: {callback.from_user.full_name}"
        if message_to_edit.photo:
            await message_to_edit.edit_caption(caption=text + new_suffix, reply_markup=None)
        else:
            await message_to_edit.edit_text(text=text + new_suffix, reply_markup=None)
        await callback.answer("Отклонено.")
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())