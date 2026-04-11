"""
Telegram Service

Core Telegram bot functionality for sending messages and handling interactions.
Uses python-telegram-bot library for Telegram API integration.
"""

import requests
from flask import current_app


def send_message(chat_id, text, parse_mode='HTML'):
    """
    Send a text message to a Telegram user.
    
    Args:
        chat_id: Telegram chat ID (string or int)
        text: Message text to send
        parse_mode: Message formatting ('HTML', 'Markdown', or None)
    
    Returns:
        dict: Telegram API response or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    
    if parse_mode:
        payload['parse_mode'] = parse_mode
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to send message to {chat_id}: {e}")
        return None


def send_formatted_message(chat_id, text, reply_markup=None):
    """
    Send a formatted message with optional keyboard markup.
    
    Args:
        chat_id: Telegram chat ID
        text: Message text
        reply_markup: Keyboard markup (optional)
    
    Returns:
        dict: Telegram API response or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        payload['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to send formatted message: {e}")
        return None


def get_file_path(file_id):
    """
    Get file path from Telegram servers.
    
    Args:
        file_id: Telegram file ID
    
    Returns:
        str: File path on Telegram servers or None
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/getFile"
    
    try:
        response = requests.get(url, params={'file_id': file_id}, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get('ok'):
            return result['result']['file_path']
        return None
    except Exception as e:
        current_app.logger.error(f"Failed to get file path: {e}")
        return None


def download_file(file_path, save_path):
    """
    Download file from Telegram servers.
    
    Args:
        file_path: File path from getFile API
        save_path: Local path to save file
    
    Returns:
        bool: True if downloaded successfully
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            f.write(response.content)
        
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to download file: {e}")
        return False


def set_webhook(webhook_url):
    """
    Set the Telegram webhook URL.
    
    Args:
        webhook_url: Full URL where Telegram should send updates
    
    Returns:
        bool: True if webhook set successfully, False otherwise
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    
    payload = {
        'url': webhook_url
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        
        if result.get('ok'):
            current_app.logger.info(f"✓ Webhook set: {webhook_url}")
            return True
        else:
            current_app.logger.error(f"✗ Webhook failed: {result}")
            return False
    except Exception as e:
        current_app.logger.error(f"Failed to set webhook: {e}")
        return False


def get_webhook_info():
    """
    Get current webhook information.
    
    Returns:
        dict: Webhook info or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to get webhook info: {e}")
        return None


def delete_webhook():
    """
    Delete the current webhook.
    
    Returns:
        bool: True if deleted successfully, False otherwise
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    
    try:
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        current_app.logger.info("✓ Webhook deleted")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to delete webhook: {e}")
        return False


def get_bot_info():
    """
    Get information about the bot.

    Returns:
        dict: Bot information or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/getMe"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to get bot info: {e}")
        return None


def send_voice(chat_id, voice_file_path):
    """
    Send a voice message to a Telegram user.

    Args:
        chat_id: Telegram chat ID
        voice_file_path: Local path to the OGG voice file

    Returns:
        dict: Telegram API response or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/sendVoice"

    try:
        with open(voice_file_path, 'rb') as voice_file:
            response = requests.post(
                url,
                data={'chat_id': chat_id},
                files={'voice': voice_file},
                timeout=30
            )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to send voice to {chat_id}: {e}")
        return None


def answer_callback_query(callback_query_id, text=None):
    """
    Answer a callback query to remove the loading indicator.

    Args:
        callback_query_id: ID of the callback query
        text: Optional notification text to show

    Returns:
        dict: Telegram API response or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"

    payload = {'callback_query_id': callback_query_id}
    if text:
        payload['text'] = text

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to answer callback query: {e}")
        return None


def send_message_with_keyboard(chat_id, text, reply_markup, parse_mode=None):
    """
    Send a message with any type of keyboard markup (inline or reply).

    Args:
        chat_id: Telegram chat ID
        text: Message text
        reply_markup: Keyboard markup dict (InlineKeyboardMarkup, ReplyKeyboardMarkup, or ReplyKeyboardRemove)
        parse_mode: Optional parse mode ('HTML', 'Markdown')

    Returns:
        dict: Telegram API response or None if failed
    """
    bot_token = current_app.config['TELEGRAM_BOT_TOKEN']
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        'chat_id': chat_id,
        'text': text,
    }

    if parse_mode:
        payload['parse_mode'] = parse_mode
    if reply_markup:
        payload['reply_markup'] = reply_markup

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        current_app.logger.error(f"Failed to send message with keyboard: {e}")
        return None
