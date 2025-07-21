import asyncio
from playwright.async_api import async_playwright
import yaml
from urllib.parse import urljoin
import json

# --- 設定項目 ---
START_URL = "https://developer.salesforce.com/docs/data/data-cloud-ref/guide/c360a-api-intro-cdpapis.htm"
OUTPUT_FILE = "salesforce_data_cloud_reference_guide.yaml"
# ★★★ 並列処理の同時実行数を設定 ★★★
MAX_CONCURRENT_TASKS = 5

# --- CSSセレクタ ---
MAIN_CONTENT_HOST_SELECTOR = "doc-content-layout"
COOKIE_BUTTON_SELECTOR = "#onetrust-accept-btn-handler"

async def accept_cookies_if_present(page):
    """クッキー同意バナーがあればクリックして閉じる"""
    try:
        await page.locator(COOKIE_BUTTON_SELECTOR).click(timeout=10000)
        print("✔ クッキー同意バナーを閉じました。")
        await page.wait_for_timeout(1000)
    except Exception:
        print("ℹ クッキーバナーは表示されませんでした。")

def extract_links_from_json(json_data, base_url):
    """再帰的にJSONを探索し、全てのリンクを抽出する"""
    links = set()
    for item in json_data:
        if 'link' in item and 'href' in item['link']:
            links.add(urljoin(base_url, item['link']['href']))
        if 'children' in item and item['children']:
            links.update(extract_links_from_json(item['children'], base_url))
    return links

async def get_all_article_links_from_json(page):
    """ページの属性に埋め込まれたJSONから全リンクを取得する"""
    print("🔗 埋め込みJSONからリンクを抽出中...")
    sidebar_content_str = await page.locator(MAIN_CONTENT_HOST_SELECTOR).get_attribute("sidebar-content")
    if not sidebar_content_str:
        raise Exception("サイドバーのJSONデータが見つかりません。")
    sidebar_data = json.loads(sidebar_content_str)
    links = extract_links_from_json(sidebar_data, page.url)
    unique_links = sorted(list(links))
    print(f"✔ {len(unique_links)}件のユニークなリンクを取得しました。")
    return unique_links

# ★★★ 処理の単位となる関数を修正 ★★★
async def scrape_single_article(context, url, index, total):
    """
    新しいページを開いて単一の記事をスクレイピングし、結果を返す。
    contextを引数に取ることで、並列処理を可能にする。
    """
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
        # 処理が終わったら必ずページを閉じる
        await page.close()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            print(f"\n📘 起点ページにアクセス: {START_URL}")
            await page.goto(START_URL, wait_until="load", timeout=90000)
            
            # ★★★ クッキー処理はここで一度だけ実行 ★★★
            await accept_cookies_if_present(page)

            article_links = await get_all_article_links_from_json(page)
            # リンク取得が終わったら、最初のページはもう不要
            await page.close()

            print(f"\n📰 記事コンテンツの収集中... (最大{MAX_CONCURRENT_TASKS}件の並列処理)")
            
            # ★★★ ここからが並列処理のロジック ★★★
            tasks = []
            for i, url in enumerate(article_links, 1):
                # 各記事のスクレイピングを「タスク」としてリストに追加
                task = scrape_single_article(context, url, i, len(article_links))
                tasks.append(task)
            
            # asyncio.gatherでタスクを並列実行
            results = await asyncio.gather(*tasks)
            
            # 失敗した結果(None)を除外
            all_articles = [res for res in results if res is not None]

            if all_articles:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    yaml.dump(all_articles, f, allow_unicode=True, sort_keys=False, indent=2)
                print(f"\n✅ 全{len(all_articles)} 件の記事を {OUTPUT_FILE} に保存しました。")
            else:
                print("❌ 有効な記事が取得できませんでした。")

        except Exception as e:
            print(f"\n❌致命的なエラーが発生しました: {e}")
            # エラー発生時は、メインページがまだ開いている可能性があるのでスクリーンショットを試みる
            if not page.is_closed():
                await page.screenshot(path="playwright_fatal_error_ref_guide.png")
                print("エラー発生時のスクリーンショットを保存しました。")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())