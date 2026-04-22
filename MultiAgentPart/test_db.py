import os
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("DB_Test")

load_dotenv()

def test_supabase_connection():
    from memory.history import _get_conn, history_stats
    
    log.info("Testing Supabase PostgreSQL connection...")
    conn = _get_conn()
    if conn:
        log.info("✅ Connection Successful!")
        conn.close()
        
        stats = history_stats()
        log.info(f"📊 Database Stats: {stats}")
    else:
        log.error("❌ Connection Failed. Check your DATABASE_URL in .env")

def test_qdrant_connection():
    from pipeline.rag import _get_client
    
    log.info("\nTesting Qdrant Cloud (Vector DB) connection...")
    try:
        client = _get_client()
        collections = client.get_collections()
        log.info(f"✅ Qdrant Connected! Collections found: {[c.name for c in collections.collections]}")
    except Exception as e:
        log.error(f"❌ Qdrant Connection Failed: {e}")

if __name__ == "__main__":
    test_supabase_connection()
    test_qdrant_connection()
