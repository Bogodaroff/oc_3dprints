import sqlite3
import openai
import re
import asyncio
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery,Message,ChatPermissions
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils.exceptions import MessageToDeleteNotFound
from aiogram.utils import executor
from typing import Dict
import json

BOT_TOKEN="5429358648:AAG5qjfop2gdRt0mfVILEQv-nSnzuRpO6t8"
openaiapi_key = "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"
dbname = "dbchat.db"

class OpenAI_API:
    def __init__(self, api_key: str, api_base: str):
        self.api_key = api_key
        self.api_base = api_base

    async def create_completion(self, model: str, **kwargs) -> Dict:
        async with httpx.AsyncClient() as client:
            headers = {"Content-Type": "application/json",
                       "Authorization": f"Bearer {self.api_key}"}
            url = f"{self.api_base}/completions"
            data = {
                "model": model,
                **kwargs
            }
            response = await client.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"OpenAI API error: {response.text}")
            
            
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

@dp.message_handler(commands=['kick'])
async def kick_user(message: types.Message):
    # Проверяем, что пользователь, вызвавший команду, является администратором
    chat_member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if not chat_member.is_chat_admin():
        await message.reply("У вас нет прав на выполнение этой команды!")
        return

    # Проверяем, что команда была отправлена в ответ на сообщение
    if not message.reply_to_message:
        await message.reply("Эта команда должна быть использована в ответ на сообщение!")
        return

    # Получаем пользователя, которого нужно кикнуть
    user = message.reply_to_message.from_user

    # Кикаем пользователя
    await bot.kick_chat_member(message.chat.id, user.id)

    # Отправляем ответное сообщение
    await message.reply(f"{user.get_mention(as_html=True)} был кикнут из чата! Наверно плохо себя вел")
    
@dp.message_handler(commands=['ban'])
async def ban_user(message: types.Message):
    # Проверяем, является ли пользователь админом
    if not await is_admin(message.from_user.id, message.chat.id):
        await message.answer("Вы не являетесь админом в этом чате.")
        return

    # Получаем имя пользователя, которого нужно забанить
    username = message.get_args()

    # Получаем id пользователя по его имени
    user_id = await get_user_id_by_username(username)

    if not user_id:
        await message.answer(f"Не удалось найти пользователя {username}.")
        return

    # Запрашиваем у пользователя причину бана
    await message.answer(f"Введите причину бана для пользователя {username}:")

    # Ожидаем ответ от пользователя с причиной бана
    reason_message = await dp.bot.wait_for('message', timeout=120, chat_id=message.chat.id)

    # Баним пользователя
    await dp.bot.kick_chat_member(message.chat.id, user_id)

    # Отправляем сообщение о бане
    ban_message = f"Пользователь {username} был забанен администратором {message.from_user.get_mention(as_html=True)}"

    # Добавляем причину бана, если она была указана
    if reason_message.text:
        ban_message += f" по причине: {reason_message.text}"

    # Отвечаем на сообщение оригинального сообщения и отправляем сообщение о бане
    await message.reply_to_message.reply(ban_message)

@dp.message_handler(commands=['tmute'])
async def tempmute_command(message: types.Message):
    # Проверяем, что команду запустил админ
    if not await is_admin(message):
        await message.reply("У вас нет прав на использование этой команды.")
        return

    # Проверяем, что указано имя пользователя
    if len(message.text.split()) < 3:
        await message.reply("Использование: /tmute @username время_в_минутах")
        return

    # Получаем имя пользователя из аргументов команды
    username = message.text.split()[1]

    # Получаем время мута из аргументов команды
    try:
        duration = int(message.text.split()[2])
    except ValueError:
        await message.reply("Использование: /tmute @username время_в_минутах")
        return

    # Получаем объект чата, в котором нужно произвести мут
    chat = await get_chat_for_action(message)

    # Получаем объект пользователя, которого нужно замутить
    user = await get_user_by_username(username)

    # Производим мут пользователя на указанное время
    await chat.restrict(user.id, ChatPermissions(), until_date=time.time() + duration*60)

    # Отправляем сообщение о том, что пользователь замучен
    if duration > 0:
        await message.reply(f"Пользователь {user.get_mention(as_html=True)} замучен на {duration} минут.")
    else:
        await message.reply(f"Пользователь {user.get_mention(as_html=True)} замучен навсегда.")

@dp.message_handler(commands=['mute'])
async def mute_command(message: types.Message):
    # Проверяем, что команду запустил админ
    if not await is_admin(message):
        await message.reply("У вас нет прав на использование этой команды.")
        return

    # Проверяем, что указано имя пользователя
    if len(message.text.split()) < 2:
        await message.reply("Использование: /mute @username")
        return

    # Получаем имя пользователя из аргументов команды
    username = message.text.split()[1]

    # Получаем объект чата, в котором нужно произвести мут
    chat = await get_chat_for_action(message)

    # Получаем объект пользователя, которого нужно замутить
    user = await get_user_by_username(username)

    # Производим перманентный мут пользователя
    await chat.restrict(user.id, ChatPermissions())

    # Отправляем сообщение о том, что пользователь замучен
    await message.reply(f"Пользователь {user.get_mention(as_html=True)} замучен навсегда.")

@dp.message_handler(commands=["unban"])
async def unban_user_command(message: types.Message):
    if not message.reply_to_message:
        # Если сообщение не является ответом, попросить у пользователя уточнение, кого разбанить
        await message.answer("Укажите, кого нужно разбанить, используя команду в формате /unban @username или /unban id_username.")
        return

    user_id = message.reply_to_message.from_user.id
    try:
        # Попытаться преобразовать аргумент команды в int, если не получится, считать его именем пользователя
        user_input = message.text.split()[1]
        user_id = int(user_input[3:]) if user_input.startswith("id_") else user_input[1:]
    except (IndexError, ValueError):
        await message.answer("Укажите, кого нужно разбанить, используя команду в формате /unban @username или /unban id_username.")
        return

    chat_id = message.chat.id
    try:
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        await message.answer(f"Пользователь {user_input} был разбанен.")
    except Exception as e:
        await message.answer(f"Не удалось разбанить пользователя {user_input}. Ошибка: {e}")

@dp.message_handler(commands=['unmute'])
async def unmute_user(message: types.Message):
    if not await is_admin(message):
        await message.answer("У вас нет прав на выполнение этой команды.")
        return

    # Получаем username или ID пользователя
    try:
        user_id = message.text.split()[1].strip('@')
    except IndexError:
        await message.answer("Использование: /unmute @username or id_username")
        return

    # Получаем объект пользователя
    user = await bot.get_chat_member(message.chat.id, user_id)

    # Размутим пользователя
    await bot.restrict_chat_member(
        message.chat.id,
        user_id=user.user.id,
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )

    await message.answer(f"Пользователь {user.user.get_mention(as_html=True)} был размучен.")

import logging

async def analyze_message(message):
    message_text = message.text[:1024]
    api = OpenAI_API(api_key=openaiapi_key, api_base="https://api.openai.com/v1")
    try:
        response = await api.create_completion(
            model="davinci",
            prompt=(f"Is this message appropriate for the chat?\n\n{message_text}\n\nAnswer yes or no."),
            temperature=0.5,
            max_tokens=1,
        )
        answer = response['choices'][0]['text'].strip()
        await message.answer(f"Ответ сервера:\n {json.dumps(response)}")
        if answer == "no":
            if re.search(r"\b(идиот|дурак|урод|долбоеб|кретин)\b", message_text, re.IGNORECASE):
                await message.delete()
            else:
                await message.answer("Ваше сообщение содержит темы, связанные с религией или политикой, которые могут вызвать споры и конфликты в чате. Пожалуйста, не обсуждайте эти темы здесь.")
    except Exception as e:
        await message.answer(f"Error: {e}")
        print(f"Error: {e}")

# Пример использования функции analyze_message
@dp.message_handler()
async def handle_message(message: types.Message):
    # Анализируем сообщение
    await analyze_message(message)
  
if __name__ == '__main__':
    executor.start_polling(dp)
