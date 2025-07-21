import asyncio
from playwright.async_api import async_playwright
import yaml
from urllib.parse import urljoin

# --- 設定項目 ---
START_URL = "https://help.salesforce.com/s/articleView?id=data.c360_a_product_considerations.htm&type=5&language=ja"
OUTPUT_FILE = "salesforce_help_articles.yaml"
# ★★★ お客様の発見による、真のサイドバーセレクタ ★★★
# クラス名が動的に変わる可能性を考慮し、部分一致で堅牢に指定
SIDEBAR_SELECTOR = "div[class*='table-of-content']" 
CONTENT_SELECTOR = "div.slds-text-longform"

async def accept_cookies_if_present(page):
    """クッキー同意バナーがあればクリックして閉じる"""
    try:
        await page.locator("#onetrust-accept-btn-handler").click(timeout=8000)
        print("✔ クッキー同意バナーを閉じました。")
        await page.wait_for_timeout(1000)
    except Exception:
        print("ℹ クッキーバナーは表示されませんでした。")

async def expand_all_sidebar_items(page):
    """サイドバーをスクロールしながら、見える範囲のボタンを繰り返しクリックする"""
    print("📂 サイドバーの全項目を展開します...")
    
    for i in range(10):
        # ★★★ 正しいサイドバーセレクタを使用 ★★★
        closed_buttons_locator = page.locator(f"{SIDEBAR_SELECTOR} button[aria-expanded='false']")
        
        clicked_in_this_pass = 0
        for button in await closed_buttons_locator.all():
            try:
                if await button.is_visible(timeout=500):
                    await button.scroll_into_view_if_needed(timeout=3000)
                    await button.click(timeout=1000)
                    clicked_in_this_pass += 1
                    await page.wait_for_timeout(50) 
            except Exception:
                pass
        
        if clicked_in_this_pass == 0:
            print(f"  ↪ パス {i+1}: これ以上展開できる項目はありませんでした。")
            break
        else:
            print(f"  ↪ パス {i+1}: {clicked_in_this_pass}個の項目を展開しました。")
    
    print("✔ 全てのメニュー展開が完了しました。")
    await page.wait_for_timeout(3000)

async def get_all_article_links(page):
    """locatorを使ってサイドバー内のリンクを全て取得する"""
    print("🔗 リンクを抽出中...")
    
    # ★★★ 正しいサイドバーセレクタを使用 ★★★
    link_selector = f"{SIDEBAR_SELECTOR} a[href*='/s/articleView?id=']"
    
    await page.locator(link_selector).first.wait_for(timeout=20000)
    
    links_locator = page.locator(link_selector)
    count = await links_locator.count()
    
    if count == 0:
        raise Exception("リンクが1件も見つかりません。")

    all_links = []
    for i in range(count):
        href = await links_locator.nth(i).get_attribute("href")
        if href:
            full_url = urljoin(page.url, href)
            all_links.append(full_url)

    unique_links = sorted(list(set(all_links)))
    print(f"✔ {len(unique_links)}件のユニークなリンクを取得しました。")
    return unique_links

async def scrape_article(page, url):
    """locatorを使って記事コンテンツを抽出する"""
    try:
        await page.goto(url, wait_until="load", timeout=60000)
        
        content_locator = page.locator(CONTENT_SELECTOR)
        await content_locator.wait_for(timeout=30000)
        
        title = await page.title()
        content = await content_locator.inner_text()
        
        return {
            "url": url,
            "title": title.strip(),
            "content": content.strip()
        }
    except Exception as e:
        print(f"❌ 記事取得失敗: {url}\n   理由: {str(e).splitlines()[0]}")
        return None

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print(f"\n📘 起点ページにアクセス: {START_URL}")
            await page.goto(START_URL, wait_until="load", timeout=90000)
            await accept_cookies_if_present(page)

            # ★★★ 正しいサイドバーセレクタを使用 ★★★
            await page.wait_for_selector(SIDEBAR_SELECTOR, timeout=30000)
            print("✔ サイドバーのコンテナを検出しました。")

            await expand_all_sidebar_items(page)
            
            article_links = await get_all_article_links(page)

            print("\n📰 記事コンテンツの収集中...")
            all_articles = []
            for i, url in enumerate(article_links, 1):
                print(f"[{i + 1}/{len(article_links)}] 取得中...")
                article = await scrape_article(page, url)
                if article:
                    all_articles.append(article)
                await page.wait_for_timeout(1000)

            if all_articles:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    yaml.dump(all_articles, f, allow_unicode=True, sort_keys=False, indent=2)
                print(f"\n✅ {len(all_articles)} 件の記事を {OUTPUT_FILE} に保存しました。")
            else:
                print("❌ 有効な記事が取得できませんでした。")

        except Exception as e:
            print(f"\n❌致命的なエラーが発生しました: {e}")
            await page.screenshot(path="playwright_fatal_error.png")
            print("エラー発生時のスクリーンショットを 'playwright_fatal_error.png' に保存しました。")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())