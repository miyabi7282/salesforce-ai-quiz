import fitz  # PyMuPDF
import yaml
import re
import os
import glob


# --- 設定項目 ---
# スクリプトファイルがあるディレクトリを取得
BASE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# ★★★ ここを修正 ★★★
# PDFファイルは、スクリプトと同じディレクトリにあることを想定
PDF_DIRECTORY = BASE_DIRECTORY 

# 出力ファイルも、スクリプトと同じディレクトリに生成
OUTPUT_FILENAME = os.path.join(BASE_DIRECTORY, "salesforce_guides_consolidated.yaml")

# ★★★ 目次抽出関数を、より強力な「しおり」ベースの方法に刷新 ★★★
def extract_toc_from_pdf(doc):
    """PDFのしおり（Bookmark）情報から、正確な目次を抽出する"""
    toc = doc.get_toc() # get_toc()でしおり情報をリストとして取得
    
    if not toc:
        print("  - 警告: このPDFには「しおり」情報が見つかりませんでした。テキストベースの目次を試みます。")
        # しおりがない場合の代替案として、以前のロジックを残す
        return extract_toc_from_text(doc)

    # tocは [レベル, タイトル, ページ番号] のリストになっている
    # 例: [1, "Chapter 1: Salesforce Basics", 5]
    toc_titles = [item[1] for item in toc]
    
    print(f"  - 「しおり」を発見。{len(toc_titles)}件の見出しを抽出しました。")
    return toc_titles

def extract_toc_from_text(doc):
    """[代替案] テキストから目次を抽出する（以前のロジック）"""
    toc_titles = []
    found_toc = False
    for page_num in range(min(10, len(doc))):
        page = doc[page_num]
        text = page.get_text("text")
        if "CONTENTS" in text.upper() or "目次" in text:
            found_toc = True
            lines = text.split('\n')
            for line in lines:
                match = re.match(r'^\s*(?:Chapter\s+\d+\s*)?([A-Za-z\s,]{5,}|[ぁ-んァ-ン一-龥\s]{5,})\s*\.*', line)
                if match:
                    title = match.group(1).strip()
                    if len(title) > 4 and "..." not in title and not title.isdigit():
                         toc_titles.append(title)
    if not found_toc:
        print("  - 警告: テキストベースの目次ページも見つかりませんでした。")
    return list(dict.fromkeys(toc_titles))

def extract_text_from_pdf(doc):
    """PDFから全ページのテキストを抽出する"""
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    print(f"  - テキスト抽出完了")
    return full_text

def structure_text_into_sections(full_text, section_titles, source_filename):
    """与えられたセクションタイトルリストを元にテキストを分割する"""
    if not section_titles:
        print("  - 目次がないため、ドキュメント全体を一つのセクションとして扱います。")
        return [{
            'source_document': source_filename,
            'title': os.path.splitext(source_filename)[0],
            'content': full_text.strip()
        }]

    pattern = '|'.join(r'\n\s*' + re.escape(title) + r'\s*\n' for title in section_titles)
    
    content_parts = re.split(f'({pattern})', full_text, flags=re.IGNORECASE)
    
    structured_data = []
    if content_parts[0].strip():
        structured_data.append({
            'source_document': source_filename,
            'title': "Introduction",
            'content': content_parts[0].strip()
        })

    for i in range(1, len(content_parts), 2):
        title = content_parts[i].strip()
        content = content_parts[i+1].strip() if (i+1) < len(content_parts) else ""
        if content:
            clean_title = re.sub(r'\s+', ' ', title).strip()
            structured_data.append({
                'source_document': source_filename,
                'title': clean_title,
                'content': content
            })

    print(f"  - {len(structured_data)} 件のセクションに分割完了")
    return structured_data

def save_as_yaml(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, indent=2)
    print(f"\n成功！ 合計{len(data)}件の記事が '{filename}' に保存されました。")

# --- メイン処理 ---
if __name__ == "__main__":
    print(f"PDF検索フォルダ: {PDF_DIRECTORY}")

    if not os.path.isdir(PDF_DIRECTORY):
        print(f"エラー: '{PDF_DIRECTORY}' フォルダが見つかりません。")
    else:
        pdf_files = glob.glob(os.path.join(PDF_DIRECTORY, "*.pdf"))
        
        if not pdf_files:
            print(f"'{PDF_DIRECTORY}' フォルダ内にPDFファイルが見つかりませんでした。")
        else:
            print(f"{len(pdf_files)} 件のPDFファイルを検出しました。処理を開始します。")
            all_structured_data = []
            
            for pdf_path in pdf_files:
                filename = os.path.basename(pdf_path)
                print(f"\n--- 処理中: {filename} ---")
                
                try:
                    doc = fitz.open(pdf_path)
                    toc = extract_toc_from_pdf(doc)
                    raw_text = extract_text_from_pdf(doc)
                    structured_sections = structure_text_into_sections(raw_text, toc, filename)
                    all_structured_data.extend(structured_sections)
                    doc.close()
                except Exception as e:
                    print(f"  - エラー: {filename} の処理中に予期せぬエラーが発生しました: {e}")

            if all_structured_data:
                save_as_yaml(all_structured_data, OUTPUT_FILENAME)
            else:
                print("\n処理が完了しましたが、有効なデータを抽出できませんでした。")