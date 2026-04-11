"""
Knowledge Ingestion Pipeline for ASHA RAG Chatbot

This module:
1. Extracts text from PDF documents
2. Chunks documents with metadata
3. Creates embeddings
4. Stores in Chroma vector database

SAFETY: Uses ONLY approved ASHA training materials.
"""

import os
import logging
from typing import List, Dict, Optional
from pathlib import Path
import hashlib

# PDF Processing
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Vector Store
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ASHAKnowledgeIngestion:
    """
    Handles ingestion of ASHA training materials into vector database.
    
    Strict safety:
    - Only processes approved documents
    - Adds metadata for filtering
    - Validates chunk quality
    """
    
    # Approved document sources
    APPROVED_SOURCES = {
        "ASHA_Module_6_English_2023.pdf": {
            "year": "2023",
            "topic": "general_asha_training",
            "authority": "NHM",
            "audience": "asha"
        },
        "guidelines-on-asha.pdf": {
            "year": "2023",
            "topic": "asha_guidelines",
            "authority": "NHM",
            "audience": "asha"
        },
        "Notes for ASHA Trainers Part -1 English.pdf": {
            "year": "2023",
            "topic": "asha_trainer_notes",
            "authority": "NHM",
            "audience": "asha"
        },
        "sba_guidelines_for_skilled_attendance_at_birth.pdf": {
            "year": "2023",
            "topic": "childbirth_attendance",
            "authority": "NHM",
            "audience": "asha"
        },
        "Guidance_Note-Extended_PMSMA_for_tracking_HRPs.pdf": {
            "year": "2023",
            "topic": "high_risk_pregnancy",
            "authority": "NHM",
            "audience": "asha"
        }
    }
    
    def __init__(
        self,
        pdf_source_dir: str = "rag_pdf_source",
        vector_db_dir: str = "app/rag/vector_db",
        chunk_size: int = 500,
        chunk_overlap: int = 100
    ):
        """
        Initialize knowledge ingestion pipeline.
        
        Args:
            pdf_source_dir: Directory containing source PDFs
            vector_db_dir: Directory to store Chroma database
            chunk_size: Size of text chunks (400-600 tokens recommended)
            chunk_overlap: Overlap between chunks (80-100 tokens)
        """
        self.pdf_source_dir = Path(pdf_source_dir)
        self.vector_db_dir = Path(vector_db_dir)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize text splitter (one medical concept per chunk)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
            is_separator_regex=False
        )
        
        # Initialize embeddings (using sentence-transformers)
        logger.info("Loading embedding model...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logger.info("✓ Embedding model loaded")
        
        self.vector_store = None
    
    def extract_text_from_pdf(self, pdf_path: Path) -> List[Dict]:
        """
        Extract text from PDF with page metadata.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            List of document chunks with metadata
        """
        logger.info(f"Extracting text from: {pdf_path.name}")
        
        try:
            loader = PyPDFLoader(str(pdf_path))
            pages = loader.load()
            
            logger.info(f"  ✓ Extracted {len(pages)} pages")
            return pages
            
        except Exception as e:
            logger.error(f"  ✗ Error extracting {pdf_path.name}: {e}")
            return []
    
    def create_chunks_with_metadata(
        self,
        documents: List,
        source_file: str
    ) -> List[Dict]:
        """
        Split documents into chunks and add safety metadata.
        
        Args:
            documents: Raw document pages
            source_file: Name of source PDF file
            
        Returns:
            List of chunks with metadata
        """
        if source_file not in self.APPROVED_SOURCES:
            logger.warning(f"⚠️  {source_file} not in approved sources list")
            return []
        
        # Get source metadata
        source_meta = self.APPROVED_SOURCES[source_file]
        
        # Split documents into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        logger.info(f"  Created {len(chunks)} chunks")
        
        # Add metadata to each chunk
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "source": source_file,
                "topic": source_meta["topic"],
                "year": source_meta["year"],
                "authority": source_meta["authority"],
                "audience": source_meta["audience"],
                "chunk_id": hashlib.md5(
                    f"{source_file}_{i}".encode()
                ).hexdigest()[:12]
            })
        
        return chunks
    
    def validate_chunk_quality(self, chunk) -> bool:
        """
        Validate that chunk contains meaningful content.
        
        Args:
            chunk: Document chunk to validate
            
        Returns:
            True if chunk is valid
        """
        content = chunk.page_content.strip()
        
        # Filter out empty or too-short chunks
        if len(content) < 50:
            return False
        
        # Filter out chunks that are mostly numbers/symbols
        alpha_ratio = sum(c.isalpha() for c in content) / len(content)
        if alpha_ratio < 0.5:
            return False
        
        return True
    
    def ingest_all_documents(self) -> bool:
        """
        Main ingestion pipeline: process all PDFs and create vector DB.
        
        Returns:
            True if successful
        """
        logger.info("=" * 70)
        logger.info("ASHA KNOWLEDGE INGESTION PIPELINE")
        logger.info("=" * 70)
        
        if not self.pdf_source_dir.exists():
            logger.error(f"✗ PDF source directory not found: {self.pdf_source_dir}")
            return False
        
        all_chunks = []
        
        # Process each approved PDF
        for pdf_file in self.APPROVED_SOURCES.keys():
            pdf_path = self.pdf_source_dir / pdf_file
            
            if not pdf_path.exists():
                logger.warning(f"⚠️  PDF not found: {pdf_file}")
                continue
            
            logger.info(f"\n📄 Processing: {pdf_file}")
            
            # Extract text
            pages = self.extract_text_from_pdf(pdf_path)
            if not pages:
                continue
            
            # Create chunks with metadata
            chunks = self.create_chunks_with_metadata(pages, pdf_file)
            
            # Validate chunks
            valid_chunks = [c for c in chunks if self.validate_chunk_quality(c)]
            logger.info(f"  ✓ {len(valid_chunks)} valid chunks")
            
            all_chunks.extend(valid_chunks)
        
        if not all_chunks:
            logger.error("✗ No valid chunks created")
            return False
        
        logger.info(f"\n📊 Total chunks ready for indexing: {len(all_chunks)}")
        
        # Create vector database
        logger.info("\n🔨 Creating Chroma vector database...")
        
        try:
            # Create directory if it doesn't exist
            self.vector_db_dir.mkdir(parents=True, exist_ok=True)
            
            # Create Chroma database
            self.vector_store = Chroma.from_documents(
                documents=all_chunks,
                embedding=self.embeddings,
                persist_directory=str(self.vector_db_dir),
                collection_name="asha_knowledge"
            )
            
            # Persist to disk
            self.vector_store.persist()
            
            logger.info("✓ Vector database created and persisted")
            logger.info(f"  Location: {self.vector_db_dir}")
            logger.info(f"  Total documents: {len(all_chunks)}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ Error creating vector database: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_existing_db(self) -> Optional[Chroma]:
        """
        Load existing Chroma database.
        
        Returns:
            Chroma vector store or None
        """
        if not self.vector_db_dir.exists():
            logger.warning("Vector database not found. Run ingest_all_documents() first.")
            return None
        
        try:
            logger.info(f"Loading vector database from: {self.vector_db_dir}")
            
            self.vector_store = Chroma(
                persist_directory=str(self.vector_db_dir),
                embedding_function=self.embeddings,
                collection_name="asha_knowledge"
            )
            
            logger.info("✓ Vector database loaded")
            return self.vector_store
            
        except Exception as e:
            logger.error(f"✗ Error loading vector database: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """
        Get statistics about the knowledge base.
        
        Returns:
            Dictionary with stats
        """
        if not self.vector_store:
            return {"status": "not_initialized"}
        
        try:
            collection = self.vector_store._collection
            count = collection.count()
            
            return {
                "status": "ready",
                "total_chunks": count,
                "embedding_model": "all-MiniLM-L6-v2",
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "sources": list(self.APPROVED_SOURCES.keys())
            }
        except:
            return {"status": "error"}


# Standalone script execution
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ASHA RAG KNOWLEDGE INGESTION")
    print("=" * 70)
    
    # Initialize ingestion pipeline
    ingestion = ASHAKnowledgeIngestion()
    
    # Run ingestion
    success = ingestion.ingest_all_documents()
    
    if success:
        print("\n" + "=" * 70)
        print("✅ INGESTION COMPLETE")
        print("=" * 70)
        
        stats = ingestion.get_stats()
        print(f"\n📊 Knowledge Base Stats:")
        print(f"  Total Chunks: {stats['total_chunks']}")
        print(f"  Embedding Model: {stats['embedding_model']}")
        print(f"  Sources: {len(stats['sources'])} PDFs")
        print("\nVector database ready for ASHA RAG queries!")
    else:
        print("\n❌ INGESTION FAILED")
        print("Check logs above for errors.")
