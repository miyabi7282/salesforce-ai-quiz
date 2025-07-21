import os
import yaml
import faiss
import numpy as np
import google.generativeai as genai
import pickle
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
import time
import json
import re
import asyncio
from tqdm.asyncio import tqdm_asyncio

# .envファイルから環境変数を読み込む
load_dotenv()

# --- 設定項目 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 並列実行するタスクの数
MAX_CONCURRENT_TASKS = 5
# エラー時の最大リトライ回数
MAX_RETRIES = 3 

# 入力ファイル
EXAM_QUESTIONS_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions.yaml")
GLOSSARY_FILE = "salesforce_master_glossary.yaml"
FAISS_INDEX_FILE = "salesforce_docs.faiss"
TEXT_CHUNKS_FILE = "salesforce_docs_chunks.pkl"
BM25_INDEX_FILE = "salesforce_docs.bm25"

# 出力ファイル
OUTPUT_PROCESSED_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions_final.yaml")


async def generate_content_with_retry(model, prompt, retries=MAX_RETRIES):
    """API呼び出しを自動でリトライするラッパー関数"""
    for attempt in range(retries):
        try:
            await asyncio.sleep(1.2 + attempt) 
            response = await model.generate_content_async(prompt)
            if response and hasattr(response, 'text'):
                return response.text.strip()
            else:
                raise Exception("APIからの応答が空です。")
        except Exception as e:
            print(f"  - ⚠ APIエラー (試行 {attempt + 1}/{retries}): {str(e).splitlines()[0]}")
            if attempt + 1 == retries:
                print(f"  - ✖ 最大リトライ回数に達しました。この処理は失敗とします。")
                raise
    return None

async def translate_explanation_async(model, explanation, glossary_str):
    """Gemini APIを使って解説を翻訳する（リトライ対応）"""
    if not explanation: return "（解説なし）"
    translation_prompt = f"""
あなたはプロのSalesforce技術翻訳家です。以下の英語の解説を、自然で分かりやすい日本語に翻訳してください。
# 指示
- 専門用語は【専門用語リスト】を参考に、正確に翻訳してください。
- 翻訳文だけを出力してください。あなたの感想や翻訳の過程、脚注番号([1], ², etc.)などのメタコメントは一切含めないでください。
- 元の文章の論理構成を維持してください。
# 専門用語リスト
{glossary_str}
# 英語の解説
{explanation}
# 日本語訳
"""
    try:
        translated_text = await generate_content_with_retry(model, translation_prompt)
        return translated_text
    except Exception:
        return "（翻訳失敗）\n" + explanation

def simple_tokenizer(text):
    """BM25の検索クエリ用の簡易的なトークナイザー"""
    return re.findall(r'[A-Za-z0-9]+|[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+', text.lower())

async def hybrid_search_async(query, faiss_index, bm25_index, chunks, embedding_model, bm25_top_n=30, final_top_k=10):
    """ハイブリッド検索を実行し、最終的な候補チャンクを返す"""
    tokenized_query = simple_tokenizer(query)
    bm25_scores = bm25_index.get_scores(tokenized_query)
    bm25_top_indices = np.argsort(bm25_scores)[::-1][:bm25_top_n]
    bm25_candidates = [chunks[i] for i in bm25_top_indices]
    
    vector_candidates = []
    try:
        await asyncio.sleep(1.2)
        result = await genai.embed_content_async(
            model=embedding_model,
            content=query,
            task_type="RETRIEVAL_QUERY"
        )
        query_vector = result['embedding']
        _, faiss_top_indices = faiss_index.search(np.array([query_vector]).astype('float32'), final_top_k)
        vector_candidates = [chunks[i] for i in faiss_top_indices[0]]
    except Exception as e:
        print(f"      - ✖ ベクトル検索エラー: {e}")

    final_candidates = []
    seen_texts = set()
    for chunk in vector_candidates + bm25_candidates:
        if chunk["text"] not in seen_texts:
            final_candidates.append(chunk)
            seen_texts.add(chunk["text"])
            
    return final_candidates[:final_top_k]

async def select_and_verify_docs_with_ai_async(model, question, candidate_docs):
    """候補ドキュメントの中から、Geminiが最適なものを厳選し、答えを検証する（リトライ対応）"""
    if not candidate_docs:
        return {'related_docs': [], 'excluded_docs': [], 'ai_verification': {'status': '判断不能', 'justification': '関連ドキュメントの候補が見つかりませんでした。'}}

    candidate_docs_str = "\n".join([f"- title: {doc['title']}\n  url: {doc['source']}\n  text: \"{doc['text']}\"" for doc in candidate_docs])
    correct_answer_key = question['correct_answer']
    correct_answer_keys = [key.strip() for key in correct_answer_key.split(',')]
    correct_answer_texts = [question['choices'].get(key, "不明な選択肢") for key in correct_answer_keys]
    correct_answer_display = ", ".join([f"{key}. {text}" for key, text in zip(correct_answer_keys, correct_answer_texts)])

    prompt = f"""
あなたはSalesforce認定試験のエキスパートです。以下の【問題】と【正答】、【候補ドキュメントリスト】を分析し、指示に従ってJSON形式で出力してください。
# 問題
- question_id: {question['question_id']}
  question_text: {question['question_text']}
  choices: {question['choices']}
  correct_answer: {correct_answer_display}
# 候補ドキュメントリスト
{candidate_docs_str}
# 指示
1. `candidate_docs`の中から、【問題】の【正答】を直接的または間接的に裏付ける最も適切なドキュメントを最大3件選んでください。
2. 選んだ各ドキュメントについて、以下の情報を含めてください。
   - `title`: ドキュメントのタイトル
   - `url`: ドキュメントのURL
   - `reason`: なぜこのドキュメントが正答の根拠として適切なのか、具体的な理由。
   - `supporting_text`: 正答の根拠となる、ドキュメント内の最も重要な一文または短いフレーズ。
3. 選ばなかったドキュメントについて、その`title`と選ばなかった理由（例：テーマが違う、抽象的すぎる、など）を簡潔にリストアップしてください。
4. 最後に、公式情報である【候補ドキュメントリスト】全体を吟味した上で、【正答】が妥当かどうかを総合的に判断し、結論を記述してください。
# 出力フォーマット (JSON形式のみで回答すること。前後に説明やマークダウンは不要)
{{
  "related_docs": [],
  "excluded_docs": [],
  "ai_verification": {{
    "status": "正答と一致 or 矛盾の可能性あり or 判断不能",
    "justification": "..."
  }}
}}
"""
    try:
        response_text = await generate_content_with_retry(model, prompt)
        json_text_match = re.search(r'```json\n(.*)\n```', response_text, re.DOTALL)
        if json_text_match:
            json_text = json_text_match.group(1)
        else:
            json_text = response_text
        return json.loads(json_text)
    except Exception as e:
        return {'related_docs': [], 'excluded_docs': [], 'ai_verification': {'status': 'エラー', 'justification': f'AI処理中にエラーが発生しました: {e}'}}

async def process_single_question_async(question, model, embedding_model, faiss_index, bm25_index, chunks, glossary_str):
    """1つの問題に対する全処理を非同期で実行する。失敗した場合はNoneを返す"""
    try:
        jp_explanation = await translate_explanation_async(model, question.get('explanation', ''), glossary_str)
        
        correct_answer_keys = [key.strip() for key in question['correct_answer'].split(',')]
        correct_answer_texts = [question['choices'].get(key, "") for key in correct_answer_keys]
        correct_answer_full_text = " ".join(correct_answer_texts)
        enhanced_query = f"{question['question_text']} {correct_answer_full_text} {jp_explanation}"
        
        candidate_chunks = await hybrid_search_async(enhanced_query, faiss_index, bm25_index, chunks, embedding_model)
        
        analysis_result = await select_and_verify_docs_with_ai_async(model, question, candidate_chunks)
        
        return {
            'question_id': question['question_id'],
            'question_text': question['question_text'],
            'choices': question['choices'],
            'correct_answer': question['correct_answer'],
            'japanese_explanation': jp_explanation,
            'ai_analysis': analysis_result
        }
    except Exception as e:
        print(f"\n✖ 問 {question['question_id']} の処理中に予期せぬ最終エラーが発生しました: {str(e).splitlines()[0]}")
        return None

async def main_async():
    """メインの非同期処理"""
    if not GEMINI_API_KEY:
        print("エラー: APIキーが設定されていません。")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
    embedding_model = "models/text-embedding-004"
    
    print("--- 必要なデータを読み込んでいます ---")
    glossary_str = ""
    if os.path.exists(GLOSSARY_FILE):
        with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
            glossary = yaml.safe_load(f)
            glossary_str = "\n".join([f"- {item['en_term']}: {item['ja_term']}" for item in glossary[:50]])
        print(f"✔ マスター用語集を読み込みました。")
    with open(EXAM_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        exam_questions = yaml.safe_load(f)
    print(f"✔ 試験問題を {len(exam_questions)} 問読み込みました。")
    faiss_index = faiss.read_index(FAISS_INDEX_FILE)
    with open(TEXT_CHUNKS_FILE, 'rb') as f:
        chunks = pickle.load(f)
    print(f"✔ ベクトルデータベースを読み込みました。")
    with open(BM25_INDEX_FILE, 'rb') as f:
        bm25_index = pickle.load(f)
    print(f"✔ BM25キーワードインデックスを読み込みました。")

    processed_questions_dict = {}
    if os.path.exists(OUTPUT_PROCESSED_FILE):
        with open(OUTPUT_PROCESSED_FILE, 'r', encoding='utf-8') as f:
            processed_data = yaml.safe_load(f) or []
            processed_questions_dict = {q['question_id']: q for q in processed_data}
        print(f"✔ 既存の処理済みファイルを検知。{len(processed_questions_dict)}問は処理済みです。")

    questions_to_process = [q for q in exam_questions if q['question_id'] not in processed_questions_dict]
    
    if not questions_to_process:
        print("\n🎉 全ての問題がすでに処理されています。処理を終了します。")
        return

    print(f"\n--- 未処理の {len(questions_to_process)}問の事前処理を最大{MAX_CONCURRENT_TASKS}件の並列処理で開始 ---")

    tasks = [process_single_question_async(q, model, embedding_model, faiss_index, bm25_index, chunks, glossary_str) for q in questions_to_process]
    
    newly_processed_results = await tqdm_asyncio.gather(*tasks)

    successful_tasks = 0
    failed_question_ids = []
    
    for original_question, result in zip(questions_to_process, newly_processed_results):
        if result:
            processed_questions_dict[result['question_id']] = result
            successful_tasks += 1
        else:
            failed_question_ids.append(original_question['question_id'])
            
    final_data = sorted(processed_questions_dict.values(), key=lambda q: q['question_id'])
    
    with open(OUTPUT_PROCESSED_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(final_data, f, allow_unicode=True, sort_keys=False, indent=2)
        
    print(f"\n--- 処理結果サマリー ---")
    print(f"  今回処理した問題数: {len(questions_to_process)}問")
    print(f"  ✅ 正常に完了: {successful_tasks}問")
    if failed_question_ids:
        print(f"  ❌ 失敗: {len(failed_question_ids)}問 (問題ID: {sorted(failed_question_ids)})")
        print("     -> 失敗した問題は保存されていません。次回スクリプト実行時に再度処理されます。")
    print(f"\n💾 全{len(final_data)}問のデータを '{OUTPUT_PROCESSED_FILE}' に保存しました。")

if __name__ == "__main__":
    asyncio.run(main_async())