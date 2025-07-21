from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import yaml
import time
import os

# --- 設定項目 ---
DRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
BASE_URL = "https://www.jpnshiken.com"
HUB_PAGE_URL = "https://www.jpnshiken.com/shiken/Salesforce.Data-Cloud-Consultant-JPN.v2025-07-12.q74.html"
OUTPUT_FILENAME = "salesforce_exam_questions.yaml"

def get_question_links(driver, hub_url):
    print(f"目次ページにアクセス中: {hub_url}")
    try:
        driver.get(hub_url)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, "barlist")))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        question_list_dl = soup.find('dl', class_='barlist')
        links = [BASE_URL + a.get('href') for a in question_list_dl.find_all('a') if a.get('href')]
        print(f"{len(links)} 件の問題リンクが見つかりました。")
        return links
    except Exception as e:
        print(f"\nエラー: 目次ページの処理中にエラーが発生しました。 {e}")
        return []

def scrape_single_question_page(driver, question_url, question_id):
    try:
        driver.get(question_url)
        wait = WebDriverWait(driver, 30)
        
        # ★★★ ここが最終修正箇所です ★★★
        # 全てのクリックやスクロールを削除。
        # ただ、答えのブロックが表示されるのを待つだけ。
        wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "qa-answerexp")))
        time.sleep(1) # 描画が安定するのを1秒待つ

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 抽出の基準となる親要素を qa-question の親に変更
        parent_box = soup.find('div', class_='qa')
        if not parent_box: return None

        q_text_div = parent_box.find('div', class_='qa-question')
        q_text = q_text_div.get_text(strip=True) if q_text_div else "取得失敗"

        choices_div = parent_box.find('div', class_='qa-options')
        choices = {}
        if choices_div:
            for label in choices_div.find_all('label'):
                if '. ' in label.text:
                    key, value = label.text.strip().split('. ', 1)
                    choices[key.strip()] = value.strip()
                    
        answer_div = parent_box.find('div', class_='qa-answerexp')
        correct_answer, explanation = "", ""
        if answer_div:
            correct_answer_text_div = answer_div.find('div', style=lambda v: v and 'font-weight:bold' in v)
            if correct_answer_text_div and '正解：' in correct_answer_text_div.text:
                correct_answer = correct_answer_text_div.text.split('：')[1].strip()

            explanation_div = answer_div.find('div', class_='qa_explanation')
            if explanation_div:
                explanation = explanation_div.text.strip()
        
        return {'question_id': question_id, 'question_text': q_text, 'choices': choices, 'correct_answer': correct_answer, 'explanation': explanation}
    
    except Exception as e:
        print(f"\n--- エラー詳細: 質問 {question_id} ---")
        print(f"URL: {question_url}")
        print(f"エラーの種類: {type(e).__name__}")
        print(f"エラーメッセージ: {str(e).splitlines()[0]}")
        return None

def save_as_yaml(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, indent=2)
    print(f"\n成功: {len(data)}件の問題が {filename} に保存されました。")

# --- メイン処理 ---
if __name__ == "__main__":
    options = Options()
    options.binary_location = r"E:\GoogleChromePortable\App\Chrome-bin\chrome.exe"
    user_data_path = r"E:\GoogleChromePortable\Data\profile"
    profile_directory = "Default"
    options.add_argument(f"--user-data-dir={user_data_path}")
    options.add_argument(f"--profile-directory={profile_directory}")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    service = Service(executable_path=DRIVER_PATH)
    
    print("【重要】スクリプト実行前に、すべてのChromeウィンドウを手動で閉じてください。")
    print("準備が完了したら、このウィンドウでEnterキーを押してください...")
    input()

    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        question_urls = get_question_links(driver, HUB_PAGE_URL)
        if question_urls:
            all_questions_data = []
            for i, url in enumerate(question_urls, 1):
                print(f"問 {i}/{len(question_urls)} を処理中...", end="", flush=True)
                question_data = scrape_single_question_page(driver, url, i)
                if question_data:
                    all_questions_data.append(question_data)
                    print(" 完了")
                else:
                    print(" 失敗")
                time.sleep(1.5) # サーバー負荷を考慮し、少し長めに待機
            
            if all_questions_data:
                save_as_yaml(all_questions_data, OUTPUT_FILENAME)
            else:
                print("\nすべての問題の抽出に失敗しました。")
    finally:
        driver.quit()
        print("処理が完了し、ブラウザを閉じました。")