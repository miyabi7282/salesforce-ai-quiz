import os
import yaml
import json
from dotenv import load_dotenv
import asyncio
from tqdm.asyncio import tqdm_asyncio
import re

# お客様の元のimport文を完全に維持します
from google import genai
from google.genai import types

# .envファイルから環境変数を読み込みます
load_dotenv()

# --- 設定項目 ---
# お客様の元の設定をベースに、出力ファイルを不要なため削除
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
YAML_FILE = "salesforce_exam_questions_final.yaml"
MAX_CONCURRENT_TASKS = 3
MAX_QUESTIONS_TO_ANALYZE = 5

async def analyze_with_gemini(client, question_data):
    """
    問題を分析し、マージに使用するai_analysisブロックをPythonの辞書として返す。
    """
    q = question_data
    # --- ★★★ お客様のアイデアを反映した、新しいJSON出力プロンプト ★★★ ---
    prompt = f"""
あなたはSalesforce認定試験のエキスパートです。以下の【問題】と【候補ドキュメントリスト】を分析し、指示に従ってJSON形式で出力してください。

# 問題
- question_id: {q['question_id']}
- question_text: {q['question_text']}
- choices: {q.get('choices')}
- correct_answer: {q.get('correct_answer')}
# (参考)RAGシステムの評価
{q.get('ai_analysis', {}).get('ai_verification', {}).get('justification', 'N/A')}

# 候補ドキュメントリスト
{q.get('ai_analysis', {}).get('related_docs', [])}

# 指示
1.  ウェブ検索を最大限に活用し、【問題】の【正答】を直接的または間接的に裏付ける最も信頼性の高い公式ドキュメントを最大3件見つけてください。
2.  見つけた各ドキュメントについて、以下の情報を含めてください。
   - `title`: ドキュメントのタイトル
   - `url`: ドキュメントのURL
   - `reason`: なぜこのドキュメントが正答の根拠として適切なのか、具体的な理由。
   - `supporting_text`: 正答の根拠となる、ドキュメント内の最も重要な一文または短いフレーズ。
3.  最終的に、検索して得た全ての情報を吟味した上で、【正答】が妥当かどうかを総合的に判断し、結論を記述してください。
    - **一致:** ドキュメントから正答が正しいと明確に判断できる場合。
    - **矛盾の可能性あり:** ドキュメントの情報が正答と食い違う、または不十分な場合。
    - **判断不能:** 提供されたドキュメントだけでは、正誤を全く判断できない場合。

# 出力フォーマット (JSON形式のみで回答すること。前後に説明や ```json のようなマークダウンは絶対に不要)
{{
  "related_docs": [
    {{
      "title": "ドキュメント1のタイトル",
      "url": "ドキュメント1のURL",
      "reason": "このドキュメントが正答の根拠として適切な具体的な理由。",
      "supporting_text": "正答の根拠となるドキュメント内の最も重要な一文。"
    }}
  ],
  "ai_verification": {{
    "status": "一致",
    "justification": "検索して得た全ての情報を吟味した上での、総合的な判断と、その詳細な理由。"
  }}
}}
"""
    try:
        # お客様の元のコードにあった、正しいツールの定義方法に戻します
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        # JSON強制をやめ、ツール利用のみを設定します
        config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )
        
        # お客様の元のAPI呼び出し構造を完全に維持します
        response = await client.aio.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=config
        )

        # AIの応答からJSON部分のみを賢く抽出します
        json_match = re.search(r'\{[\s\S]*\}', response.text)
        if json_match:
            json_string = json_match.group(0)
            # 後続の処理のため、IDと解析済みの辞書を返します
            return q['question_id'], json.loads(json_string)
        else:
            raise ValueError("AI response does not contain a valid JSON object.")

    except Exception as e:
        # エラー発生時も、自己修復のために辞書形式でエラー情報を返します
        error_data = {
            'ai_verification': {
                'status': '分析エラー', 
                'justification': f"問題ID {q['question_id']} の分析中にエラーが発生しました: {e}"
            },
            'related_docs': []
        }
        return q['question_id'], error_data

async def main():
    if not os.getenv("GOOGLE_API_KEY"):
        print("エラー: 環境変数 'GOOGLE_API_KEY' が.envファイルに設定されていません。")
        return

    # お客様の元の`genai.Client()`の呼び出しを維持します
    client = genai.Client()
    
    if not os.path.exists(YAML_FILE):
        print(f"❌ エラー: ファイル '{YAML_FILE}' が見つかりません。")
        return

    print(f"📄 '{YAML_FILE}' を読み込んでいます...")
    with open(YAML_FILE, 'r', encoding='utf-8') as f:
        all_questions = yaml.safe_load(f)

    # --- ★★★ 自己修復機能付きの更新対象抽出 ★★★ ---
    undecided_questions = [
        q for q in all_questions 
        if q.get('ai_analysis', {}).get('ai_verification', {}).get('status') in ['判断不能', '分析エラー', 'フォーマットエラー']
    ]
    
    if not undecided_questions:
        print("🎉 更新対象となる問題は見つかりませんでした！")
        return

    print(f"🔍 {len(undecided_questions)}件の更新対象の問題を検出しました。")
    
    questions_to_analyze = undecided_questions
    if MAX_QUESTIONS_TO_ANALYZE > 0 and len(questions_to_analyze) > MAX_QUESTIONS_TO_ANALYZE:
        questions_to_analyze = undecided_questions[:MAX_QUESTIONS_TO_ANALYZE]
        print(f"🔬 上限設定に基づき、そのうち {len(questions_to_analyze)} 件を分析します...")

    # お客様の元の非同期処理の構造を維持します
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    async def analyze_with_semaphore(question):
        async with semaphore:
            await asyncio.sleep(1)
            return await analyze_with_gemini(client, question)

    tasks = [analyze_with_semaphore(q) for q in questions_to_analyze]
    analysis_results = await tqdm_asyncio.gather(*tasks, desc="Analyzing questions")
    
    # --- ★★★ ここからが新しいファイル上書き処理です ★★★ ---
    print(f"\n🔄 '{YAML_FILE}' を直接更新しています...")
    
    questions_dict = {q['question_id']: q for q in all_questions}
    update_count = 0

    for question_id, new_analysis_data in analysis_results:
        if question_id in questions_dict and isinstance(new_analysis_data, dict):
            # AIが返した辞書で 'ai_analysis' ブロックを更新します
            questions_dict[question_id]['ai_analysis'] = new_analysis_data
            update_count += 1
        else:
            # 万が一、解析に失敗した場合はエラーとして記録し、次回再処理の対象とします
            error_status = {'ai_verification': {'status': 'フォーマットエラー', 'justification': 'AIからの応答が不正な形式でした。'}}
            questions_dict[question_id]['ai_analysis'] = error_status
            update_count += 1
            print(f"  - ⚠️ 問題ID {question_id} の更新に失敗。エラーとして記録しました。")

    if update_count > 0:
        print(f"\n💾 {update_count}件の問題を更新しました。ファイルを保存します...")
        with open(YAML_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(list(questions_dict.values()), f, allow_unicode=True, sort_keys=False, indent=2)
        print("✅ ファイルの更新が完了しました！")
    else:
        print("\n⚠️ 更新された問題はありませんでした。")

if __name__ == "__main__":
    asyncio.run(main())