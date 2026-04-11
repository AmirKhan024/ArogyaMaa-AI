"""
ASHA RAG Retriever & Prompt System

This module implements:
1. Vector database retriever with metadata filtering
2. ASHA-specific prompt templates
3. Top-k document retrieval (max 4 chunks)
4. Context injection for LLM
5. Source citation extraction

SAFETY: Only retrieves from ASHA-approved documents.
"""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path

# LangChain imports
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_classic.prompts import ChatPromptTemplate
from langchain_classic.schema import Document

# Groq LLM
from groq import Groq

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ASHARAGRetriever:
    """
    RAG retriever specifically for ASHA protocol guidance.
    
    Features:
    - Metadata filtering (audience=asha)
    - Top-k retrieval (max 4 chunks)
    - Source citation tracking
    - Safety validation
    """
    
    def __init__(
        self,
        vector_db_dir: str = "app/rag/vector_db",
        top_k: int = 4
    ):
        """
        Initialize ASHA RAG retriever.
        
        Args:
            vector_db_dir: Path to Chroma database
            top_k: Maximum number of chunks to retrieve (max 4)
        """
        self.vector_db_dir = Path(vector_db_dir)
        self.top_k = min(top_k, 4)  # Enforce max 4 chunks
        
        # Initialize embeddings (same as ingestion)
        logger.info("Loading embedding model for retrieval...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # Load vector database
        self.vector_store = None
        self.load_vector_db()
    
    def load_vector_db(self) -> bool:
        """
        Load existing Chroma vector database.
        
        Returns:
            True if successful
        """
        if not self.vector_db_dir.exists():
            logger.error(f"Vector database not found: {self.vector_db_dir}")
            logger.error("Run knowledge ingestion first: python test_rag_ingestion.py")
            return False
        
        try:
            logger.info(f"Loading vector database from: {self.vector_db_dir}")
            
            self.vector_store = Chroma(
                persist_directory=str(self.vector_db_dir),
                embedding_function=self.embeddings,
                collection_name="asha_knowledge"
            )
            
            logger.info("✓ Vector database loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"✗ Error loading vector database: {e}")
            return False
    
    def retrieve_documents(
        self,
        query: str,
        metadata_filter: Optional[Dict] = None
    ) -> List[Document]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: User's query
            metadata_filter: Optional metadata filter (e.g., {"audience": "asha"})
            
        Returns:
            List of relevant documents (max top_k)
        """
        if not self.vector_store:
            logger.error("Vector database not initialized")
            return []
        
        try:
            # Default filter: audience=asha
            if metadata_filter is None:
                metadata_filter = {"audience": "asha"}
            
            logger.info(f"Retrieving documents for query: '{query[:50]}...'")
            logger.info(f"  Metadata filter: {metadata_filter}")
            logger.info(f"  Top-k: {self.top_k}")
            
            # Similarity search with metadata filter
            docs = self.vector_store.similarity_search(
                query=query,
                k=self.top_k,
                filter=metadata_filter
            )
            
            logger.info(f"  ✓ Retrieved {len(docs)} documents")
            
            return docs
            
        except Exception as e:
            logger.error(f"✗ Error retrieving documents: {e}")
            return []
    
    def extract_sources(self, documents: List[Document]) -> List[str]:
        """
        Extract unique source citations from retrieved documents.
        
        Args:
            documents: Retrieved documents
            
        Returns:
            List of unique source names
        """
        sources = set()
        for doc in documents:
            source = doc.metadata.get("source", "Unknown")
            year = doc.metadata.get("year", "")
            if year:
                source_citation = f"{source.replace('.pdf', '')} ({year})"
            else:
                source_citation = source.replace('.pdf', '')
            sources.add(source_citation)
        
        return sorted(list(sources))
    
    def format_context(self, documents: List[Document]) -> str:
        """
        Format retrieved documents into context string for LLM.
        
        Args:
            documents: Retrieved documents
            
        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant information found in knowledge base."
        
        context_parts = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get("source", "Unknown")
            topic = doc.metadata.get("topic", "general")
            content = doc.page_content.strip()
            
            context_parts.append(
                f"[Document {i}]\n"
                f"Source: {source}\n"
                f"Topic: {topic}\n"
                f"Content:\n{content}\n"
            )
        
        return "\n---\n".join(context_parts)


class ASHAPromptManager:
    """
    Manages prompts for ASHA RAG chatbot.
    
    Ensures:
    - Safety-first messaging
    - Protocol-driven guidance
    - Proper escalation rules
    - JSON-only responses
    """
    
    # System prompt for ASHA guidance
    SYSTEM_PROMPT = """You are an ASHA protocol guidance assistant for ArogyaMaa, a maternal health monitoring system.

YOUR ROLE:
- Provide step-based protocol guidance to ASHA workers
- Help identify danger signs in pregnancy
- Guide when to escalate to doctors
- Use ONLY the information from retrieved documents

ABSOLUTE RULES:
❌ NEVER diagnose medical conditions
❌ NEVER recommend specific medicines or dosages
❌ NEVER make treatment decisions
❌ NEVER reassure about mother/baby safety
❌ NEVER give advice not found in the documents

✅ ALWAYS provide step-based checklists
✅ ALWAYS specify when to refer to doctor
✅ ALWAYS cite source documents
✅ ALWAYS include safety disclaimer
✅ ALWAYS escalate if uncertain

If the answer is NOT in the retrieved documents:
Respond with: "Insufficient information. Please refer this case to a doctor immediately."

RESPONSE FORMAT (JSON ONLY):
{
  "guidance": "Clear, actionable protocol guidance",
  "checklist": ["Step 1", "Step 2", "Step 3"],
  "escalation_rule": "Exact condition requiring doctor referral",
  "source_documents": ["Source 1", "Source 2"],
  "disclaimer": "AI-assisted guidance only. Doctor verification required."
}

Return ONLY valid JSON. No extra text."""

    @staticmethod
    def create_rag_prompt(query: str, context: str) -> str:
        """
        Create complete RAG prompt with query and context.
        
        Args:
            query: User's query
            context: Retrieved document context
            
        Returns:
            Complete prompt for LLM
        """
        user_prompt = f"""ASHA Worker Query:
"{query}"

Retrieved Knowledge Base Context:
{context}

Based ONLY on the context above, provide ASHA protocol guidance.

Remember:
- Use ONLY information from the retrieved documents
- Provide step-based checklist
- Specify when to escalate to doctor
- Include source citations
- Never diagnose or prescribe medication

Return response as valid JSON following the exact format specified in the system prompt."""

        return user_prompt
    
    @staticmethod
    def get_blocked_query_response() -> Dict:
        """
        Response for blocked/unsafe queries.
        
        Returns:
            JSON response refusing unsafe query
        """
        return {
            "guidance": "This query requests information outside ASHA worker scope.",
            "checklist": [
                "Do not attempt to answer this question",
                "Immediately refer the mother to a doctor",
                "Do not administer any medication or treatment"
            ],
            "escalation_rule": "Doctor consultation required immediately",
            "source_documents": ["ASHA Roles and Responsibilities Guidelines"],
            "disclaimer": "AI-assisted guidance only. Doctor verification required."
        }
    
    @staticmethod
    def get_no_results_response() -> Dict:
        """
        Response when no relevant documents found.
        
        Returns:
            JSON response for no results
        """
        return {
            "guidance": "Insufficient information available in knowledge base.",
            "checklist": [
                "This specific case is not covered in ASHA training materials",
                "Refer the mother to a doctor for proper evaluation"
            ],
            "escalation_rule": "Immediate doctor consultation required",
            "source_documents": [],
            "disclaimer": "AI-assisted guidance only. Doctor verification required."
        }


class ASHARAGEngine:
    """
    Complete RAG engine combining retriever, prompt, and LLM.
    
    This is the main interface for ASHA protocol queries.
    """
    
    def __init__(self):
        """Initialize RAG engine with retriever and LLM."""
        # Initialize retriever
        self.retriever = ASHARAGRetriever()
        
        # Initialize prompt manager
        self.prompt_manager = ASHAPromptManager()
        
        # Initialize Groq LLM
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            logger.error("GROQ_API_KEY not found in environment")
            raise ValueError("GROQ_API_KEY required for RAG engine")
        
        self.llm_client = Groq(api_key=groq_api_key)
        self.model = "llama-3.1-8b-instant"
        
        logger.info("✓ ASHA RAG Engine initialized")
    
    def query(self, user_query: str) -> Dict:
        """
        Process ASHA worker query through RAG pipeline.
        
        Args:
            user_query: ASHA worker's question
            
        Returns:
            JSON response with guidance
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"ASHA RAG Query: {user_query}")
        logger.info(f"{'='*70}")
        
        # Step 1: Retrieve relevant documents
        documents = self.retriever.retrieve_documents(
            query=user_query,
            metadata_filter={"audience": "asha"}
        )
        
        # Step 2: Check if documents found
        if not documents:
            logger.warning("No documents retrieved - returning fallback response")
            return self.prompt_manager.get_no_results_response()
        
        # Step 3: Format context
        context = self.retriever.format_context(documents)
        sources = self.retriever.extract_sources(documents)
        
        logger.info(f"Context length: {len(context)} characters")
        logger.info(f"Sources: {sources}")
        
        # Step 4: Create prompt
        user_prompt = self.prompt_manager.create_rag_prompt(user_query, context)
        
        # Step 5: Call Groq LLM
        try:
            logger.info("Calling Groq LLM...")
            
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.prompt_manager.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1500,
                response_format={"type": "json_object"}  # Force JSON output
            )
            
            # Parse JSON response
            import json
            result = json.loads(response.choices[0].message.content)
            
            logger.info("✓ LLM response received and parsed")
            
            return result
            
        except Exception as e:
            logger.error(f"✗ Error calling LLM: {e}")
            import traceback
            traceback.print_exc()
            
            # Return fallback
            return self.prompt_manager.get_no_results_response()


# Standalone testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("ASHA RAG RETRIEVER TEST")
    print("="*70)
    
    # Test retriever
    print("\n1. Testing Retriever...")
    retriever = ASHARAGRetriever()
    
    if retriever.vector_store:
        print("   ✓ Vector database loaded")
        
        # Test query
        test_query = "What should I do if blood pressure is 150/95 at 28 weeks?"
        print(f"\n2. Test Query: '{test_query}'")
        
        docs = retriever.retrieve_documents(test_query)
        print(f"   ✓ Retrieved {len(docs)} documents")
        
        if docs:
            print("\n3. Retrieved Documents:")
            for i, doc in enumerate(docs, 1):
                print(f"\n   Document {i}:")
                print(f"   Source: {doc.metadata.get('source')}")
                print(f"   Topic: {doc.metadata.get('topic')}")
                print(f"   Content preview: {doc.page_content[:200]}...")
            
            sources = retriever.extract_sources(docs)
            print(f"\n4. Source Citations:")
            for source in sources:
                print(f"   - {source}")
        
        print("\n" + "="*70)
        print("✅ RETRIEVER TEST COMPLETE")
        print("="*70)
    else:
        print("   ✗ Vector database not loaded")
        print("   Run: python test_rag_ingestion.py first")
