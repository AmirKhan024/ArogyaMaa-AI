"""
Telegram Bot Blueprint

Handles all Telegram webhook interactions.
Mothers interact with the system exclusively through this interface.

URL Prefix: /telegram
"""

from flask import Blueprint, request, jsonify, current_app
from app.services import telegram_handlers

telegram_bp = Blueprint('telegram', __name__)


@telegram_bp.route('/webhook', methods=['POST'])
def webhook():
    """
    Telegram webhook endpoint.
    
    Receives all updates from Telegram (messages, commands, documents, callbacks).
    This is where mothers interact with the system.
    
    Flow:
    1. Telegram sends POST request with update data
    2. Extract message/command/callback from update
    3. Route to appropriate handler
    4. Handler processes and responds via Telegram API
    """
    try:
        update = request.get_json()
        
        if not update:
            current_app.logger.warning("Received empty update from Telegram")
            return jsonify({"status": "ok"}), 200
        
        # Handle callback queries (inline keyboard button presses)
        if 'callback_query' in update:
            callback_query = update['callback_query']
            result = telegram_handlers.handle_callback_query(callback_query)
            current_app.logger.info(f"Callback query handled: {result}")
            return jsonify({"status": "ok"}), 200
        
        # Extract message data
        message = update.get('message')
        if not message:
            # Could be edited_message, channel_post, etc. - ignore for now
            return jsonify({"status": "ok"}), 200
        
        chat_id = message.get('chat', {}).get('id')
        user_info = message.get('from', {})
        text = message.get('text', '')
        
        if not chat_id:
            current_app.logger.warning("No chat_id in update")
            return jsonify({"status": "ok"}), 200
        
        # Handle voice messages (used during AI registration)
        if 'voice' in message:
            current_app.logger.info(f"[TELEGRAM] Voice message received from {chat_id}")
            try:
                from app.repositories import registration_repo
                session = registration_repo.get_session(str(chat_id))
                if session and session.get('registration_active'):
                    result = telegram_handlers.handle_registration_voice(chat_id, message['voice'])
                    current_app.logger.info(f"[TELEGRAM] Voice registration result: {result}")
                else:
                    from app.services import telegram_service
                    telegram_service.send_message(
                        chat_id,
                        "🎤 Voice messages are supported during registration. Press the 📝 Register button to start."
                    )
            except Exception as e:
                current_app.logger.error(f"[TELEGRAM] Voice handling failed: {e}", exc_info=True)
            return jsonify({"status": "ok"}), 200

        # Handle contact sharing (used during AI registration for phone number)
        if 'contact' in message:
            current_app.logger.info(f"[TELEGRAM] Contact received from {chat_id}")
            try:
                from app.repositories import registration_repo
                session = registration_repo.get_session(str(chat_id))
                if session and session.get('registration_active'):
                    result = telegram_handlers.handle_registration_contact(chat_id, message['contact'])
                    current_app.logger.info(f"[TELEGRAM] Contact registration result: {result}")
            except Exception as e:
                current_app.logger.error(f"[TELEGRAM] Contact handling failed: {e}", exc_info=True)
            return jsonify({"status": "ok"}), 200

        # Handle document uploads (photos and files)
        if 'photo' in message:
            current_app.logger.info(f"[TELEGRAM] Photo received from {chat_id}, processing...")
            try:
                result = telegram_handlers.handle_document_upload(chat_id, message['photo'])
                current_app.logger.info(f"[TELEGRAM] Photo upload result: {result}")
            except Exception as e:
                current_app.logger.error(f"[TELEGRAM] Photo upload failed: {e}", exc_info=True)
            return jsonify({"status": "ok"}), 200
        
        if 'document' in message:
            current_app.logger.info(f"[TELEGRAM] Document received from {chat_id}, processing...")
            try:
                result = telegram_handlers.handle_document_upload(chat_id, message['document'])
                current_app.logger.info(f"[TELEGRAM] Document upload result: {result}")
            except Exception as e:
                current_app.logger.error(f"[TELEGRAM] Document upload failed: {e}", exc_info=True)
            return jsonify({"status": "ok"}), 200
        
        # Route based on message type
        if text.startswith('/'):
            # Command handling
            command = text.split()[0].lower()
            
            if command == '/start':
                result = telegram_handlers.handle_start_command(chat_id, user_info)
                current_app.logger.info(f"/start command: {result}")
            
            elif command == '/help':
                result = telegram_handlers.handle_help_command(chat_id)
                current_app.logger.info(f"/help command processed")
            
            elif command == '/status':
                result = telegram_handlers.handle_status_command(chat_id)
                current_app.logger.info(f"/status command processed")
            
            elif command == '/profile':
                result = telegram_handlers.handle_profile_command(chat_id)
                current_app.logger.info(f"/profile command processed")
            
            else:
                result = telegram_handlers.handle_unknown_command(chat_id, command)
                current_app.logger.info(f"Unknown command: {command}")
        
        else:
            # Regular text message
            result = telegram_handlers.handle_text_message(chat_id, text)
            current_app.logger.info(f"Text message from {chat_id}: {text[:50]}")
        
        return jsonify({"status": "ok"}), 200
    
    except Exception as e:
        current_app.logger.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@telegram_bp.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Telegram blueprint"""
    return jsonify({
        "service": "telegram",
        "status": "active"
    }), 200


@telegram_bp.route('/set_webhook', methods=['POST'])
def set_webhook():
    """
    Manually set Telegram webhook.
    
    Expects JSON body:
    {
        "webhook_url": "https://yourdomain.com/telegram/webhook"
    }
    """
    from app.services import telegram_service
    
    data = request.get_json()
    webhook_url = data.get('webhook_url')
    
    if not webhook_url:
        return jsonify({
            "status": "error",
            "message": "webhook_url is required"
        }), 400
    
    success = telegram_service.set_webhook(webhook_url)
    
    if success:
        return jsonify({
            "status": "success",
            "webhook_url": webhook_url
        }), 200
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to set webhook"
        }), 500


@telegram_bp.route('/webhook_info', methods=['GET'])
def webhook_info():
    """Get current webhook information"""
    from app.services import telegram_service
    
    info = telegram_service.get_webhook_info()
    
    if info:
        return jsonify(info), 200
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to get webhook info"
        }), 500


@telegram_bp.route('/bot_info', methods=['GET'])
def bot_info():
    """Get bot information"""
    from app.services import telegram_service
    
    info = telegram_service.get_bot_info()
    
    if info:
        return jsonify(info), 200
    else:
        return jsonify({
            "status": "error",
            "message": "Failed to get bot info"
        }), 500
