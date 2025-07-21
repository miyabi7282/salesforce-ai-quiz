import os
import yaml
from dotenv import load_dotenv
import asyncio
from tqdm.asyncio import tqdm_asyncio
from google import genai
from google.genai import types
import re # 差分処理のためにreをインポート

# .envファイルから環境変数を読み込む
load_dotenv()

# --- あなたの元の設定項目 (変更なし) ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
INPUT_FILE = "salesforce_exam_questions_final.yaml"
OUTPUT_FILE = "undecided_questions_analysis_report.md"
MAX_CONCURRENT_TASKS = 3
MAX_QUESTIONS_TO_ANALYZE = 3

# 【追加】分析済みIDを読み込むためのヘルパー関数
def get_already_analyzed_ids(report_file):
    analyzed_ids = set()
    if not os.path.exists(report_file):
        return analyzed_ids
    with open(report_file, 'r', encoding='utf-8') as f:
        content = f.read()
    found_ids = re.findall(r'問題ID:\s*(\d+)', content)
    analyzed_ids = {int(id_str) for id_str in found_ids}
    return analyzed_ids

async def analyze_with_gemini(client, question_data):
    """
    自己修復型プロンプトを使用し、一度のAPIコールで
    「原因分析→情報検索→再評価」のサイクルを完結させる
    """
    # (あなたの元のコードから一切変更なし)
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
    if not os.getenv("GOOGLE_API_KEY"):
        print("エラー: 環境変数 'GOOGLE_API_KEY' が.envファイルに設定されていません。")
        return

    client = genai.Client()
    model_name_to_use = "gemini-1.5-pro-latest"

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
    
    analyzed_ids = get_already_analyzed_ids(OUTPUT_FILE)
    if analyzed_ids:
        print(f"ℹ️ {len(analyzed_ids)} 件の問題が既に分析済みです。")

    questions_to_analyze = [q for q in undecided_questions if q['question_id'] not in analyzed_ids]
    
    if not questions_to_analyze:
        print("✅ 全ての判断不能問題が分析済みです。処理を終了します。")
        return
        
    print(f"🎯 今回、{len(questions_to_analyze)}件の未分析問題を処理対象とします。")
    
    if MAX_QUESTIONS_TO_ANALYZE > 0 and len(questions_to_analyze) > MAX_QUESTIONS_TO_ANALYZE:
        questions_to_analyze = questions_to_analyze[:MAX_QUESTIONS_TO_ANALYZE]
        print(f"🔬 上限設定に基づき、そのうち {len(questions_to_analyze)} 件を分析します...")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    async def analyze_with_semaphore(question):
        async with semaphore:
            await asyncio.sleep(1)
            return await analyze_with_gemini(client, model_name_to_use, question)

    tasks = [analyze_with_semaphore(q) for q in questions_to_analyze]
    analysis_results = await tqdm_asyncio.gather(*tasks, desc="Analyzing questions")
    
    print(f"\n💾 分析レポートを '{OUTPUT_FILE}' に追記しています...")
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as f:
        # 【最終修正】レポートに記載済みの「## 問題 X」の数を数える
        # これにより、手動でレポートの一部を削除した場合でも、正しい通し番号が維持される
        existing_report_content = ""
        # ファイルが存在し、空でない場合のみ読み込む
        if os.path.exists(OUTPUT_FILE) and os.path.getsize(OUTPUT_FILE) > 0:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as rf:
                existing_report_content = rf.read()
        
        # レポート内の「## 問題 X」という見出しの数を数える
        existing_report_count = len(re.findall(r'^##\s*問題\s*\d+', existing_report_content, re.MULTILINE))
        start_index = existing_report_count
        
        # ファイルが新規作成された場合（ファイルサイズが0の場合）のみヘッダーを書き込む
        if f.tell() == 0:
            f.write("# RAGシステム「判断不能」問題の深掘り分析レポート\n\n")
            f.write("...\n\n---\n\n")
        
        # zipを使って、結果と元の質問データを正しくペアにする
        for i, (report, question_data) in enumerate(zip(analysis_results, questions_to_analyze)):
            if report and isinstance(report, str):
                # 問題番号を通し番号にする
                report_question_number = start_index + i + 1
                f.write(f"## 問題 {report_question_number} (ID: {question_data['question_id']}) の分析結果\n\n")
                f.write(report)
                f.write("\n\n---\n\n")
            
    print(f"✅ レポートへの追記が完了しました！ '{OUTPUT_FILE}' を確認してください。")

if __name__ == "__main__":
    # 以前エラーが出ていたWindows用のコードは削除済み
    asyncio.run(main())