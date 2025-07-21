import os
import yaml
import faiss
import numpy as np
import google.generativeai as genai
import pickle
from dotenv import load_dotenv
import time
import json
import re

# .envファイルから環境変数を読み込む
load_dotenv()

# --- 設定項目 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ★★★ ここを実行日ごとに調整してください ★★★
START_INDEX = 0
END_INDEX = 74  # 1日の処理上限 (50 / 4 ≈ 12)

# 入力ファイル
EXAM_QUESTIONS_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions.yaml")
GLOSSARY_FILE = "salesforce_master_glossary.yaml"
FAISS_INDEX_FILE = "salesforce_docs.faiss"
TEXT_CHUNKS_FILE = "salesforce_docs_chunks.pkl"

# 出力ファイル（全部入り）
OUTPUT_PROCESSED_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions_final.yaml") # 出力ファイル名を変更

def translate_explanation(model, explanation, glossary_str):
    """Gemini APIを使って解説を翻訳する"""
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
        time.sleep(1.2) # レートリミット対策
        response = model.generate_content(translation_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"  - ✖ 翻訳エラー: {e}")
        return "（翻訳失敗）\n" + explanation

def search_candidate_chunks(query, index, chunks, embedding_model, k=10):
    """関連する可能性のあるヘルプドキュメントの「候補」を多めに検索する"""
    print("    - 関連ヘルプの候補を検索中...")
    try:
        time.sleep(1.2) # レートリミット対策
        query_vector = genai.embed_content(
            model=embedding_model,
            content=query,
            task_type="RETRIEVAL_QUERY"
        )['embedding']
        
        _, indices = index.search(np.array([query_vector]).astype('float32'), k)
        return [chunks[i] for i in indices[0]]
    except Exception as e:
        print(f"    - ✖ ヘルプ検索エラー: {e}")
        return []

def select_and_verify_docs_with_ai(model, question, candidate_docs):
    """
    候補ドキュメントの中から、Geminiが最適なものを厳選し、答えを検証する
    """
    print("    - AIによる関連ヘルプの厳選と答えの検証を実行中...")
    
    if not candidate_docs:
        return {
            'related_docs': [],
            'excluded_docs': [],
            'ai_verification': {'status': '判断不能', 'justification': '関連ドキュメントの候補が見つかりませんでした。'}
        }

    candidate_docs_str = "\n".join(
        [f"- title: {doc['title']}\n  url: {doc['source']}\n  text: \"{doc['text']}\"" for doc in candidate_docs]
    )
    
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
  "related_docs": [
    {{
      "title": "...",
      "url": "...",
      "reason": "...",
      "supporting_text": "..."
    }}
  ],
  "excluded_docs": [
    {{
      "title": "...",
      "reason": "..."
    }}
  ],
  "ai_verification": {{
    "status": "正答と一致 or 矛盾の可能性あり or 判断不能",
    "justification": "..."
  }}
}}
"""
    try:
        time.sleep(1.2) # レートリミット対策
        response = model.generate_content(prompt)
        
        json_text_match = re.search(r'```json\n(.*)\n```', response.text, re.DOTALL)
        if json_text_match:
            json_text = json_text_match.group(1)
        else:
            json_text = response.text
            
        return json.loads(json_text)
            
    except Exception as e:
        print(f"    - ✖ AIによる厳選・検証エラー: {e}")
        return {
            'related_docs': [],
            'excluded_docs': [],
            'ai_verification': {'status': 'エラー', 'justification': f'AI処理中にエラーが発生しました: {e}'}
        }

def main():
    if not GEMINI_API_KEY or "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        print("エラー: Gemini APIキーが.envファイルに設定されていません。")
        return

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-pro')
    embedding_model = "models/text-embedding-004"
    
    print("--- 必要なデータを読み込んでいます ---")
    glossary_str = ""
    if os.path.exists(GLOSSARY_FILE):
        with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
            glossary = yaml.safe_load(f)
            glossary_str = "\n".join([f"- {item['en_term']}: {item['ja_term']}" for item in glossary[:30]])
        print(f"✔ 用語集を読み込みました。")
    with open(EXAM_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        exam_questions = yaml.safe_load(f)
    print(f"✔ 試験問題を {len(exam_questions)} 問読み込みました。")
    index = faiss.read_index(FAISS_INDEX_FILE)
    with open(TEXT_CHUNKS_FILE, 'rb') as f:
        chunks = pickle.load(f)
    print(f"✔ ベクトルデータベースを読み込みました。")

    processed_questions = []
    current_start_index = START_INDEX
    if os.path.exists(OUTPUT_PROCESSED_FILE) and START_INDEX == 0:
        with open(OUTPUT_PROCESSED_FILE, 'r', encoding='utf-8') as f:
            processed_questions = yaml.safe_load(f) or []
        current_start_index = len(processed_questions)
        print(f"✔ 既存の処理済みファイルを検知。{current_start_index}問目まで完了済み。")
        print(f"  -> {current_start_index + 1}問目から再開します。")

    start = current_start_index
    end = END_INDEX
    
    if start >= len(exam_questions):
        print("\n全ての問がすでに処理されています。処理を終了します。")
        return
    if start >= end:
        print(f"\n今日の処理範囲 ({start+1}～{end}) は既に完了しています。END_INDEXを増やして再実行してください。")
        return

    questions_to_process = exam_questions[start:end]
    print(f"\n--- 問題 {start + 1} から {min(end, len(exam_questions))} までの事前処理を開始 ---")
    
    for i, question in enumerate(questions_to_process, 1):
        print(f"問 {start + i}/{len(exam_questions)} を処理中...")
        
        print("  - 解説を翻訳中...")
        jp_explanation = translate_explanation(model, question.get('explanation', ''), glossary_str)
        
        correct_answer_keys = [key.strip() for key in question['correct_answer'].split(',')]
        correct_answer_texts = [question['choices'].get(key, "") for key in correct_answer_keys]
        correct_answer_full_text = " ".join(correct_answer_texts)
        enhanced_query = f"{question['question_text']} {correct_answer_full_text} {jp_explanation}"
        
        candidate_chunks = search_candidate_chunks(enhanced_query, index, chunks, embedding_model)
        
        analysis_result = select_and_verify_docs_with_ai(model, question, candidate_chunks)
        
        processed_question = {
            'question_id': question['question_id'],
            'question_text': question['question_text'],
            'choices': question['choices'],
            'correct_answer': question['correct_answer'],
            'japanese_explanation': jp_explanation,
            'ai_analysis': analysis_result
        }
        processed_questions.append(processed_question)

    with open(OUTPUT_PROCESSED_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(processed_questions, f, allow_unicode=True, sort_keys=False, indent=2)
        
    print(f"\n✅ 全{len(processed_questions)}問の事前処理が完了しました。")
    print(f"結果を '{OUTPUT_PROCESSED_FILE}' に保存しました。")
    if len(processed_questions) < len(exam_questions):
        print("API上限に達した可能性があります。残りの問題は、明日以降にEND_INDEXを増やして再度実行してください。")

if __name__ == "__main__":
    main()