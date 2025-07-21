import os
import yaml
from dotenv import load_dotenv
import asyncio
from tqdm.asyncio import tqdm_asyncio
from google import genai
from google.genai import types

# .envファイルから環境変数を読み込む
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INPUT_FILE = "salesforce_exam_questions_final.yaml"
OUTPUT_FILE = "undecided_questions_analysis_report.md"
MAX_CONCURRENT_TASKS = 3
MAX_QUESTIONS_TO_ANALYZE = 5

async def analyze_with_gemini(client, question_data):
    """
    自己修復型プロンプトを使用し、一度のAPIコールで
    「原因分析→情報検索→再評価」のサイクルを完結させる
    """
    q = question_data
    prompt = f"""
あなたはSalesforce Data Cloudのトップエキスパート兼リサーチアナリストです。
あなたのタスクは、以下の思考プロセスに従い、提供された【問題データ】を分析し、最終的な分析レポートを生成することです。

# 思考プロセス
1.  **初期評価:** まず、【問題データ】にある「RAGシステムの評価」を読み、なぜ「判断不能」と結論付けられたのか、その原因を推測します。正答を導くための鍵となる専門用語や概念を特定してください。
2.  **知識の欠落特定:** 初期評価に基づき、正答を完全に裏付けるためにどのような情報が欠けているかを明確にしてください。
3.  **ウェブ検索の実行（あなたの能力）:** 特定した欠落知識を補うため、あなたの持つGoogle検索能力を最大限に活用し、最も信頼できるSalesforceの公式ドキュメント（ヘルプ、開発者ガイド、Trailheadなど）を探してください。
4.  **追加情報の統合:** 検索で見つけたドキュメントの内容を熟読し、元の【問題データ】と統合して、あなたの知識をアップデートしてください。
5.  **最終判断:** アップデートされた知識を基に、改めて【問題データ】の正答が妥当であるかを再評価してください。今度は、「判断不能」ではなく、「一致」または「矛盾の可能性あり」という明確な結論とその根拠を記述してください。

# 問題データ
- **問題ID:** {q['question_id']}
- **問題文:** {q['question_text']}
- **選択肢:** {yaml.dump(q.get('choices', {}), allow_unicode=True)}
- **正答:** {q.get('correct_answer', 'N/A')}
- **(参考)非公式解説:** {q.get('japanese_explanation', 'N/A')}
- **(参考)RAGシステムの評価:** {q.get('ai_analysis', {}).get('ai_verification', {}).get('justification', 'N/A')}

# 出力フォーマット
上記の思考プロセスに従って生成した最終的な分析レポートを、以下のマークダウン形式で出力してください。

## 1. 「判断不能」の根本原因分析
(思考プロセス 1, 2 の結果をここに記述)

## 2. 不足知識を補うための推奨情報源
(思考プロセス 3 で見つけた、最も重要だと判断した公式ドキュメントのURLを最大3つ、その有用性の説明と共にリストアップ)

## 3. 追加情報を踏まえた最終評価
(思考プロセス 4, 5 の結果をここに記述。明確な結論と、検索で見つけた情報を根拠とした詳細な理由説明)
---
"""
    try:
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        config = types.GenerateContentConfig(
            tools=[grounding_tool]
        )
        response = await client.aio.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config=config
        )
        return response.text
    except Exception as e:
        return f"## 分析エラー\n\n問題ID {q['question_id']} の分析中にエラーが発生しました: {e}"

async def main():
    if not GOOGLE_API_KEY:
        print("エラー: APIキーが設定されていません。")
        return

    client = genai.Client()  # APIキーは環境変数から自動検出

    if not os.path.exists(INPUT_FILE):
        print(f"❌ エラー: ファイル '{INPUT_FILE}' が見つかりません。")
        return

    print(f"📄 '{INPUT_FILE}' を読み込んでいます...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        all_questions = yaml.safe_load(f)

    undecided_questions = [
        q for q in all_questions 
        if q.get('ai_analysis', {}).get('ai_verification', {}).get('status') == '判断不能'
    ]
    
    if not undecided_questions:
        print("🎉 判断不能な問題は見つかりませんでした！")
        return

    print(f"🔍 {len(undecided_questions)}件の「判断不能」な問題を検出しました。")
    
    questions_to_analyze = undecided_questions
    if MAX_QUESTIONS_TO_ANALYZE > 0 and len(undecided_questions) > MAX_QUESTIONS_TO_ANALYZE:
        questions_to_analyze = undecided_questions[:MAX_QUESTIONS_TO_ANALYZE]
        print(f"🔬 最初の {len(questions_to_analyze)} 件を分析します...")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    async def analyze_with_semaphore(question):
        async with semaphore:
            await asyncio.sleep(1)
            return await analyze_with_gemini(client, question)

    tasks = [analyze_with_semaphore(q) for q in questions_to_analyze]
    analysis_results = await tqdm_asyncio.gather(*tasks, desc="Analyzing questions")
    
    print(f"\n💾 分析レポートを '{OUTPUT_FILE}' に書き出しています...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# RAGシステム「判断不能」問題の深掘り分析レポート\n\n")
        f.write("...\n\n---\n\n")
        
        for i, report in enumerate(analysis_results):
            f.write(f"## 問題 {i+1} (ID: {questions_to_analyze[i]['question_id']}) の分析結果\n\n")
            f.write(report)
            f.write("\n\n---\n\n")
            
    print(f"✅ レポートが完成しました！ '{OUTPUT_FILE}' を確認してください。")

if __name__ == "__main__":
    asyncio.run(main())
