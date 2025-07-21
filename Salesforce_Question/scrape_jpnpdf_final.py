import asyncio
import aiohttp
from bs4 import BeautifulSoup
import yaml
import time
import re
import sys

# --- 設定項目 ---
BASE_URL = "https://www.jpnpdf.com/Salesforce.Data-Cloud-Consultant.v2025-07-18.q128-mondaishu.html"
OUTPUT_FILENAME = "salesforce_exam_questions_from_web.yaml"
START_PAGE = 1
END_PAGE = 27
CONCURRENT_REQUESTS = 10

async def fetch_page(session, url):
    """指定されたURLから非同期でHTMLコンテンツを取得する"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            print(f"  - Fetching {url}... Status: {response.status}")
            response.raise_for_status()
            return await response.text()
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None

def parse_page_content(html_content, page_num):
    """1ページ分のHTMLコンテンツから全ての問題を解析する"""
    if not html_content: return []
    
    soup = BeautifulSoup(html_content, 'lxml')
    questions_on_page = []
    
    q_headers = soup.find_all('h4', class_='querstion-title')
    
    for header in q_headers:
        container = header.find_next_sibling('div', class_='qa')
        if not container: continue
        
        try:
            q_id_match = re.search(r'問題\s*(\d+)', header.get_text(strip=True))
            q_id = int(q_id_match.group(1)) if q_id_match else 0
            
            q_body_tag = container.find('div', class_='qa-question')
            q_body = q_body_tag.get_text('\n', strip=True) if q_body_tag else ""
            
            choices = {}
            options_div = container.find('div', class_=re.compile(r"qa-options"))
            if options_div:
                choice_items = options_div.find_all('li')
                for item in choice_items:
                    label_tag = item.find('label')
                    if not label_tag: continue
                    
                    strong_tag = label_tag.find('strong')
                    if not strong_tag: continue
                    
                    key = strong_tag.get_text(strip=True).replace(".", "")
                    strong_text = strong_tag.get_text(strip=True)
                    
                    full_label_text = label_tag.get_text(strip=True)
                    choice_text = full_label_text.replace(strong_text, "").strip()
                    
                    if key and choice_text:
                        choices[key] = choice_text

            # --- ここから解答抽出ロジックの修正 ---
            answer_div = container.find('div', class_=re.compile(r'qa-answerexp'))
            correct_answer = ""
            if answer_div:
                # '正解:'というテキストを含むdivを探し、その中のspanタグを取得
                answer_container = answer_div.find('div', style=lambda value: value and 'font-weight:bold' in value)
                if answer_container:
                    answer_span = answer_container.find('span')
                    if answer_span:
                        correct_answer = answer_span.get_text(strip=True)
            # --- 修正ここまで ---
            
            explanation = ""
            if answer_div:
                explanation_div = answer_div.find('div', class_='qa_explanation')
                explanation = explanation_div.get_text('\n', strip=True) if explanation_div else ""
            
            if q_id and q_body and choices: # 解答が空でもとりあえず抽出する
                questions_on_page.append({
                    'question_id': q_id,
                    'question_text': q_body,
                    'choices': choices,
                    'correct_answer': correct_answer,
                    'explanation': explanation.replace("説明\n", "").strip()
                })
        except Exception as e:
            q_id_text = f"QID {q_id}" if 'q_id' in locals() and q_id else 'Unknown Question'
            print(f"  - ⚠️  Warning: Could not fully parse {q_id_text} on page {page_num}. Error: {e}")
            
    return questions_on_page

async def main():
    print("🚀 Starting Asynchronous Scraper (Final Corrected Version)...")
    start_time = time.time()
    
    urls = [f"{BASE_URL}?p={i}" for i in range(START_PAGE, END_PAGE + 1)]
    all_questions = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_page(session, url) for url in urls]
        html_contents = await asyncio.gather(*tasks)
    
    print(f"\n🧠 Parsing all {len(html_contents)} downloaded pages...")
    
    for i, html in enumerate(html_contents):
        if html:
            page_num = START_PAGE + i
            questions_on_page = parse_page_content(html, page_num)
            all_questions.extend(questions_on_page)
        
    all_questions.sort(key=lambda x: x['question_id'])

    if all_questions:
        with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
            yaml.dump(all_questions, f, allow_unicode=True, sort_keys=False, indent=2)
        print(f"\n💾 Saved {len(all_questions)} questions to '{OUTPUT_FILENAME}'.")
    else:
        print("\n❌ No questions were extracted. Please check the HTML source again.")
        
    end_time = time.time()
    print(f"🎉 Process finished in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    if sys.platform.startswith('win') and sys.version_info >= (3, 8):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())