"""
AI Nutrition Advisor for Telegram Bot

Provides personalized, context-aware nutrition recommendations for pregnant mothers.
Uses:
- Current time of day (breakfast/lunch/dinner/snack)
- Latest health assessment and vitals
- Doctor messages and alerts
- Pregnancy stage (gestational week)
- Risk factors and AI analysis
"""

import os
from datetime import datetime
from typing import Dict, Optional
from groq import Groq
import json

from app.repositories import mothers_repo, assessments_repo, messages_repo, consultations_repo

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
DEFAULT_MODEL = "llama-3.1-8b-instant"


def get_time_context() -> Dict[str, str]:
    """Determine meal context based on current Indian time."""
    now = datetime.now()
    hour = now.hour
    
    if 5 <= hour < 10:
        return {
            "meal_type": "breakfast",
            "greeting": "Good morning",
            "time_specific": "Start your day with a nutritious breakfast"
        }
    elif 10 <= hour < 12:
        return {
            "meal_type": "mid_morning_snack",
            "greeting": "Good morning",
            "time_specific": "A healthy mid-morning snack will keep you energized"
        }
    elif 12 <= hour < 15:
        return {
            "meal_type": "lunch",
            "greeting": "Good afternoon",
            "time_specific": "Let's plan a balanced lunch for you"
        }
    elif 15 <= hour < 17:
        return {
            "meal_type": "afternoon_snack",
            "greeting": "Good afternoon",
            "time_specific": "A nutritious snack will help you stay active"
        }
    elif 17 <= hour < 21:
        return {
            "meal_type": "dinner",
            "greeting": "Good evening",
            "time_specific": "Let's prepare a healthy dinner"
        }
    else:
        return {
            "meal_type": "night_snack",
            "greeting": "Good evening",
            "time_specific": "If you're hungry, here's what you can have"
        }


def gather_health_context(mother_id) -> Dict:
    """
    Gather comprehensive health context for nutrition recommendations.
    
    Args:
        mother_id: Mother's ObjectId
        
    Returns:
        dict with health summary, vitals, alerts, doctor messages
    """
    mother = mothers_repo.get_by_id(mother_id)
    
    # Get latest assessment
    assessments = assessments_repo.list_by_mother(mother_id, limit=1)
    latest_assessment = assessments[0] if assessments else None
    
    # Get recent messages from doctor/ASHA
    recent_messages = messages_repo.get_messages(mother_id, limit=10)
    
    # Extract relevant information
    context = {
        "mother_name": mother.get('name', 'Mother'),
        "age": mother.get('age'),
        "gestational_week": None,
        "risk_level": "UNKNOWN",
        "vitals": {},
        "symptoms": [],
        "doctor_notes": [],
        "ai_concerns": [],
        "has_assessment": False
    }
    
    if latest_assessment:
        context["has_assessment"] = True
        vitals = latest_assessment.get('vitals', {})
        context["vitals"] = {
            "bp_systolic": vitals.get('bp_systolic'),
            "bp_diastolic": vitals.get('bp_diastolic'),
            "weight": vitals.get('weight') or vitals.get('weight_kg'),
            "hemoglobin": vitals.get('hemoglobin') or vitals.get('hemoglobin_g_dl'),
            "glucose": vitals.get('glucose_fasting') or vitals.get('glucose_random'),
            "temperature": vitals.get('temperature')
        }
        
        context["symptoms"] = latest_assessment.get('symptoms', [])
        context["gestational_week"] = latest_assessment.get('gestational_age_at_assessment')
        
        # AI evaluation
        ai_eval = latest_assessment.get('ai_evaluation', {})
        context["risk_level"] = ai_eval.get('risk_category', 'UNKNOWN')
        
        # Extract AI concerns
        risk_strat = ai_eval.get('agent_outputs', {}).get('risk_stratification', {})
        if risk_strat:
            context["ai_concerns"] = risk_strat.get('clinical_flags', [])
    
    # Get doctor consultation notes
    if latest_assessment and latest_assessment.get('reviewed_by_doctor'):
        consultation_id = latest_assessment.get('doctor_consultation_id')
        if consultation_id:
            consultation = consultations_repo.get_by_id(consultation_id)
            if consultation:
                context["doctor_notes"].append(consultation.get('notes', ''))
    
    # Extract doctor/ASHA messages
    for msg in recent_messages:
        if msg.get('sender_type') in ['doctor', 'asha']:
            sender_name = msg.get('sender_name', 'Healthcare Worker')
            msg_text = msg.get('text', '')
            if msg_text:
                context["doctor_notes"].append(f"{sender_name}: {msg_text}")
    
    return context


def generate_nutrition_recommendation(mother_id, query_text: str) -> str:
    """
    Generate personalized nutrition recommendation using AI.
    
    Args:
        mother_id: Mother's ObjectId
        query_text: User's original question/query
        
    Returns:
        Formatted nutrition recommendation message
    """
    try:
        # Get time context
        time_ctx = get_time_context()
        
        # Gather health context
        health_ctx = gather_health_context(mother_id)
        
    except Exception as e:
        print(f"[NUTRITION AI ERROR - Context Gathering] {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    
    # Build AI prompt
    system_prompt = """You are an expert maternal nutrition advisor for ArogyaMaa, an AI-assisted maternal health system in India.

Your role:
- Provide safe, evidence-based nutrition advice for pregnant women
- Consider Indian cuisine and locally available foods
- Adapt recommendations based on pregnancy stage, health conditions, and risks
- Be culturally sensitive and practical
- NEVER diagnose or prescribe medication
- Always recommend consulting doctor for medical concerns

Output format:
Provide recommendations in this structure:
{
  "greeting": "Warm, personalized greeting",
  "meal_suggestions": ["Specific food item 1 with portion", "Food item 2", "Food item 3"],
  "nutrition_focus": "Key nutrients to focus on and why",
  "foods_to_avoid": ["Food to avoid and reason"],
  "general_tips": ["Practical tip 1", "Practical tip 2"],
  "doctor_alert": "If health concern requires doctor consultation, state it here, else empty string"
}
"""
    
    user_prompt = f"""Mother's Query: "{query_text}"

Time Context:
- Current time: {time_ctx['meal_type']}
- {time_ctx['time_specific']}

Health Context:
- Name: {health_ctx['mother_name']}
- Age: {health_ctx.get('age', 'Unknown')}
- Gestational Week: {health_ctx.get('gestational_week', 'Unknown')}
- Risk Level: {health_ctx['risk_level']}

Vitals (Latest):
- Blood Pressure: {health_ctx['vitals'].get('bp_systolic')}/{health_ctx['vitals'].get('bp_diastolic')} mmHg
- Hemoglobin: {health_ctx['vitals'].get('hemoglobin')} g/dL
- Weight: {health_ctx['vitals'].get('weight')} kg
- Blood Glucose: {health_ctx['vitals'].get('glucose')}

Symptoms: {', '.join(health_ctx['symptoms']) if health_ctx['symptoms'] else 'None reported'}

AI Health Concerns: {', '.join(health_ctx['ai_concerns']) if health_ctx['ai_concerns'] else 'None'}

Doctor/ASHA Notes:
{chr(10).join(health_ctx['doctor_notes'][:3]) if health_ctx['doctor_notes'] else 'No recent notes'}

Based on this context, provide a personalized, detailed nutrition recommendation for this mother RIGHT NOW.
Focus on practical, affordable Indian foods she can eat today.
"""
    
    try:
        # Call Groq API
        response = groq_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        ai_output = json.loads(response.choices[0].message.content)
        
        # Format the response message
        formatted_msg = f"""
🍽️ <b>{time_ctx['greeting']}, {health_ctx['mother_name']}!</b>

{ai_output.get('greeting', '')}

<b>🥗 Recommended {time_ctx['meal_type'].replace('_', ' ').title()}:</b>
"""
        
        for item in ai_output.get('meal_suggestions', []):
            formatted_msg += f"• {item}\n"
        
        formatted_msg += f"\n<b>💊 Nutrition Focus:</b>\n{ai_output.get('nutrition_focus', '')}\n"
        
        if ai_output.get('foods_to_avoid'):
            formatted_msg += "\n<b>⚠️ Foods to Avoid:</b>\n"
            for item in ai_output['foods_to_avoid']:
                formatted_msg += f"• {item}\n"
        
        if ai_output.get('general_tips'):
            formatted_msg += "\n<b>💡 Tips:</b>\n"
            for tip in ai_output['general_tips']:
                formatted_msg += f"• {tip}\n"
        
        # Add health-based alerts
        if health_ctx['risk_level'] in ['HIGH', 'CRITICAL']:
            formatted_msg += f"\n<b>🔴 Important:</b> Your current risk level is {health_ctx['risk_level']}. Please follow your doctor's dietary instructions carefully.\n"
        
        if ai_output.get('doctor_alert'):
            formatted_msg += f"\n⚕️ <i>{ai_output['doctor_alert']}</i>\n"
        
        formatted_msg += "\n<i>💚 This advice is personalized based on your health data. Always consult your doctor for medical concerns.</i>"
        
        return formatted_msg
        
    except Exception as e:
        print(f"[NUTRITION AI ERROR] {str(e)}")
        # Fallback response
        return f"""
🍽️ {time_ctx['greeting']}, {health_ctx['mother_name']}!

{time_ctx['time_specific']}. Here are some general pregnancy nutrition tips:

<b>Focus on:</b>
• Iron-rich foods (spinach, lentils, dates)
• Calcium sources (milk, yogurt, cheese)
• Protein (dal, eggs, chicken, paneer)
• Fresh fruits and vegetables
• Plenty of water (8-10 glasses/day)

<b>Avoid:</b>
• Raw/undercooked foods
• Unpasteurized dairy
• Excessive caffeine
• Street food

💚 For personalized advice, please consult your ASHA worker or doctor.

Use /start to return to the main menu.
"""


def is_nutrition_query(text: str) -> bool:
    """
    Check if the message is asking about food/nutrition.
    
    Args:
        text: User's message text
        
    Returns:
        True if nutrition-related query
    """
    text_lower = text.lower()
    
    nutrition_keywords = [
        'eat', 'food', 'diet', 'nutrition', 'meal',
        'breakfast', 'lunch', 'dinner', 'snack',
        'hungry', 'appetite', 'recipe',
        'vitamin', 'calcium', 'iron', 'protein',
        'खाना', 'भोजन', 'आहार',  # Hindi keywords
        'kya khau', 'kya khana chahiye', 'kya khaye'
    ]
    
    return any(keyword in text_lower for keyword in nutrition_keywords)
