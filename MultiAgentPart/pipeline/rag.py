import os
from typing import Dict, List

from langchain_chroma import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHROMA_DIR = os.path.join("data", "chroma")
COLLECTION_NAME = "research_chunks"


def build_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def build_vectorstore() -> Chroma:
    embeddings = build_embeddings()
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_DIR,
    )


def chunk_text(raw_text: str) -> List:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
    )
    return splitter.create_documents([raw_text])


def run_rag_node(state: Dict) -> Dict:
    raw_text = state.get("scraped_content", "").strip()
    topic = state.get("topic", "").strip()

    if not raw_text:
        return {
            **state,
            "rag_context": "",
            "error": state.get("error", "No scraped content available for RAG."),
        }

    chunks = chunk_text(raw_text)
    if not chunks:
        return {
            **state,
            "rag_context": "",
            "error": state.get("error", "No chunks created for RAG."),
        }

    try:
        vectorstore = build_vectorstore()
        vectorstore.add_documents(chunks)

        relevant_docs = vectorstore.similarity_search(topic, k=5)
        relevant_text = "\n\n".join(doc.page_content for doc in relevant_docs)

        return {
            **state,
            "rag_context": relevant_text,
        }
    except Exception as exc:
        return {
            **state,
            "rag_context": "",
            "error": f"RAG failed: {exc}",
        }