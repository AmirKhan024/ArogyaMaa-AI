"""
Doctor AI Assistant - Clinical Decision Support

Non-RAG AI assistant for doctors working within the ArogyaMaa platform.
Provides AI explainability and case context analysis.

IMPORTANT: This assistant supports, not replaces, clinical judgment.
"""

import os
import json
import logging
from typing import Dict, Optional, List
from datetime import datetime
from groq import Groq

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# MASTER SYSTEM PROMPT - Clinical Decision Support
DOCTOR_SYSTEM_PROMPT = """You are a clinical decision-support assistant.

You must:
- Summarize patient data clearly
- Explain AI reasoning transparently
- Highlight trends and abnormalities
- Avoid diagnosis or treatment advice
- Use professional medical language
- Defer all decisions to the doctor

ABSOLUTE SAFETY RULES (NON-NEGOTIABLE):
❌ No diagnosis
❌ No medication recommendations or dosages
❌ No treatment plans
❌ No reassurance about outcomes
✅ Explain AI reasoning clearly
✅ Present facts, trends, and flags only
✅ Always defer final decision to doctor
✅ Maintain professional clinical tone

If uncertain, state uncertainty explicitly.

Return ONLY valid JSON in this format:
{
  "case_summary": "Brief factual summary of pregnancy and current status",
  "key_abnormal_findings": ["Abnormal finding with value and reference"],
  "trend_observations": ["Clear trend description over time"],
  "ai_flag_reasoning": "Why the AI system marked this case as high/moderate risk",
  "urgency_level": "LOW / MODERATE / HIGH / CRITICAL",
  "doctor_note": "This is AI-assisted screening. Clinical judgment required."
}

No extra text outside JSON."""


class DoctorAIAssistant:
    """
    AI Assistant for Doctor Portal - Case Analysis & Explainability
    
    This assistant:
    - Summarizes maternal cases
    - Explains AI risk flagging reasoning
    - Highlights abnormal values and trends
    - Provides urgency levels
    - Maintains clinical safety boundaries
    """
    
    def __init__(self):
        """Initialize the Doctor AI Assistant."""
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY required for Doctor AI Assistant")
        
        self.llm_client = Groq(api_key=groq_api_key)
        self.model = "llama-3.1-8b-instant"
        
        logger.info("✓ Doctor AI Assistant initialized")
    
    def analyze_case(self, case_data: Dict) -> Dict:
        """
        Analyze a maternal health case and provide structured insights.
        
        Args:
            case_data: Dictionary containing:
                - mother_info: Basic mother information
                - current_vitals: Latest vital signs
                - symptoms: Current symptoms
                - gestational_age: Weeks of pregnancy
                - historical_vitals: List of past vitals with timestamps
                - ai_risk_score: Current AI risk assessment
                - assessments: Past assessment data
                
        Returns:
            Structured JSON response with case analysis
        """
        logger.info(f"\n{'='*70}")
        logger.info("Doctor AI Assistant - Case Analysis")
        logger.info(f"{'='*70}")
        
        # Build the case context prompt
        case_prompt = self._build_case_prompt(case_data)
        
        try:
            logger.info("Calling Groq LLM for case analysis...")
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DOCTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": case_prompt}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            logger.info("✓ Case analysis completed")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return self._get_error_response("Unable to parse AI response")
            
        except Exception as e:
            logger.error(f"Error in case analysis: {e}")
            return self._get_error_response(str(e))
    
    def _build_case_prompt(self, case_data: Dict) -> str:
        """Build structured prompt from case data with full assessment history."""
        
        prompt_parts = ["Analyze this maternal health case:\n"]
        
        # Mother Information
        mother_info = case_data.get('mother_info', {})
        if mother_info:
            prompt_parts.append(f"PATIENT INFO:")
            prompt_parts.append(f"- Name: {mother_info.get('name', 'Unknown')}")
            prompt_parts.append(f"- Age: {mother_info.get('age', 'Unknown')}")
            prompt_parts.append(f"- Gestational Age: {case_data.get('gestational_age', 'Unknown')} weeks")
            prompt_parts.append(f"- Current Risk Level: {case_data.get('risk_level', 'Unknown')}")
            if mother_info.get('blood_group'):
                prompt_parts.append(f"- Blood Group: {mother_info.get('blood_group')}")
            prompt_parts.append("")
        
        # Current Vitals (from latest assessment)
        current_vitals = case_data.get('current_vitals', {})
        if current_vitals:
            prompt_parts.append("LATEST VITALS:")
            if current_vitals.get('bp_systolic') and current_vitals.get('bp_diastolic'):
                prompt_parts.append(f"- Blood Pressure: {current_vitals['bp_systolic']}/{current_vitals['bp_diastolic']} mmHg")
            if current_vitals.get('hemoglobin'):
                prompt_parts.append(f"- Hemoglobin: {current_vitals['hemoglobin']} g/dL")
            if current_vitals.get('weight'):
                prompt_parts.append(f"- Weight: {current_vitals['weight']} kg")
            if current_vitals.get('fetal_heart_rate'):
                prompt_parts.append(f"- Fetal Heart Rate: {current_vitals['fetal_heart_rate']} bpm")
            if current_vitals.get('pulse'):
                prompt_parts.append(f"- Pulse: {current_vitals['pulse']} bpm")
            if current_vitals.get('temperature'):
                prompt_parts.append(f"- Temperature: {current_vitals['temperature']}°C")
            if current_vitals.get('glucose'):
                prompt_parts.append(f"- Glucose: {current_vitals['glucose']} mg/dL")
            if current_vitals.get('oxygen_saturation'):
                prompt_parts.append(f"- SpO2: {current_vitals['oxygen_saturation']}%")
            prompt_parts.append("")
        
        # Current Symptoms
        symptoms = case_data.get('symptoms', [])
        if symptoms:
            prompt_parts.append("CURRENT SYMPTOMS:")
            for symptom in symptoms:
                prompt_parts.append(f"- {symptom}")
            prompt_parts.append("")
        
        # Latest AI Evaluation (if available)
        ai_eval = case_data.get('latest_ai_evaluation', {})
        if ai_eval:
            prompt_parts.append("LATEST AI EVALUATION:")
            prompt_parts.append(f"- Risk Level: {ai_eval.get('risk_level', 'Unknown')}")
            if ai_eval.get('risk_score'):
                prompt_parts.append(f"- Risk Score: {ai_eval.get('risk_score')}/100")
            if ai_eval.get('reasoning'):
                prompt_parts.append(f"- Reasoning: {ai_eval.get('reasoning')}")
            if ai_eval.get('recommendations'):
                prompt_parts.append(f"- Recommendations: {', '.join(ai_eval.get('recommendations', []))}")
            prompt_parts.append("")
        
        # Full Assessment History (most detailed)
        full_history = case_data.get('full_assessment_history', [])
        if full_history:
            prompt_parts.append(f"COMPLETE ASSESSMENT HISTORY ({len(full_history)} assessments):")
            for i, assessment in enumerate(full_history[:10], 1):  # Show up to 10 recent
                prompt_parts.append(f"\n  Assessment #{assessment.get('assessment_number', i)} - {assessment.get('date', 'Unknown')}:")
                if assessment.get('gestational_age_at_assessment'):
                    prompt_parts.append(f"    Gestational Age: {assessment['gestational_age_at_assessment']} weeks")
                
                # Vitals
                vitals = assessment.get('vitals', {})
                prompt_parts.append(f"    Vitals: BP={vitals.get('bp', 'N/A')}, Hb={vitals.get('hemoglobin', 'N/A')}, Weight={vitals.get('weight', 'N/A')}")
                if vitals.get('glucose') != 'N/A':
                    prompt_parts.append(f"    Glucose: {vitals.get('glucose')}, HR: {vitals.get('heart_rate', 'N/A')}")
                
                # Symptoms
                if assessment.get('symptoms'):
                    prompt_parts.append(f"    Symptoms: {', '.join(assessment['symptoms'])}")
                
                # Risk
                prompt_parts.append(f"    Risk Level: {assessment.get('risk_level', 'Unknown')}, Score: {assessment.get('risk_score', 'N/A')}")
                
                # ASHA notes
                if assessment.get('asha_notes'):
                    prompt_parts.append(f"    ASHA Notes: {assessment['asha_notes'][:100]}...")
                
                # AI recommendations
                if assessment.get('ai_recommendations'):
                    prompt_parts.append(f"    AI Recommendations: {', '.join(assessment['ai_recommendations'][:3])}")
            
            prompt_parts.append("")
        
        # Historical Vitals Trend
        historical_vitals = case_data.get('historical_vitals', [])
        if historical_vitals:
            prompt_parts.append("VITALS TREND (chronological):")
            for record in historical_vitals[-7:]:  # Last 7 records
                date = record.get('date', 'Unknown')
                bp = f"{record.get('bp_systolic', '?')}/{record.get('bp_diastolic', '?')}"
                hb = record.get('hemoglobin', '?')
                wt = record.get('weight', '?')
                prompt_parts.append(f"- {date}: BP={bp} mmHg, Hb={hb} g/dL, Weight={wt} kg")
            prompt_parts.append("")
        
        prompt_parts.append("Based on the complete assessment history above, provide your analysis in the required JSON format. Focus on:")
        prompt_parts.append("1. Key abnormal findings from the latest assessment")
        prompt_parts.append("2. Trends observed across all assessments")
        prompt_parts.append("3. Why the AI flagged this case")
        prompt_parts.append("4. Appropriate urgency level")
        
        return "\n".join(prompt_parts)
    
    def chat_about_case(self, case_data: Dict, question: str) -> str:
        """
        Answer doctor's questions about a patient's case in a conversational way.
        
        Allows doctors to ask about:
        - Comparison between assessments
        - Patient progress over time
        - Specific symptoms or vitals
        - Trend analysis
        
        Args:
            case_data: Complete case data from database
            question: Doctor's question
            
        Returns:
            AI response as a conversational string (no JSON/code)
        """
        logger.info(f"Doctor chat question: {question[:50]}...")
        
        # Build context from case data
        case_context = self._build_case_prompt(case_data)
        
        chat_prompt = f"""You are Dr. AI, a friendly clinical decision-support assistant helping a doctor review a maternal health case.

PATIENT DATA:
{case_context}

DOCTOR'S QUESTION:
{question}

RESPONSE GUIDELINES:
1. Answer in a natural, conversational tone - like a colleague explaining to another doctor
2. Be specific with dates, values, and comparisons
3. Use bullet points for lists, but keep the overall tone friendly
4. NEVER return JSON, code blocks, or technical formatting
5. Highlight concerning findings with clear language
6. If comparing assessments, create a clear before/after comparison
7. Keep responses concise but thorough (2-4 paragraphs max)
8. Use emojis sparingly for visual clarity (📈 for trends, ⚠️ for concerns)
9. Do NOT make diagnoses or treatment recommendations
10. End with a brief clinical note if relevant

Respond naturally as if having a conversation with the doctor:"""

        try:
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are Dr. AI, a friendly and knowledgeable clinical assistant. Always respond in plain, conversational English. Never use JSON, code blocks, or technical formatting. Be helpful and clear."},
                    {"role": "user", "content": chat_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            answer = response.choices[0].message.content
            
            # Clean up any accidental JSON/code formatting
            answer = answer.replace("```json", "").replace("```", "").strip()
            if answer.startswith("{") and answer.endswith("}"):
                # If it still returned JSON, provide a fallback
                answer = "I apologize, let me rephrase that in a clearer way. Based on the patient data, I can see there are some concerning trends that need attention. Could you please ask your question again so I can provide a more helpful response?"
            
            logger.info("✓ Chat response generated")
            return answer
            
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return f"I apologize, but I encountered an error processing your question. Please try again or rephrase your question."
    
    def _get_error_response(self, error_msg: str) -> Dict:
        """Return error response in expected format."""
        return {
            "case_summary": f"Error: {error_msg}",
            "key_abnormal_findings": [],
            "trend_observations": [],
            "ai_flag_reasoning": "Unable to complete analysis",
            "urgency_level": "UNDETERMINED",
            "doctor_note": "This is AI-assisted screening. Clinical judgment required."
        }
    
    def get_insufficient_data_response(self) -> Dict:
        """Response when data is insufficient."""
        return {
            "case_summary": "Insufficient longitudinal data available.",
            "key_abnormal_findings": [],
            "trend_observations": [],
            "ai_flag_reasoning": "Unable to assess trends due to limited data.",
            "urgency_level": "UNDETERMINED",
            "doctor_note": "Additional data required. Clinical judgment required."
        }


# Singleton instance
_doctor_assistant = None

def get_doctor_assistant() -> DoctorAIAssistant:
    """Get or create Doctor AI Assistant instance."""
    global _doctor_assistant
    if _doctor_assistant is None:
        _doctor_assistant = DoctorAIAssistant()
    return _doctor_assistant
