import os
import time
import shutil
import tempfile
from git import Repo
from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import JinaEmbeddings
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo import MongoClient

SUPPORTED_EXTENSIONS = ['.py', '.js', '.jsx', '.ts', '.tsx', '.md', '.txt', '.json', '.yaml', '.yml', '.html', '.css']
# Files that are pure metadata/lockfiles — useless for RAG and pollute similarity search
BLOCKED_FILENAMES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', '.env', '.env.example'}
BATCH_SIZE = 100       # Chunks per batch
BATCH_DELAY = 1        # Seconds between batches
MAX_CHUNKS = 2000      # Raised — free Jina tier supports up to 1M tokens/month

# Folders to skip when building the directory tree
SKIP_DIRS = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build', '.nyc_output', 'coverage'}

def get_directory_tree(repo_path: str) -> str:
    """Walk the repo and return a human-readable directory tree string."""
    tree_lines = ["REPOSITORY DIRECTORY STRUCTURE:"]
    for root, dirs, files in os.walk(repo_path):
        # Prune noisy/large directories in-place so os.walk skips them
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith('.'))
        level = root.replace(repo_path, '').count(os.sep)
        indent = '  ' * level
        folder_name = os.path.basename(root) or os.path.basename(repo_path)
        tree_lines.append(f"{indent}{folder_name}/")
        sub_indent = '  ' * (level + 1)
        for file in sorted(files):
            tree_lines.append(f"{sub_indent}{file}")
    return "\n".join(tree_lines)

def load_documents(directory: str):
    """Load documents from multiple file extensions."""
    all_docs = []
    for ext in SUPPORTED_EXTENSIONS:
        try:
            loader = DirectoryLoader(
                directory,
                glob=f"**/*{ext}",
                loader_cls=TextLoader,
                loader_kwargs={"encoding": "utf-8", "autodetect_encoding": True},
                silent_errors=True,
            )
            docs = loader.load()
            # Filter out blocked filenames (lockfiles, .env, etc.)
            docs = [d for d in docs if os.path.basename(d.metadata.get("source", "")) not in BLOCKED_FILENAMES]
            all_docs.extend(docs)
        except Exception:
            continue
    return all_docs

def process_github_repo(repo_url: str):
    # 1. Clone Repo
    temp_dir = tempfile.mkdtemp()
    try:
        print(f"Cloning {repo_url}...")
        Repo.clone_from(repo_url, temp_dir)

        # 2. Build and inject the directory tree as a special document
        print("Building directory tree document...")
        tree_text = get_directory_tree(temp_dir)
        tree_doc = Document(
            page_content=tree_text,
            metadata={"source": "directory_tree", "type": "structure"}
        )

        # 3. Load file-content Documents
        print("Loading documents...")
        docs = [tree_doc] + load_documents(temp_dir)
        print(f"Loaded {len(docs)} documents (including directory tree)")

        if not docs:
            return {"status": "warning", "message": "No readable files found in repository", "chunks_processed": 0}

        # 4. Chunk Documents
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        texts = splitter.split_documents(docs)

        # Cap chunks to avoid quota exhaustion on free tier
        if len(texts) > MAX_CHUNKS:
            print(f"Capping chunks from {len(texts)} to {MAX_CHUNKS} to respect API quota")
            texts = texts[:MAX_CHUNKS]

        print(f"Processing {len(texts)} chunks in batches of {BATCH_SIZE}...")

        # 5. Generate Embeddings using Jina AI and Save to MongoDB
        mongo_uri = os.environ.get("MONGO_URI")
        jina_api_key = os.environ.get("JINA_API_KEY")

        client = MongoClient(mongo_uri)
        collection = client["codebase_rag"]["vectors"]

        embeddings = JinaEmbeddings(
            jina_api_key=jina_api_key,
            model_name="jina-embeddings-v3"
        )

        vectorstore = MongoDBAtlasVectorSearch(
            collection=collection,
            embedding=embeddings,
            index_name="default",
            relevance_score_fn="cosine"
        )

        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i:i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            print(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")

            # Retry logic for rate limit errors
            for attempt in range(3):
                try:
                    vectorstore.add_documents(batch)
                    break
                except Exception as e:
                    if "429" in str(e) or "rate" in str(e).lower():
                        wait = BATCH_DELAY * (attempt + 1) * 5
                        print(f"Rate limited, waiting {wait}s before retry...")
                        time.sleep(wait)
                    else:
                        raise e

            if batch_num < total_batches:
                time.sleep(BATCH_DELAY)

        print("Done!")
        return {"status": "success", "chunks_processed": len(texts)}

    except Exception as e:
        print(f"Error: {e}")
        raise e
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
