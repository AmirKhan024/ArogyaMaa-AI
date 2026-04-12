"""
AI Document Analyzer

Uses Groq Vision API to analyze medical documents (lab reports, scans, prescriptions).
Extracts key findings, abnormal values, and provides clinical insights.
"""

import os
import base64
from groq import Groq
from typing import Dict, Optional
import json


def analyze_medical_document(image_path: str, document_type: str, description: str = "") -> Dict:
    """
    Analyze a medical document using OCR + Groq AI.
    
    Args:
        image_path: Path to the document image
        document_type: Type of document (lab_report, ultrasound, prescription, xray, other)
        description: Optional description provided by uploader
    
    Returns:
        Dictionary containing:
            - key_findings: List of main findings
            - abnormal_values: List of abnormal test results
            - clinical_summary: Brief clinical interpretation
            - recommendations: List of recommendations
            - extracted_text: Text extracted from document
    """
    try:
        # Initialize Groq client
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            return {
                "error": "GROQ_API_KEY not configured",
                "key_findings": [],
                "abnormal_values": [],
                "clinical_summary": "AI analysis unavailable",
                "recommendations": [],
                "extracted_text": ""
            }
        
        # First, try to use pytesseract for OCR if available
        extracted_text = ""
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            extracted_text = pytesseract.image_to_string(img)
            print(f"[DOCUMENT ANALYZER] OCR extracted {len(extracted_text)} characters")
        except Exception as ocr_error:
            print(f"[DOCUMENT ANALYZER] OCR failed, will use AI-only analysis: {ocr_error}")
            # If OCR fails, create a sample analysis template
            extracted_text = f"""Unable to extract text from image (OCR not available).

Document Type: {document_type.replace('_', ' ').title()}
Description: {description if description else 'No description provided'}

IMPORTANT: Since OCR is unavailable, please provide a SAMPLE analysis for a typical {document_type.replace('_', ' ')} 
relevant to maternal health. Include common parameters and normal/abnormal value examples."""
        
        client = Groq(api_key=api_key)
        
        # Create analysis prompt based on document type with extracted text
        prompt_prefix = f"Analyze this {document_type.replace('_', ' ')} based on the extracted text below.\n\n"
        if description:
            prompt_prefix += f"Description: {description}\n\n"
        prompt_prefix += f"Extracted Text:\n{extracted_text}\n\n"
        
        prompts = {
            'lab_report': prompt_prefix + """Based on the extracted lab report text above, provide analysis in this format:

1. **Key Findings**: List all test results with their values
2. **Abnormal Values**: Identify any results outside normal ranges (mark with ⚠️)
3. **Clinical Summary**: Brief interpretation for maternal health (pregnancy context)
4. **Recommendations**: Specific actions needed based on results

Focus on pregnancy-relevant tests: Hemoglobin, Blood Pressure, Glucose, Protein, Blood group, RH factor, TSH, etc.

Return ONLY a valid JSON object with this exact structure:
{
  "key_findings": ["Test Name: Value Unit (Normal: X-Y)"],
  "abnormal_values": ["⚠️ Test Name: Value (Expected: X-Y, Status: High/Low, Severity: Mild/Moderate/Severe)"],
  "clinical_summary": "Brief clinical interpretation in 2-3 sentences",
  "recommendations": ["Specific action 1", "Specific action 2"]
}""",
            
            'ultrasound': prompt_prefix + """Based on the extracted ultrasound report text above, provide analysis:

1. **Key Findings**: Gestational age, fetal measurements, placenta position, amniotic fluid
2. **Abnormal Findings**: Any concerning observations
3. **Clinical Summary**: Brief interpretation
4. **Recommendations**: Follow-up actions needed

Return ONLY a valid JSON object:
{
  "key_findings": ["Gestational age: X weeks", "Fetal measurements: ...", "Placenta: ...", "Amniotic fluid: ..."],
  "abnormal_values": ["⚠️ Any concerning finding"],
  "clinical_summary": "Brief interpretation",
  "recommendations": ["Action 1", "Action 2"]
}""",
            
            'prescription': prompt_prefix + """Based on the extracted prescription text above, provide analysis:

1. **Medications**: List all prescribed drugs with dosages
2. **Special Instructions**: Timing, precautions
3. **Duration**: Treatment duration
4. **Warnings**: Pregnancy safety category, contraindications

Return ONLY a valid JSON object:
{
  "key_findings": ["Drug name: Dosage, Frequency, Duration"],
  "abnormal_values": ["⚠️ Any pregnancy contraindications or warnings"],
  "clinical_summary": "Brief summary of prescription purpose",
  "recommendations": ["Follow-up action 1", "Precaution 1"]
}""",
            
            'other': prompt_prefix + """Based on the extracted medical document text above, provide analysis:

1. **Key Information**: Main findings or data points
2. **Important Values**: Any measurements or test results
3. **Clinical Relevance**: How this relates to maternal health
4. **Next Steps**: Recommended actions

Return ONLY a valid JSON object:
{
  "key_findings": ["Finding 1", "Finding 2"],
  "abnormal_values": ["⚠️ Any concerning values"],
  "clinical_summary": "Brief interpretation",
  "recommendations": ["Action 1", "Action 2"]
}"""
        }
        
        prompt = prompts.get(document_type, prompts['other'])
        
        # Call Groq AI with text-only model (much faster and more reliable)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Fast, reliable text model
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert medical document analyzer. Analyze medical documents and return structured JSON responses."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,
            max_tokens=2000,
            top_p=0.9
        )
        
        # Parse response
        result_text = response.choices[0].message.content
        print(f"[DOCUMENT ANALYZER] AI Response: {result_text[:500]}")  # Debug output
        
        # Try to extract JSON from response
        try:
            # Find JSON object in response
            start_idx = result_text.find('{')
            end_idx = result_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = result_text[start_idx:end_idx]
                analysis = json.loads(json_str)
                print(f"[DOCUMENT ANALYZER] Parsed JSON successfully: {len(analysis.get('key_findings', []))} findings")
            else:
                print(f"[DOCUMENT ANALYZER] No JSON found in response, using fallback")
                # Fallback: create structured response from text
                analysis = {
                    "key_findings": [result_text[:200]],
                    "abnormal_values": [],
                    "clinical_summary": result_text[:300],
                    "recommendations": ["Review with healthcare provider"]
                }
        except json.JSONDecodeError:
            # If JSON parsing fails, return raw text in structured format
            analysis = {
                "key_findings": [result_text[:200]],
                "abnormal_values": [],
                "clinical_summary": result_text[:300],
                "recommendations": ["Review with healthcare provider"]
            }
        
        # Ensure all required fields exist
        analysis.setdefault('key_findings', [])
        analysis.setdefault('abnormal_values', [])
        analysis.setdefault('clinical_summary', 'Analysis completed')
        analysis.setdefault('recommendations', [])
        analysis['extracted_text'] = extracted_text  # Add the OCR text
        
        return analysis
    
    except Exception as e:
        print(f"[DOCUMENT ANALYZER] Error: {e}")
        return {
            "error": str(e),
            "key_findings": [],
            "abnormal_values": [],
            "clinical_summary": f"Analysis failed: {str(e)}",
            "recommendations": ["Manual review required"],
            "extracted_text": ""
        }


def analyze_document_from_base64(base64_data: str, document_type: str, description: str = "") -> Dict:
    """
    Analyze a medical document from base64 encoded image.
    
    Args:
        base64_data: Base64 encoded image data
        document_type: Type of document
        description: Optional description
    
    Returns:
        Analysis results dictionary
    """
    # Save temporarily and analyze
    import tempfile
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
        tmp_path = tmp_file.name
        
        # Decode and save
        image_bytes = base64.b64decode(base64_data)
        tmp_file.write(image_bytes)
    
    try:
        result = analyze_medical_document(tmp_path, document_type, description)
        return result
    finally:
        # Clean up temp file
        import os
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
