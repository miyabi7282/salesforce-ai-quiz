import asyncio
from playwright.async_api import async_playwright
import yaml
import os
import re
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv

# .envファイルからAPIキーを読み込む
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- 設定項目 ---
GLOSSARY_URL_JA = "https://help.salesforce.com/s/articleView?id=sf.glossary.htm&type=5&language=ja"
GLOSSARY_URL_EN = "https://help.salesforce.com/s/articleView?id=sf.glossary.htm&type=5&language=en"
OUTPUT_FILE = "salesforce_basics_glossary.yaml"

CONTENT_SELECTOR = "div.slds-text-longform"
COOKIE_BUTTON_SELECTOR = "#onetrust-accept-btn-handler"

async def accept_cookies_if_present(page):
    try:
        await page.locator(COOKIE_BUTTON_SELECTOR).click(timeout=10000)
        print("✔ クッキー同意バナーを閉じました。")
        await page.wait_for_timeout(1000)
    except Exception:
        print("ℹ クッキーバナーは表示されませんでした。")

def parse_glossary_from_soup(soup_element):
    if not soup_element: return []
    glossary_list = []
    sections = soup_element.find_all('h2')
    for section in sections:
        dl_list = section.find_next_sibling('dl')
        if not dl_list: continue
        dts = dl_list.find_all('dt', recursive=False)
        dds = dl_list.find_all('dd', recursive=False)
        for i in range(min(len(dts), len(dds))):
            term = dts[i].get_text(strip=True)
            description = dds[i].get_text(strip=True)
            if term and description:
                glossary_list.append({"term": term, "description": description})
    return glossary_list

async def scrape_glossary_page(page, url):
    print(f"\n--- 用語集ページを処理中: {url} ---")
    await page.goto(url, wait_until="load", timeout=90000)
    await accept_cookies_if_present(page)
    await page.wait_for_timeout(3000)
    try:
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        content_div = soup.select_one(CONTENT_SELECTOR)
        if not content_div:
            raise Exception(f"本文エリア ('{CONTENT_SELECTOR}') が見つかりませんでした。")
        print("✔ 本文エリアを発見しました。テキストを解析します...")
        glossary_list = parse_glossary_from_soup(content_div)
        print(f"✔ {len(glossary_list)}件の用語を抽出しました。")
        return glossary_list
    except Exception as e:
        print(f"✖ 用語集の抽出に失敗しました: {e}")
        return []

# ★★★ AIによるペアリング関数 ★★★
async def pair_terms_with_gemini(ja_terms, en_terms):
    if not GEMINI_API_KEY:
        print("✖ Gemini APIキーが設定されていません。")
        return None

    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-pro')

    # AIに渡すためのリストを作成
    ja_list_str = "\n".join([f"- {item['term']}" for item in ja_terms])
    en_list_str = "\n".join([f"- {item['term']}" for item in en_terms])

    prompt = f"""
あなたはSalesforceの専門知識を持つプロの翻訳家です。
以下の日本語の用語リストと英語の用語リストを比較し、意味的に完全に一致するペアを見つけ出してください。

# 指示
- 2つのリストから、意味が同じになるペアを全て抽出してください。
- 英語の用語が日本語の用語の正確な対訳になっているペアのみを選んでください。
- 出力はJSON形式のリストのみとし、前後に説明文やマークダウンは一切含めないでください。
- 各ペアには、日本語の用語(`ja_term`)と英語の用語(`en_term`)の両方を含めてください。

# 出力フォーマットの例
[
  {{
    "ja_term": "取引先",
    "en_term": "Account"
  }},
  {{
    "ja_term": "取引先割り当てルール",
    "en_term": "Account Assignment Rule"
  }}
]

# 日本語の用語リスト
{ja_list_str}

# 英語の用語リスト
{en_list_str}

# JSON出力
"""
    print("\n🤖 Geminiに意味ベースでの日英ペアリングを依頼します...")
    try:
        response = await model.generate_content_async(prompt)
        # レスポンスからJSON部分を抽出
        json_text_match = re.search(r'\[.*\]', response.text, re.DOTALL)
        if json_text_match:
            return json.loads(json_text_match.group(0))
        else:
            print("✖ Geminiからの応答が期待したJSON形式ではありませんでした。")
            return None
    except Exception as e:
        print(f"✖ Gemini APIの呼び出し中にエラーが発生しました: {e}")
        return None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        ja_terms_list = await scrape_glossary_page(page, GLOSSARY_URL_JA)
        en_terms_list = await scrape_glossary_page(page, GLOSSARY_URL_EN)
        await browser.close()
        
        if not ja_terms_list or not en_terms_list:
            print("\n用語集の取得に失敗したため、処理を中断します。")
            return
            
        # AIを使ってペアリング
        paired_terms = await pair_terms_with_gemini(ja_terms_list, en_terms_list)
        
        if not paired_terms:
            print("\nAIによるペアリングに失敗しました。")
            return
            
        print(f"✔ AIが{len(paired_terms)}件のペアを見つけました。詳細情報をマージします...")

        # マージ処理
        final_dictionary = []
        ja_term_map = {item['term']: item['description'] for item in ja_terms_list}
        en_term_map = {item['term']: item['description'] for item in en_terms_list}

        for pair in paired_terms:
            ja_term = pair['ja_term']
            en_term = pair['en_term']
            if ja_term in ja_term_map and en_term in en_term_map:
                final_dictionary.append({
                    'en_term': en_term,
                    'ja_term': ja_term,
                    'en_description': en_term_map[en_term],
                    'ja_description': ja_term_map[ja_term]
                })

        if final_dictionary:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                yaml.dump(final_dictionary, f, allow_unicode=True, sort_keys=False, indent=2)
            print(f"\n✅ 全{len(final_dictionary)}件の日英対訳辞書を保存しました: {OUTPUT_FILE}")
        else:
            print("\n❌ 辞書の作成に失敗しました。")

if __name__ == "__main__":
    asyncio.run(main())