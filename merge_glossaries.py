import yaml
import os

# --- 設定項目 ---
# 入力となる2つの辞書ファイル
INPUT_FILES = [
    "salesforce_glossary_dictionary.yaml",    # Data Cloud専門用語集
    "salesforce_basics_glossary.yaml"         # Salesforce基本用語集
]

# 出力ファイル名
OUTPUT_FILE = "salesforce_master_glossary.yaml"

def main():
    print("--- 辞書のマージ処理を開始します ---")
    
    merged_terms = []
    seen_en_terms = set() # 重複チェック用のセット

    # 1. 各ファイルを順番に読み込む
    for filename in INPUT_FILES:
        if not os.path.exists(filename):
            print(f"警告: ファイル '{filename}' が見つかりません。スキップします。")
            continue
        
        with open(filename, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if not isinstance(data, list):
                print(f"警告: '{filename}' はリスト形式ではありません。スキップします。")
                continue
            
            print(f"✔ '{filename}' から {len(data)}件の用語を読み込みました。")
            
            # 2. 辞書の内容を結合
            for term_entry in data:
                # en_termをキーにして重複をチェック（大文字小文字を区別しない）
                en_term_lower = term_entry.get('en_term', '').lower()
                
                if en_term_lower and en_term_lower not in seen_en_terms:
                    merged_terms.append(term_entry)
                    seen_en_terms.add(en_term_lower)

    print(f"\n✔ マージと重複除去が完了しました。ユニークな用語数: {len(merged_terms)}件")

    # 3. 新しいファイルとして保存
    if merged_terms:
        # 英語の用語順でソートして、見やすくする
        sorted_merged_terms = sorted(merged_terms, key=lambda x: x.get('en_term', ''))
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            yaml.dump(sorted_merged_terms, f, allow_unicode=True, sort_keys=False, indent=2)
        print(f"✅ マスター辞書を '{OUTPUT_FILE}' に保存しました。")
    else:
        print("❌ マージするデータが見つかりませんでした。")

if __name__ == "__main__":
    main()