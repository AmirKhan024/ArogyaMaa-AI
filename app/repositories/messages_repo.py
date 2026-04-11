"""
Messages Repository

Data access layer for the 'messages' collection.
Stores unified chat history (Telegram + system messages).
"""

from bson import ObjectId
from datetime import datetime
from app.db import get_collection


def create(message_data):
    """
    Create a single standalone message.
    
    Args:
        message_data: Dictionary with message fields
    
    Returns:
        ObjectId of created message
    """
    messages = get_collection('messages')
    
    # Ensure timestamps
    if 'timestamp' not in message_data:
        message_data['timestamp'] = datetime.utcnow()
    
    result = messages.insert_one(message_data)
    return result.inserted_id


def create_thread(mother_id):
    """
    Create a new message thread for a mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        ObjectId of the created message thread
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    thread_data = {
        'mother_id': mother_id,
        'messages': [],
        'created_at': datetime.utcnow(),
        'last_message_at': datetime.utcnow(),
        'total_messages': 0
    }
    
    result = messages.insert_one(thread_data)
    return result.inserted_id


def get_by_mother_id(mother_id):
    """
    Get the message thread for a specific mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        Message thread document or None if not found
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    return messages.find_one({'mother_id': mother_id})


def add_message(mother_id, message_data):
    """
    Add a message to a mother's chat thread.
    
    Args:
        mother_id: ObjectId or string representation
        message_data: Dictionary containing message information
            Required fields:
                - sender_type: str ('mother', 'asha', 'doctor', 'ai', 'system')
                - text: str
            Optional fields:
                - sender_id: ObjectId
                - sender_name: str
                - telegram_message_id: int
                - is_alert: bool
                - alert_type: str
    
    Returns:
        True if added, False if thread not found
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    # Generate message ID
    import uuid
    message_data['message_id'] = f"msg_{uuid.uuid4().hex[:8]}"
    message_data['timestamp'] = datetime.utcnow()
    message_data.setdefault('read_by_mother', False)
    message_data.setdefault('read_at', None)
    
    result = messages.update_one(
        {'mother_id': mother_id},
        {
            '$push': {'messages': message_data},
            '$set': {'last_message_at': datetime.utcnow()},
            '$inc': {'total_messages': 1}
        }
    )
    
    return result.modified_count > 0


def get_messages(mother_id, limit=None, skip=0):
    """
    Get messages from a mother's chat thread.
    
    Args:
        mother_id: ObjectId or string representation
        limit: Maximum number of messages to return (optional)
        skip: Number of messages to skip (for pagination)
    
    Returns:
        List of message objects (most recent first)
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    # Use aggregation to slice the messages array
    pipeline = [
        {'$match': {'mother_id': mother_id}},
        {'$project': {
            'messages': {
                '$reverseArray': '$messages'  # Reverse to get newest first
            }
        }}
    ]
    
    if skip > 0:
        pipeline.append({'$project': {
            'messages': {'$slice': ['$messages', skip, limit or 1000]}
        }})
    elif limit:
        pipeline.append({'$project': {
            'messages': {'$slice': ['$messages', limit]}
        }})
    
    result = list(messages.aggregate(pipeline))
    
    if result:
        return result[0].get('messages', [])
    return []


def get_by_mother(mother_id, sender_type=None, limit=None):
    """
    Get messages for a mother, optionally filtered by sender type.
    
    Args:
        mother_id: ObjectId or string representation
        sender_type: Optional filter by sender_type ('doctor', 'asha', 'system', etc.)
        limit: Maximum number of messages to return
    
    Returns:
        List of message objects (most recent first)
    """
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    # Get all messages for this mother
    all_messages = get_messages(mother_id)
    
    # Filter by sender_type if provided
    if sender_type:
        filtered_messages = [
            msg for msg in all_messages 
            if msg.get('sender_type') == sender_type
        ]
    else:
        filtered_messages = all_messages
    
    # Apply limit
    if limit:
        filtered_messages = filtered_messages[:limit]
    
    return filtered_messages


def mark_as_read(mother_id, message_id):
    """
    Mark a specific message as read by the mother.
    
    Args:
        mother_id: ObjectId or string representation
        message_id: Message ID (string)
    
    Returns:
        True if marked, False if not found
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = messages.update_one(
        {
            'mother_id': mother_id,
            'messages.message_id': message_id
        },
        {
            '$set': {
                'messages.$.read_by_mother': True,
                'messages.$.read_at': datetime.utcnow()
            }
        }
    )
    
    return result.modified_count > 0


def mark_all_as_read(mother_id):
    """
    Mark all messages as read for a mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        True if updated, False if not found
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    # Get all messages
    thread = messages.find_one({'mother_id': mother_id})
    if not thread:
        return False
    
    # Update all unread messages
    updated_messages = []
    for msg in thread.get('messages', []):
        if not msg.get('read_by_mother', False):
            msg['read_by_mother'] = True
            msg['read_at'] = datetime.utcnow()
        updated_messages.append(msg)
    
    result = messages.update_one(
        {'mother_id': mother_id},
        {'$set': {'messages': updated_messages}}
    )
    
    return result.modified_count > 0


def get_unread_count(mother_id):
    """
    Get count of unread messages for a mother.
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        Number of unread messages
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    thread = messages.find_one({'mother_id': mother_id})
    if not thread:
        return 0
    
    unread_count = sum(
        1 for msg in thread.get('messages', [])
        if not msg.get('read_by_mother', False) and msg.get('sender_type') != 'mother'
    )
    
    return unread_count


def get_recent_threads(limit=10):
    """
    Get most recently active message threads.
    
    Args:
        limit: Maximum number of threads to return
    
    Returns:
        List of message thread documents (most recent first)
    """
    messages = get_collection('messages')
    
    return list(messages.find().sort('last_message_at', -1).limit(limit))


def delete_thread(mother_id):
    """
    Delete a message thread (use with caution).
    
    Args:
        mother_id: ObjectId or string representation
    
    Returns:
        True if deleted, False if not found
    """
    messages = get_collection('messages')
    
    if isinstance(mother_id, str):
        mother_id = ObjectId(mother_id)
    
    result = messages.delete_one({'mother_id': mother_id})
    
    return result.deleted_count > 0


def list_by_recipient(recipient_id, recipient_type='asha', limit=None):
    """
    Get all messages sent to a specific recipient (ASHA worker or doctor).
    
    Args:
        recipient_id: ObjectId or string representation
        recipient_type: 'asha' or 'doctor'
        limit: Maximum number of messages (optional)
    
    Returns:
        List of message documents (most recent first)
    """
    messages = get_collection('messages')
    
    if isinstance(recipient_id, str):
        recipient_id = ObjectId(recipient_id)
    
    # Build query based on recipient type
    if recipient_type == 'asha':
        query = {'to_asha_id': recipient_id}
    elif recipient_type == 'doctor':
        query = {'to_doctor_id': recipient_id}
    else:
        return []
    
    cursor = messages.find(query).sort('timestamp', -1)
    
    if limit:
        cursor = cursor.limit(limit)
    
    return list(cursor)
