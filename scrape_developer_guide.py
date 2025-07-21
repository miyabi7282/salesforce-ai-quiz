import asyncio
from playwright.async_api import async_playwright
import yaml
from urllib.parse import urljoin
import json

# --- ★★★ 設定項目を「Developer Guide」用に変更 ★★★ ---
START_URL = "https://developer.salesforce.com/docs/data/data-cloud-dev/guide/dc-quick-start.html"
OUTPUT_FILE = "salesforce_data_cloud_developer_guide.yaml"
MAX_CONCURRENT_TASKS = 5

# --- CSSセレクタ (developer.salesforce.com共通) ---
MAIN_CONTENT_HOST_SELECTOR = "doc-content-layout"
COOKIE_BUTTON_SELECTOR = "#onetrust-accept-btn-handler"

# ★★★ 展開ボタンのセレクタを、より汎用的なものに微調整 ★★★
SIDEBAR_SELECTOR = "dx-sidebar"
SIDEBAR_BUTTON_SELECTOR = "dx-tree-item[aria-expanded='false']" # 前回うまくいかなかったセレクタが、こちらのサイトでは有効
SIDEBAR_LINK_SELECTOR = "dx-tree-tile > a[href]"
CONTENT_SELECTOR = "div.content-type-markdown"


async def accept_cookies_if_present(page):
    try:
        await page.locator(COOKIE_BUTTON_SELECTOR).click(timeout=10000)
        print("✔ クッキー同意バナーを閉じました。")
        await page.wait_for_timeout(1000)
    except Exception:
        print("ℹ クッキーバナーは表示されませんでした。")

def extract_links_from_json(json_data, base_url):
    links = set()
    for item in json_data:
        if 'link' in item and 'href' in item['link']:
            links.add(urljoin(base_url, item['link']['href']))
        if 'children' in item and item['children']:
            links.update(extract_links_from_json(item['children'], base_url))
    return links

async def get_all_article_links_from_json(page):
    print("🔗 埋め込みJSONからリンクを抽出中...")
    sidebar_content_str = await page.locator(MAIN_CONTENT_HOST_SELECTOR).get_attribute("sidebar-content")
    if not sidebar_content_str:
        raise Exception("サイドバーのJSONデータが見つかりません。")
    sidebar_data = json.loads(sidebar_content_str)
    links = extract_links_from_json(sidebar_data, page.url)
    unique_links = sorted(list(links))
    print(f"✔ {len(unique_links)}件のユニークなリンクを取得しました。")
    return unique_links

async def scrape_single_article(context, url, index, total):
    print(f"[{index}/{total}] 取得開始: {url.split('/')[-1]}")
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        
        host_locator = page.locator(MAIN_CONTENT_HOST_SELECTOR)
        await host_locator.wait_for(timeout=30000)
        
        title = await page.locator("h1").inner_text()
        content = await host_locator.inner_text()
        
        print(f"[{index}/{total}] ✔ 取得完了: {title[:30]}...")
        return {"url": url, "title": title.strip(), "content": content.strip()}
    except Exception as e:
        print(f"[{index}/{total}] ❌ 記事取得失敗: {url.split('/')[-1]}\n   理由: {str(e).splitlines()[0]}")
        return None
    finally:
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            print(f"\n📘 起点ページにアクセス: {START_URL}")
            await page.goto(START_URL, wait_until="load", timeout=90000)
            
            await accept_cookies_if_present(page)

            article_links = await get_all_article_links_from_json(page)
            await page.close()

            print(f"\n📰 記事コンテンツの収集中... (最大{MAX_CONCURRENT_TASKS}件の並列処理)")
            
            tasks = [scrape_single_article(context, url, i, len(article_links)) for i, url in enumerate(article_links, 1)]
            results = await asyncio.gather(*tasks)
            
            all_articles = [res for res in results if res is not None]

            if all_articles:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    yaml.dump(all_articles, f, allow_unicode=True, sort_keys=False, indent=2)
                print(f"\n✅ 全{len(all_articles)} 件の記事を {OUTPUT_FILE} に保存しました。")
            else:
                print("❌ 有効な記事が取得できませんでした。")

        except Exception as e:
            print(f"\n❌致命的なエラーが発生しました: {e}")
            if not page.is_closed():
                await page.screenshot(path="playwright_fatal_error_dev_guide.png")
                print("エラー発生時のスクリーンショットを保存しました。")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())