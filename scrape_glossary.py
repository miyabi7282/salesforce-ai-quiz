import asyncio
from playwright.async_api import async_playwright
import yaml
import os

# --- 設定項目 ---
GLOSSARY_URL_JA = "https://help.salesforce.com/s/articleView?id=data.c360_a_glossary_guide.htm&type=5&language=ja"
GLOSSARY_URL_EN = "https://help.salesforce.com/s/articleView?id=data.c360_a_glossary_guide.htm&type=5&language=en"

OUTPUT_FILE = "salesforce_glossary_dictionary.yaml"

async def accept_cookies_if_present(page):
    """クッキー同意バナーがあればクリックして閉じる"""
    try:
        await page.locator("#onetrust-accept-btn-handler").click(timeout=8000)
        print("✔ クッキー同意バナーを閉じました。")
        await page.wait_for_timeout(1000)
    except Exception:
        print("ℹ クッキーバナーは表示されませんでした。")

# ★★★ お客様のロジックを強化する新しい関数 ★★★
def parse_glossary_from_full_text(full_text):
    """
    ページ全体のテキストから、用語集の本体部分だけを抜き出して解析する
    """
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    # 本文の開始と終了の目印を定義
    start_marker_ja = "Data Cloud 用語集"
    end_marker_ja = "この記事で問題は解決されましたか?"
    start_marker_en = "Data Cloud Glossary of Terms"
    end_marker_en = "DID THIS ARTICLE SOLVE YOUR ISSUE?"

    start_index = -1
    end_index = len(lines)

    # 開始位置を探す
    for i, line in enumerate(lines):
        if start_marker_ja in line or start_marker_en in line:
            start_index = i + 1 # 見出しの次の行からが本文
            break
    
    if start_index == -1:
        print("✖ 本文の開始位置が見つかりませんでした。")
        return []

    # 終了位置を探す
    for i in range(start_index, len(lines)):
        line = lines[i]
        if end_marker_ja in line or end_marker_en in line:
            end_index = i
            break
            
    # 本文部分だけをスライス
    content_lines = lines[start_index:end_index]
    
    glossary_list = []
    i = 0
    while i < len(content_lines):
        term = content_lines[i]
        
        # アルファベット1文字の見出しはスキップ
        if len(term) == 1 and 'A' <= term <= 'Z':
            i += 1
            continue

        # 説明文を結合（複数行対応）
        description_parts = []
        i += 1
        while i < len(content_lines):
            next_line = content_lines[i]
            # 次の行が新しい用語のように見えたら説明は終わり
            # 条件：短い and 句読点で終わらない
            is_likely_new_term = len(next_line.split()) < 5 and not next_line.endswith(('。', '.', ':', 'ます。', '))'))
            
            # ただし、アルファベット1文字の見出しは用語ではないので、その前で止まらない
            if is_likely_new_term and not (len(next_line) == 1 and 'A' <= next_line <= 'Z'):
                break
            
            description_parts.append(next_line)
            i += 1

        if description_parts:
            description = " ".join(description_parts)
            glossary_list.append({
                "term": term,
                "description": description
            })
    
    return glossary_list

async def scrape_glossary_page(page, url):
    """用語集ページから用語と説明を抽出する"""
    print(f"\n--- 用語集ページを処理中: {url} ---")
    await page.goto(url, wait_until="load", timeout=90000)
    
    await accept_cookies_if_present(page)
    await page.wait_for_timeout(5000)

    try:
        # お客様のアイデア通り、ページ全体のテキストを取得
        full_text = await page.evaluate("() => document.body.innerText")
        
        # 強化された解析関数を呼び出す
        glossary_list = parse_glossary_from_full_text(full_text)

        print(f"✔ {len(glossary_list)} 件の用語を抽出しました。")
        return glossary_list

    except Exception as e:
        print(f"✖ 用語集の抽出に失敗しました: {e}")
        await page.screenshot(path="playwright_glossary_error.png")
        print("スクリーンショットを保存しました。")
        return []

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        ja_terms = await scrape_glossary_page(page, GLOSSARY_URL_JA)
        en_terms = await scrape_glossary_page(page, GLOSSARY_URL_EN)

        await browser.close()

        if not ja_terms or not en_terms:
            print("\n❌ 日本語または英語の用語が取得できなかったため、中断します。")
            return

        print("\n--- 日英用語集をマージ中 ---")
        final_dictionary = []

        num_terms = min(len(ja_terms), len(en_terms))
        if len(ja_terms) != len(en_terms):
            print(f"⚠️ 用語数が一致しません: JA={len(ja_terms)} / EN={len(en_terms)} → {num_terms}件でマージ")

        for i in range(num_terms):
            final_dictionary.append({
                'en_term': en_terms[i]['term'],
                'ja_term': ja_terms[i]['term'],
                'en_description': en_terms[i]['description'],
                'ja_description': ja_terms[i]['description']
            })

        if final_dictionary:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                yaml.dump(final_dictionary, f, allow_unicode=True, sort_keys=False, indent=2)
            print(f"\n✅ {len(final_dictionary)} 件の用語辞書を保存しました: {OUTPUT_FILE}")
        else:
            print("\n❌ 辞書の作成に失敗しました。")

if __name__ == "__main__":
    asyncio.run(main())