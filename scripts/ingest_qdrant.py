import os
import glob
import logging
import yaml
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFLUENCE_DIR = os.path.join(BASE_DIR, "data", "confluence_raw")
TICKETS_DIR = os.path.join(BASE_DIR, "data", "historical_tickets")

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

conf_client = QdrantClient(
    url=os.getenv("QDRANT_CONFLUENCE_URL"),
    api_key=os.getenv("QDRANT_CONFLUENCE_API_KEY"),
)

hist_client = QdrantClient(
    url=os.getenv("QDRANT_HISTORY_URL"),
    api_key=os.getenv("QDRANT_HISTORY_API_KEY"),
)

def recreate_collection(client, collection_name):
    if client.collection_exists(collection_name=collection_name):
        client.delete_collection(collection_name=collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
    logging.info(f"Recreated collection: {collection_name}")

def ingest_confluence():
    collection_name = "confluence"
    recreate_collection(conf_client, collection_name)
    
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    
    documents = []
    filepaths = glob.glob(os.path.join(CONFLUENCE_DIR, "*.md"))
    logging.info(f"Processing {len(filepaths)} Confluence Markdown files...")
    
    for filepath in filepaths:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        parts = content.split('---', 2)
        metadata = {}
        body = content
        
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()
            except Exception as e:
                logging.warning(f"Failed to parse frontmatter for {filepath}: {e}")
                
        splits = markdown_splitter.split_text(body)
        for split in splits:
            split.metadata.update(metadata)
            split.metadata['source'] = filepath
            documents.append(split)
            
    logging.info(f"Created {len(documents)} chunks from Confluence. Ingesting into Qdrant Cloud...")
    
    batch_size = 500
    vector_store = QdrantVectorStore(
        client=conf_client,
        collection_name=collection_name,
        embedding=embeddings,
    )
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        vector_store.add_documents(batch)
        logging.info(f"Ingested Confluence batch {i//batch_size + 1}/{(len(documents)//batch_size) + 1}")

def ingest_tickets():
    collection_name = "historical_tickets"
    recreate_collection(hist_client, collection_name)
    
    documents = []
    filepaths = glob.glob(os.path.join(TICKETS_DIR, "*.txt"))
    logging.info(f"Processing {len(filepaths)} Historical Tickets...")
    
    for filepath in filepaths:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        metadata = {'source': filepath}
        
        lines = content.split('\n')
        for line in lines[:5]:
            if line.startswith("Ticket ID:"):
                metadata['ticket_id'] = line.replace("Ticket ID:", "").strip()
            elif line.startswith("Product Category:"):
                metadata['category'] = line.replace("Product Category:", "").strip()
            elif line.startswith("Issue:"):
                metadata['issue'] = line.replace("Issue:", "").strip()
                
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)
        
    logging.info(f"Created {len(documents)} documents. Ingesting into Qdrant Cloud...")
    
    batch_size = 500
    vector_store = QdrantVectorStore(
        client=hist_client,
        collection_name=collection_name,
        embedding=embeddings,
    )
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i+batch_size]
        vector_store.add_documents(batch)
        logging.info(f"Ingested Tickets batch {i//batch_size + 1}/{(len(documents)//batch_size) + 1}")

if __name__ == "__main__":
    logging.info("Starting Vector Database Ingestion Phase to Qdrant Cloud...")
    ingest_confluence()
    ingest_tickets()
    logging.info("Ingestion Complete!")
