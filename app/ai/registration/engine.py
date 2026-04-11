"""
Registration Engine

AI-driven state machine that determines the next registration question,
extracts answers from user messages via LLM, and handles dynamic skipping
and identity confirmation rollback.
"""

import json
from app.ai.registration.assistant import AIAssistant
from app.ai.registration.questions import REGISTRATION_QUESTIONS


class RegistrationEngine:
    def __init__(self, ai_assistant: AIAssistant):
        self.ai = ai_assistant

    def provide_next_question(self, current_data: dict, last_message: str = None) -> tuple:
        """
        Determines the next question to ask and optionally extracts data from the last message.
        Returns: (extracted_json, next_question_text, is_complete, ui_details)
        """

        # 1. Identify which questions are still missing
        missing_questions = [q for q in REGISTRATION_QUESTIONS if q['id'] not in current_data or current_data[q['id']] is None]

        if not missing_questions:
            return {}, "आपका पंजीकरण पहले ही पूरा हो चुका है। धन्यवाद!", True, {"type": "text"}

        current_question = missing_questions[0]

        # 2. If there is a last_message, try to extract data from it via LLM
        extracted_data = {}
        if last_message:
            extraction_prompt = f"""You are a data extractor for a Maternal Health System (ArogyaMaa).
The user was asked: "{current_question['text']}"
User replied: "{last_message}"

Please extract the answer for "{current_question['id']}".
If the user also provided other information from the registration list, extract that too.
REGISTRATION FIELDS: {', '.join([q['id'] for q in REGISTRATION_QUESTIONS])}

CRITICAL: If you extract 'dob' (Date of Birth), please also mentally calculate the person's 'age' in integer years based on the current year 2026, and include BOTH 'dob' and 'age' in your returned JSON.

Return ONLY a JSON object with the extracted fields. If nothing was found, return {{}}.
"""
            raw_json = self.ai._call_groq(extraction_prompt, "You are a precise data extraction engine.")
            try:
                json_str = raw_json.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                extracted_data = json.loads(json_str)
            except:
                extracted_data = {}

        # Intercept negative confirmation to rollback
        if 'confirm_identity' in extracted_data:
            ans = str(extracted_data['confirm_identity']).lower()
            if 'no' in ans or 'false' in ans or 'नहीं' in ans:
                # Use None to override current state effectively in MongoDB update
                extracted_data['confirm_identity'] = None
                extracted_data['phone_number'] = None
                extracted_data['dob'] = None
                extracted_data['age'] = None

                # Send back the rollback UI immediately
                user_lang = current_data.get('preferred_language', 'Hindi')
                msg = "No problem! Let's start over, please share your phone number again:" if 'English' in user_lang else "कोई बात नहीं! कृपया अपना फोन नंबर फिर से साझा करें:"
                return extracted_data, msg, False, {"type": "contact"}

        # 3. Update data and check if the specific target question was answered
        updated_data = {**current_data, **extracted_data}

        # Dynamic Skipping Logic: If it is the first pregnancy, skip previous complication questions natively
        first_preg_val = str(updated_data.get('first_pregnancy', '')).lower()
        if first_preg_val and ('yes' in first_preg_val or 'हाँ' in first_preg_val or 'true' in first_preg_val):
            updated_data['previous_pregnancies_count'] = '0'
            updated_data['previous_complications'] = 'No'
            extracted_data['previous_pregnancies_count'] = '0'
            extracted_data['previous_complications'] = 'No'

        # Did we successfully get the answer to WHAT WE JUST ASKED?
        target_field = current_question['id']
        was_target_answered = target_field in updated_data and updated_data[target_field] is not None

        new_missing = [q for q in REGISTRATION_QUESTIONS if q['id'] not in updated_data or updated_data[q['id']] is None]

        if not new_missing:
            user_lang = updated_data.get('preferred_language', 'Hindi')
            comp_msg = "Your registration is already complete. Thank you!" if 'English' in user_lang else "आपका पंजीकरण पहले ही पूरा हो चुका है। धन्यवाद!"
            return extracted_data, comp_msg, True, {"type": "text"}

        # Determine the next question to show
        next_q = new_missing[0]
        ui_details = {"type": next_q.get("ui_type", "text"), "options": next_q.get("options", [])}

        # Intercept condition before letting language generation take over
        if next_q['id'] == 'confirm_identity':
            name = updated_data.get('full_name', 'Unknown')
            age = updated_data.get('age', 'Unknown')
            phone = updated_data.get('phone_number', 'Unknown')
            lang = updated_data.get('preferred_language', 'Hindi')

            if 'English' in lang:
                custom_q = f"Let's confirm your details: Name: {name}, Age: {age}, Phone: {phone}. Is this correct?"
            else:
                custom_q = f"आपका नाम {name} है, आपकी उम्र {age} वर्ष है, और आपका फोन नंबर {phone} है। क्या यह सही है?"
            return extracted_data, custom_q, False, ui_details

        # 4. Generate a warm, dialect-appropriate asking string
        # If the user didn't answer what we asked, we re-ask with a slight clarification
        is_reasking = last_message and not was_target_answered

        user_lang = updated_data.get('preferred_language', 'Hindi')
        is_english = 'English' in user_lang

        script_constraint = "Speak ONLY in perfect English." if is_english else "Speak ONLY in Hindi using Devanagari script."
        character_constraint = "Use standard English characters." if is_english else "**NEVER USE ENGLISH WORDS OR CHARACTERSET**. No English script at all."

        dialect_prompt = f"""The user is registering in ArogyaMaa.
Next required question: "{next_q['text']}"
Is this a follow-up/re-ask because they missed the answer? {'Yes' if is_reasking else 'No'}

Your task:
1. {'Acknowledge their answer briefly but kindly remind them that you still need the answer to: ' + next_q['text'] if is_reasking else 'Ask the next question: ' + next_q['text']}
2. **STRICT CONSTRAINT**: {script_constraint}
3. {character_constraint}
4. Keep the response warm, like a caring village midwife, and under 15 words.
"""
        system_persona = "You are a village midwife helper who speaks empathetic English." if is_english else "You are a village midwife helper who speaks only the local dialect. You do not know English."
        empathetic_next_q = self.ai._call_groq(dialect_prompt, system_persona)

        # If it's the very first question after language, prepend the custom welcome.
        if target_field == 'preferred_language' and was_target_answered:
            name = updated_data.get('full_name', 'Mother')
            if is_english:
                welcome = f"Hi {name}, I am ArogyaSathi, your pregnancy friend."
            else:
                welcome = f"नमस्ते {name}, मैं हूँ आपकी ArogyaSathi, आपकी अपनी pregnancy friend।"
            empathetic_next_q = f"{welcome}\n\n{empathetic_next_q}"

        return extracted_data, empathetic_next_q, False, ui_details
