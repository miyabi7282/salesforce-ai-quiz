import os
import yaml
import faiss
import numpy as np
import google.generativeai as genai
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pickle
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
import time
import re

# .envファイルから環境変数を読み込む
load_dotenv()

# --- 設定項目 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 入力となるYAMLファイル
INPUT_FILES = [
    "salesforce_help_articles.yaml",
    "salesforce_guides_consolidated.yaml",
    "salesforce_data_cloud_reference_guide.yaml",
    "salesforce_data_cloud_developer_guide.yaml"
]

# 出力ファイル
FAISS_INDEX_FILE = "salesforce_docs.faiss"
TEXT_CHUNKS_FILE = "salesforce_docs_chunks.pkl"
BM25_INDEX_FILE = "salesforce_docs.bm25"

# テキスト分割の設定
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

def load_documents_from_files(filenames):
    """複数のYAMLファイルからドキュメントを読み込む"""
    all_docs = []
    print("--- ドキュメントの読み込み開始 ---")
    for filename in filenames:
        if not os.path.exists(filename):
            print(f"警告: ファイル '{filename}' が見つかりません。スキップします。")
            continue
        
        with open(filename, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if isinstance(data, list):
                valid_docs = [doc for doc in data if doc and doc.get('content') and isinstance(doc.get('content'), str)]
                all_docs.extend(valid_docs)
                print(f"✔ '{filename}' から {len(valid_docs)} 件の有効なドキュメントを読み込みました。")
    print(f"✔ 合計 {len(all_docs)} 件のドキュメントを読み込み完了。")
    return all_docs

def split_documents_into_chunks(documents):
    """ドキュメントを意味のあるチャンクに分割する（メタデータ埋め込み＆分割戦略改善）"""
    print("\n--- テキストのチャンク分割を開始 ---")
    
    # 改行や句読点を優先的に区切り文字として使うように設定
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", "。", "、", " ", ""] # 優先順位が高い区切り文字
    )
    
    chunks_with_metadata = []
    for doc in documents:
        content = doc.get('content', '')
        if not content or not isinstance(content, str):
            continue
            
        split_texts = text_splitter.split_text(content)
        
        for text in split_texts:
            # 各チャンクの先頭に、出典とタイトルの情報を追加
            source_info = doc.get('url') or doc.get('source_document', 'N/A')
            title_info = doc.get('title', 'N/A')
            
            # チャンクのテキスト本体
            chunk_text = f"出典: {source_info}\nタイトル: {title_info}\n\n{text}"
            
            chunks_with_metadata.append({
                "text": chunk_text, # メタデータが埋め込まれたテキスト
                "source": source_info,
                "title": title_info
            })
            
    print(f"✔ {len(documents)}件のドキュメントを {len(chunks_with_metadata)}個のチャンクに分割しました。")
    return chunks_with_metadata

def vectorize_chunks(chunks):
    """Gemini APIを使ってチャンクをベクトル化する"""
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("\n★★★ エラー: Gemini APIキーが設定されていません。★★★")
        return None, None

    print("\n--- チャンクのベクトル化を開始 ---")
    print("使用モデル: text-embedding-004")
    
    genai.configure(api_key=GEMINI_API_KEY)
    
    vectors = []
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        # チャンクの辞書からテキスト部分だけを抽出
        batch_texts = [chunk["text"] for chunk in chunks[i:i+batch_size]]
        
        try:
            time.sleep(1) # レートリミット対策
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=batch_texts,
                task_type="RETRIEVAL_DOCUMENT"
            )
            vectors.extend(result['embedding'])
            progress = min(i + batch_size, len(chunks))
            print(f"  - 進行状況: {progress} / {len(chunks)} 件のチャンクをベクトル化済み...")
        except Exception as e:
            print(f"✖ バッチ処理中にAPIエラーが発生しました (件名: {i}～{i+batch_size}): {e}")
            vectors.extend([None] * len(batch_texts))

    print(f"✔ ベクトル化処理完了。")
    
    valid_vectors = []
    valid_chunks = []
    for chunk, vector in zip(chunks, vectors):
        if vector is not None:
            valid_chunks.append(chunk)
            valid_vectors.append(vector)

    if not valid_vectors:
        return None, None
        
    return np.array(valid_vectors).astype('float32'), valid_chunks


def create_and_save_faiss_index(vectors, index_path):
    """ベクトルからFaissインデックスを作成し、保存する"""
    if vectors is None or len(vectors) == 0:
        print("✖ ベクトルが空のため、Faissインデックスを作成できません。")
        return False
        
    print("\n--- Faissベクトルインデックスの作成と保存を開始 ---")
    dimension = vectors.shape[1]
    
    if faiss.get_num_gpus() > 0:
        print(f"✔ {faiss.get_num_gpus()}個のGPUを検出しました。GPU版Faissを使用します。")
        res = faiss.StandardGpuResources()
        index_gpu = faiss.GpuIndexFlatL2(res, dimension)
        index_gpu.add(vectors)
        print(f"  - GPU上でインデックス作成完了。CPUに転送して保存します...")
        index_cpu = faiss.index_gpu_to_cpu(index_gpu)
        faiss.write_index(index_cpu, index_path)
    else:
        print("ℹ GPUが見つかりません。CPU版Faissを使用します。")
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        faiss.write_index(index, index_path)

    print(f"✔ Faissインデックスを '{index_path}' に保存しました。")
    return True

def create_and_save_bm25_index(chunks, index_path):
    """チャンクからBM25インデックスを作成し、保存する"""
    print("\n--- BM25キーワードインデックスの作成と保存を開始 ---")
    
    def simple_tokenizer(text):
        return re.findall(r'[A-Za-z0-9]+|[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+', text.lower())

    # BM25のインデックス作成には、メタデータが埋め込まれていない元のテキストを使う方が良い場合がある
    # ここでは、埋め込み済みのテキストをそのまま使う
    tokenized_corpus = [simple_tokenizer(chunk["text"]) for chunk in chunks]
    
    bm25 = BM25Okapi(tokenized_corpus)
    
    with open(index_path, 'wb') as f:
        pickle.dump(bm25, f)
        
    print(f"✔ BM25インデックスを '{index_path}' に保存しました。")

def save_chunks(chunks, chunks_path):
    """チャンクのテキストデータを保存する"""
    with open(chunks_path, 'wb') as f:
        pickle.dump(chunks, f)
    print(f"✔ チャンクデータを '{chunks_path}' に保存しました。")

# --- メイン処理 ---
if __name__ == "__main__":
    docs = load_documents_from_files(INPUT_FILES)
    
    if docs:
        chunks = split_documents_into_chunks(docs)
        if chunks:
            vectors, valid_chunks = vectorize_chunks(chunks)
            
            if vectors is not None and len(vectors) > 0:
                create_and_save_bm25_index(valid_chunks, BM25_INDEX_FILE)
                if create_and_save_faiss_index(vectors, FAISS_INDEX_FILE):
                    save_chunks(valid_chunks, TEXT_CHUNKS_FILE)
                    print("\n🎉 全てのドキュメントのベクトル化とインデックス作成が完了しました！ 🎉")
                else:
                    print("\n✖ Faissインデックスの作成または保存に失敗しました。")
            else:
                print("\n✖ 有効なベクトルが生成されなかったため、処理を終了します。")
        else:
            print("\n✖ チャンクが生成されなかったため、処理を終了します。")