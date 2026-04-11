"""
Safety Filters & Query Validation for ASHA RAG

This module implements:
1. Query validation (detects unsafe queries)
2. Blocked query detection (medicines, diagnosis, treatment)
3. JSON schema validation
4. Safe refusal handling
5. Confidence scoring

SAFETY RULES:
- Block queries asking for medication recommendations
- Block queries asking for diagnosis
- Block queries about treatment decisions
- Block queries seeking safety reassurances
- Escalate ALL blocked queries to doctor
"""

import re
import logging
from typing import Dict, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QuerySafetyLevel(Enum):
    """Safety classification for queries."""
    SAFE = "safe"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"


class ASHAResponseSchema(BaseModel):
    """
    Pydantic schema for validating ASHA RAG responses.
    
    Ensures all responses follow required structure.
    """
    guidance: str = Field(..., min_length=10, description="Protocol guidance text")
    checklist: list[str] = Field(..., min_items=1, description="Action checklist")
    escalation_rule: str = Field(..., min_length=10, description="When to escalate to doctor")
    source_documents: list[str] = Field(default_factory=list, description="Source citations")
    disclaimer: str = Field(
        default="AI-assisted guidance only. Doctor verification required.",
        description="Safety disclaimer"
    )


class ASHASafetyFilter:
    """
    Safety filter for ASHA worker queries.
    
    Detects and blocks unsafe queries that violate ASHA scope:
    - Medication recommendations
    - Medical diagnosis
    - Treatment decisions
    - Safety reassurances
    """
    
    # Blocked query patterns
    MEDICATION_PATTERNS = [
        r'\b(medicine|medication|drug|tablet|pill|dose|dosage|mg|ml)\b',
        r'\b(paracetamol|aspirin|antibiotic|injection|vitamin|iron tablet)\b',
        r'\bwhat (medicine|drug|medication) (should|can|to)\b',
        r'\b(give|administer|prescribe) (medicine|drug|medication)\b',
    ]
    
    DIAGNOSIS_PATTERNS = [
        r'\b(diagnose|diagnosis|what (is|are) (the|this) (disease|condition|problem))\b',
        r'\b(does (she|mother) have|is (this|it) (a|an))\b.*\b(disease|condition|infection)\b',
        r'\bwhat (disease|illness|condition|infection)\b',
    ]
    
    TREATMENT_PATTERNS = [
        r'\b(treatment|treat|cure|therapy)\b',
        r'\b(how to treat|best treatment|treatment (for|of))\b',
        r'\bcan (i|we) treat\b',
    ]
    
    SAFETY_REASSURANCE_PATTERNS = [
        r'\b(is (it|this|baby|mother) safe|will (baby|mother) be (safe|okay|fine))\b',
        r'\b(don\'t worry|no need to worry|everything (will be|is) (fine|okay))\b',
        r'\b(can (i|we) (wait|delay)|should (i|we) wait)\b',
    ]
    
    DELAY_PATTERNS = [
        r'\bcan (i|we) (delay|postpone|wait)\b',
        r'\b(do|does) (it|this) (need|require) immediate\b',
        r'\bhow urgent\b',
    ]
    
    def __init__(self):
        """Initialize safety filter with compiled regex patterns."""
        # Compile all patterns for efficiency
        self.medication_regex = [re.compile(p, re.IGNORECASE) for p in self.MEDICATION_PATTERNS]
        self.diagnosis_regex = [re.compile(p, re.IGNORECASE) for p in self.DIAGNOSIS_PATTERNS]
        self.treatment_regex = [re.compile(p, re.IGNORECASE) for p in self.TREATMENT_PATTERNS]
        self.safety_regex = [re.compile(p, re.IGNORECASE) for p in self.SAFETY_REASSURANCE_PATTERNS]
        self.delay_regex = [re.compile(p, re.IGNORECASE) for p in self.DELAY_PATTERNS]
        
        logger.info("✓ Safety filter initialized with pattern matching")
    
    def validate_query(self, query: str) -> Tuple[QuerySafetyLevel, Optional[str]]:
        """
        Validate if query is safe for ASHA RAG system.
        
        Args:
            query: User's query text
            
        Returns:
            Tuple of (safety_level, reason)
            - safety_level: SAFE, BLOCKED, or UNCERTAIN
            - reason: Explanation if blocked
        """
        query_lower = query.lower().strip()
        
        # Check for medication queries
        for pattern in self.medication_regex:
            if pattern.search(query_lower):
                return (
                    QuerySafetyLevel.BLOCKED,
                    "Query requests medication recommendation. ASHA workers cannot prescribe medicines."
                )
        
        # Check for diagnosis queries
        for pattern in self.diagnosis_regex:
            if pattern.search(query_lower):
                return (
                    QuerySafetyLevel.BLOCKED,
                    "Query requests medical diagnosis. ASHA workers cannot diagnose conditions."
                )
        
        # Check for treatment queries
        for pattern in self.treatment_regex:
            if pattern.search(query_lower):
                return (
                    QuerySafetyLevel.BLOCKED,
                    "Query requests treatment decision. ASHA workers cannot make treatment decisions."
                )
        
        # Check for safety reassurance
        for pattern in self.safety_regex:
            if pattern.search(query_lower):
                return (
                    QuerySafetyLevel.BLOCKED,
                    "Query seeks safety reassurance. Only doctors can assess safety."
                )
        
        # Check for delay/urgency questions
        for pattern in self.delay_regex:
            if pattern.search(query_lower):
                return (
                    QuerySafetyLevel.UNCERTAIN,
                    "Query about delaying care. Always err on side of caution."
                )
        
        # Query is safe
        return (QuerySafetyLevel.SAFE, None)
    
    def get_blocked_response(self, query: str, reason: str) -> Dict:
        """
        Generate safe refusal response for blocked query.
        
        Args:
            query: Original query
            reason: Reason for blocking
            
        Returns:
            Structured response refusing query
        """
        return {
            "guidance": f"This query is outside ASHA worker scope. {reason}",
            "checklist": [
                "Do not attempt to answer this question yourself",
                "Do not provide any medical advice or recommendations",
                "Immediately refer the mother to a qualified doctor",
                "Document the concern in the assessment form"
            ],
            "escalation_rule": "Doctor consultation required immediately for this concern",
            "source_documents": ["ASHA Roles and Responsibilities Guidelines"],
            "disclaimer": "AI-assisted guidance only. Doctor verification required.",
            "blocked": True,
            "block_reason": reason
        }


class ResponseValidator:
    """
    Validates RAG responses against required schema.
    
    Ensures all responses are safe and properly structured.
    """
    
    @staticmethod
    def validate_response(response: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate response follows ASHAResponseSchema.
        
        Args:
            response: Response dict to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Validate against Pydantic schema
            ASHAResponseSchema(**response)
            
            # Additional safety checks
            guidance = response.get("guidance", "")
            
            # Check for forbidden content
            forbidden_phrases = [
                "don't worry", "everything will be fine", "baby is safe",
                "mother is safe", "no need to see doctor", "you can wait"
            ]
            
            guidance_lower = guidance.lower()
            for phrase in forbidden_phrases:
                if phrase in guidance_lower:
                    return (
                        False,
                        f"Response contains forbidden reassurance: '{phrase}'"
                    )
            
            # Check checklist not empty
            if not response.get("checklist") or len(response["checklist"]) == 0:
                return (False, "Response missing actionable checklist")
            
            # Check escalation rule present
            if not response.get("escalation_rule") or len(response["escalation_rule"]) < 10:
                return (False, "Response missing clear escalation rule")
            
            # Check disclaimer present
            if "disclaimer" not in response or not response["disclaimer"]:
                return (False, "Response missing safety disclaimer")
            
            return (True, None)
            
        except ValidationError as e:
            return (False, f"Schema validation failed: {str(e)}")
        except Exception as e:
            return (False, f"Validation error: {str(e)}")
    
    @staticmethod
    def sanitize_response(response: Dict) -> Dict:
        """
        Sanitize response to ensure safety.
        
        Args:
            response: Response to sanitize
            
        Returns:
            Sanitized response with safety disclaimer
        """
        # Ensure disclaimer is present
        if "disclaimer" not in response or not response["disclaimer"]:
            response["disclaimer"] = "AI-assisted guidance only. Doctor verification required."
        
        # Ensure escalation rule mentions doctor
        escalation = response.get("escalation_rule", "")
        if "doctor" not in escalation.lower():
            response["escalation_rule"] += " Consult doctor if uncertain."
        
        return response


class ConfidenceScorer:
    """
    Scores confidence of RAG responses.
    
    Lower confidence → stronger escalation recommendation.
    """
    
    @staticmethod
    def score_response(
        query: str,
        retrieved_docs: list,
        response: Dict
    ) -> float:
        """
        Calculate confidence score for response.
        
        Args:
            query: Original query
            retrieved_docs: Documents retrieved
            response: Generated response
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        score = 1.0
        
        # Factor 1: Number of retrieved documents
        if len(retrieved_docs) == 0:
            score *= 0.0  # No confidence without sources
        elif len(retrieved_docs) == 1:
            score *= 0.6  # Low confidence with only 1 source
        elif len(retrieved_docs) == 2:
            score *= 0.8
        else:  # 3-4 documents
            score *= 1.0
        
        # Factor 2: Source diversity
        sources = set()
        for doc in retrieved_docs:
            sources.add(doc.metadata.get("source", "unknown"))
        
        if len(sources) == 1:
            score *= 0.8  # Penalty for single source
        
        # Factor 3: Response has specific guidance
        guidance = response.get("guidance", "")
        if len(guidance) < 50:
            score *= 0.5  # Penalty for vague guidance
        
        # Factor 4: Checklist has actionable steps
        checklist = response.get("checklist", [])
        if len(checklist) < 2:
            score *= 0.6  # Penalty for insufficient steps
        
        # Factor 5: Clear escalation rule
        escalation = response.get("escalation_rule", "")
        if "immediate" in escalation.lower() or "urgent" in escalation.lower():
            score *= 1.0  # Good - clear urgency
        elif len(escalation) < 20:
            score *= 0.7  # Penalty for vague escalation
        
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]
    
    @staticmethod
    def should_flag_for_review(confidence: float) -> bool:
        """
        Determine if response should be flagged for doctor review.
        
        Args:
            confidence: Confidence score
            
        Returns:
            True if should be reviewed by doctor
        """
        return confidence < 0.7


# Standalone testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("ASHA SAFETY FILTER TEST")
    print("="*70)
    
    safety_filter = ASHASafetyFilter()
    
    # Test queries
    test_cases = [
        # Safe queries
        ("What are danger signs in pregnancy?", QuerySafetyLevel.SAFE),
        ("BP is 150/95 at 28 weeks, what to do?", QuerySafetyLevel.SAFE),
        ("When should I refer to doctor?", QuerySafetyLevel.SAFE),
        
        # Blocked queries
        ("Which medicine should I give for high BP?", QuerySafetyLevel.BLOCKED),
        ("What disease does she have?", QuerySafetyLevel.BLOCKED),
        ("How can I treat this infection?", QuerySafetyLevel.BLOCKED),
        ("Is the baby safe?", QuerySafetyLevel.BLOCKED),
        ("Can we delay the hospital visit?", QuerySafetyLevel.UNCERTAIN),
    ]
    
    print("\nTesting query validation:")
    for query, expected in test_cases:
        level, reason = safety_filter.validate_query(query)
        status = "✓" if level == expected else "✗"
        
        print(f"\n{status} Query: '{query}'")
        print(f"  Result: {level.value}")
        if reason:
            print(f"  Reason: {reason}")
    
    print("\n" + "="*70)
    print("✅ SAFETY FILTER TEST COMPLETE")
    print("="*70)
