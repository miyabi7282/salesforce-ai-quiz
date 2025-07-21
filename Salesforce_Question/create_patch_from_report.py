import re
import yaml
import os

# --- 設定項目 ---
REPORT_FILE = "undecided_questions_analysis_report.md"
PATCH_OUTPUT_FILE = "patch_for_undecided.yaml"

def parse_analysis_report(report_content):
    """
    マークダウン形式の分析レポートを解析し、
    構造化されたデータのリストを返す。
    """
    
    # "---"で各問題のレポートに分割（最初のヘッダー部分は除く）
    report_blocks = report_content.split('---')[1:]
    
    patch_data_list = []

    for block in report_blocks:
        if not block.strip():
            continue

        # 問題IDを抽出
        id_match = re.search(r'##\s*問題\s*\d+\s*\(ID:\s*(\d+)\)\s*の分析結果', block)
        if not id_match:
            continue
        
        q_id = int(id_match.group(1))

        # --- 推奨情報源 (related_docs) の抽出 ---
        related_docs = []
        # URLとタイトルを抽出する正規表現
        # 例: * **URL:** [https://...](https://...)
        url_pattern = re.compile(r'\*\s*\[([^\]]+)\]\((https?://[^\)]+)\)')
        
        # "推奨される情報源"セクションを見つける
        source_section_match = re.search(r'##\s*2\.\s*不足知識を補うための推奨情報源\s*(.*?)(?=##\s*3\.|\Z)', block, re.DOTALL)
        if source_section_match:
            source_text = source_section_match.group(1)
            found_urls = url_pattern.finditer(source_text)
            for match in found_urls:
                title = match.group(1).strip()
                url = match.group(2).strip()
                # 後の説明文を取得しようと試みる
                reason_search_text = source_text[match.end():]
                reason_match = re.search(r'\*\s*推奨理由:\s*(.*?)(?=\n\n|\n\*\s*\[|\Z)', reason_search_text, re.DOTALL)
                reason = reason_match.group(1).strip().replace('\n', ' ') if reason_match else "AIによる推奨情報源です。"

                related_docs.append({
                    "title": title,
                    "url": url,
                    "reason": reason,
                    "supporting_text": "このドキュメントは、AIの追加調査によって正答の根拠として特定されました。"
                })

        # --- 最終評価 (ai_verification) の抽出 ---
        status = "判断不能" # デフォルト値
        justification = "分析レポートから自動生成された情報です。" # デフォルト値
        
        # "最終評価"セクションを見つける
        final_eval_match = re.search(r'##\s*3\.\s*追加情報を踏まえた最終評価\s*(.*)', block, re.DOTALL)
        if final_eval_match:
            eval_text = final_eval_match.group(1)
            
            # "結論：" からステータスを抽出
            status_match = re.search(r'結論\s*[:：]\s*([^\n]+)', eval_text, re.IGNORECASE)
            if status_match:
                status_text = status_match.group(1).strip()
                if "一致" in status_text:
                    status = "一致"
                elif "矛盾" in status_text:
                    status = "矛盾の可能性あり"
            
            # "理由：" または "根拠：" 以降をjustificationとして抽出
            just_match = re.search(r'(?:理由|根拠)\s*[:：]\s*(.*)', eval_text, re.DOTALL)
            if just_match:
                justification = just_match.group(1).strip().replace('\n', ' ')

        patch_data_list.append({
            "question_id": q_id,
            "ai_analysis": {
                "related_docs": related_docs,
                "ai_verification": {
                    "status": status,
                    "justification": justification
                }
            }
        })
        
    return patch_data_list


def main():
    if not os.path.exists(REPORT_FILE):
        print(f"❌ エラー: 分析レポートファイル '{REPORT_FILE}' が見つかりません。")
        return
        
    print(f"📄 '{REPORT_FILE}' を読み込んで解析しています...")
    with open(REPORT_FILE, 'r', encoding='utf-8') as f:
        report_content = f.read()
        
    patch_data = parse_analysis_report(report_content)
    
    if not patch_data:
        print("❌ レポートから有効な問題データを抽出できませんでした。")
        return

    print(f"💾 {len(patch_data)}件の修正パッチデータを '{PATCH_OUTPUT_FILE}' に保存します...")
    with open(PATCH_OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(patch_data, f, allow_unicode=True, sort_keys=False, indent=2)
        
    print("✅ パッチファイルの自動生成が完了しました！")
    print(f"👉 次に `merge_analysis_results.py` を実行して、このパッチを適用してください。")


if __name__ == "__main__":
    main()