import os
import yaml
import random
import streamlit as st

# --- 設定項目 ---
EXAM_QUESTIONS_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions_final.yaml")

@st.cache_resource
def load_processed_data():
    """事前処理済みの試験問題データをロードし、キャッシュする"""
    if not os.path.exists(EXAM_QUESTIONS_FILE):
        st.error(f"'{EXAM_QUESTIONS_FILE}'が見つかりません。先にpreprocess_exam_data.pyを実行してください。")
        return None, None
    with open(EXAM_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        exam_questions = yaml.safe_load(f)
    # question_idをキーにした辞書と、IDでソートされたリストの両方を準備
    questions_dict = {q['question_id']: q for q in exam_questions}
    sorted_questions_list = sorted(exam_questions, key=lambda q: q['question_id'])
    return questions_dict, sorted_questions_list

# --- アプリケーションのコア機能 ---

def get_current_question():
    """現在のインデックスに基づいて問題を取得する"""
    if st.session_state.current_index == -1: return None
    active_list = st.session_state.review_history if st.session_state.is_review_mode else st.session_state.history
    if not active_list or st.session_state.current_index >= len(active_list): return None
    q_id = active_list[st.session_state.current_index]
    return questions_dict.get(q_id)

def go_to_question_by_id(q_id):
    """指定されたIDの問題にジャンプする"""
    st.session_state.page = 'quiz'
    st.session_state.is_review_mode = False
    st.session_state.answer_submitted = q_id in st.session_state.answered_ids
    if q_id not in st.session_state.history:
        st.session_state.history.append(q_id)
    st.session_state.current_index = st.session_state.history.index(q_id)
    st.session_state.user_answers = st.session_state.all_user_answers.get(q_id, [])

def go_to_next_question():
    """次の問題へ進むロジック"""
    st.session_state.answer_submitted = False
    st.session_state.user_answers = []
    active_list = st.session_state.review_history if st.session_state.is_review_mode else st.session_state.history
    if st.session_state.current_index < len(active_list) - 1:
        st.session_state.current_index += 1
    elif not st.session_state.is_review_mode:
        unseen_q_ids = list(set(questions_dict.keys()) - set(st.session_state.history))
        if not unseen_q_ids:
             st.toast("🎉 全ての問題を解きました！", icon="🥳")
             return
        new_q_id = sorted(unseen_q_ids)[0]
        st.session_state.history.append(new_q_id)
        st.session_state.current_index = len(st.session_state.history) - 1

def go_to_prev_question():
    """前の問題へ戻るロジック"""
    if st.session_state.current_index > 0:
        st.session_state.current_index -= 1
        st.session_state.answer_submitted = True

# --- Streamlit アプリケーションUI ---
st.set_page_config(page_title="Salesforce AI 試験対策クイズ", layout="wide")

# カスタムCSSを定義
st.markdown("""
<style>
    /* ボタンの共通スタイルを調整 */
    a.stButton button {
        text-align: left !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        width: 100%;
        text-decoration: none;
        padding: 0.25rem 0.75rem;
        border-radius: 0.5rem;
        font-weight: 400;
        line-height: 1.6;
        font-size: 14px;
    }
    /* 未解答問題ボタンのカスタムスタイル */
    .unanswered-btn {
        background-color: #FFF8DC !important; /* コーンシルク */
        color: #31333F !important;
        border: 1px solid #DCDCDC !important;
    }
    .unanswered-btn:hover {
        background-color: #FAFAD2 !important; /* マウスオーバー時 */
        border-color: #A9A9A9 !important;
    }
    /* 解答済み問題ボタンのスタイル */
    .answered-btn {
        background-color: #F0F2F6 !important; /* Streamlitのデフォルトの灰色に近い色 */
        color: #31333F !important;
        border: 1px solid #DCDCDC !important;
    }
    .answered-btn:hover {
        background-color: #E0E2E6 !important;
        border-color: #A9A9A9 !important;
    }
</style>
""", unsafe_allow_html=True)

questions_dict, sorted_questions_list = load_processed_data()
if not questions_dict:
    st.stop()

# セッション状態の初期化
if 'page' not in st.session_state:
    st.session_state.page = 'start'
if 'history' not in st.session_state:
    st.session_state.history = []
    st.session_state.current_index = -1
    st.session_state.answer_submitted = False
    st.session_state.user_answers = []
    st.session_state.answered_ids = set()
    st.session_state.wrong_answer_ids = set()
    st.session_state.is_review_mode = False
    st.session_state.review_history = []
    st.session_state.all_user_answers = {}

# サイドバー
with st.sidebar:
    st.title("Salesforce AI クイズ")
    
    if st.session_state.wrong_answer_ids:
        if st.button(f"間違えた問題 ({len(st.session_state.wrong_answer_ids)}) を復習", use_container_width=True):
            st.session_state.page = 'quiz'
            st.session_state.is_review_mode = True
            st.session_state.review_history = random.sample(list(st.session_state.wrong_answer_ids), len(st.session_state.wrong_answer_ids))
            st.session_state.current_index = 0
            st.session_state.answer_submitted = False
            st.session_state.user_answers = []
            st.rerun()
    
    st.markdown("---")
    st.subheader("問題一覧")
    
    if "jump_to" in st.query_params:
        try:
            jump_to_id = int(st.query_params["jump_to"])
            go_to_question_by_id(jump_to_id)
            st.query_params.clear()
            st.rerun()
        except (ValueError, KeyError):
            st.query_params.clear()
            
    for q in sorted_questions_list:
        q_id = q['question_id']
        label = f"問 {q_id}: {q['question_text'][:30]}..."
        is_answered = q_id in st.session_state.answered_ids
        button_class = "answered-btn" if is_answered else "unanswered-btn"
        
        st.markdown(
            f'<a href="?jump_to={q_id}" target="_self" class="stButton"><button class="{button_class}">{label}</button></a>',
            unsafe_allow_html=True
        )
    
    st.markdown("---")
    st.caption("Developed with Gemini")

# メイン画面
st.title("Salesforce 資格試験 AIアシスタント")

if st.session_state.page == 'start':
    st.subheader("Salesforce Data Cloud 認定コンサルタント試験対策へようこそ！")
    st.write("このツールは、非公式の試験問題を基に、AIが公式ドキュメントと照らし合わせて解説とファクトチェックを行う学習支援ツールです。")
    if st.button("学習を開始する (問1から)", type="primary"):
        st.session_state.page = 'quiz'
        go_to_question_by_id(sorted_questions_list[0]['question_id'])
        st.rerun()

elif st.session_state.page == 'quiz':
    question = get_current_question()
    if not question:
        st.info("「学習を開始する」またはサイドバーから問題を選択してください。")
        st.stop()
    
    header_text = f"問題 {question['question_id']}"
    if st.session_state.is_review_mode:
        header_text = f"復習問題 {st.session_state.current_index + 1}/{len(st.session_state.review_history)} (元の問 {question['question_id']})"
    st.header(header_text)

    st.markdown("---")
    st.info(question['question_text'])

    choices = question['choices']
    choice_keys = sorted(choices.keys())
    correct_answers = sorted([key.strip() for key in question['correct_answer'].replace(" ", "").split(',')])
    num_correct_answers = len(correct_answers)
    is_multiple_choice = num_correct_answers > 1

    st.markdown("#### 選択肢")
    if is_multiple_choice and not st.session_state.answer_submitted:
        st.warning(f"この問題は **{num_correct_answers}個** の正解を選択してください。")

    if not st.session_state.answer_submitted:
        with st.form(key=f"answer_form_{question['question_id']}"):
            user_selections = {}
            for key in choice_keys:
                user_selections[key] = st.checkbox(f"{key}. {choices[key]}")
            
            submitted = st.form_submit_button("回答を決定", type="primary")
            if submitted:
                st.session_state.user_answers = sorted([key for key, checked in user_selections.items() if checked])
                st.session_state.all_user_answers[question['question_id']] = st.session_state.user_answers
                
                if not is_multiple_choice and len(st.session_state.user_answers) > 1:
                    st.error(f"エラー: この問題では1つの選択肢のみ選べます。")
                elif not st.session_state.user_answers:
                    st.error("エラー: 少なくとも1つの選択肢を選んでください。")
                else:
                    st.session_state.answer_submitted = True
                    st.session_state.answered_ids.add(question['question_id'])
                    is_correct = (sorted(st.session_state.user_answers) == correct_answers)
                    if not is_correct:
                        st.session_state.wrong_answer_ids.add(question['question_id'])
                    else:
                        st.session_state.wrong_answer_ids.discard(question['question_id'])
                    st.rerun()
    
    if st.session_state.answer_submitted:
        user_answers_set = set(st.session_state.user_answers)
        correct_answers_set = set(correct_answers)
        
        for key in choice_keys:
            display_text = f"**{key}.** {choices[key]}"
            is_correct_answer = key in correct_answers_set
            is_user_selection = key in user_answers_set

            if is_user_selection:
                # ユーザーが選んだ答えが正解かどうかの判定
                # 複数選択の場合はセットの一致、単一選択の場合は要素が含まれるかで判定
                is_submission_correct = (user_answers_set == correct_answers_set)
                
                if is_submission_correct:
                    st.success(display_text, icon="✅")
                else:
                    st.error(display_text, icon="❌")
            else:
                st.markdown(display_text)
        
        st.markdown("---")
        st.markdown("### 分析結果")
        
        user_answer_str = ", ".join(st.session_state.user_answers)
        correct_answer_str = ", ".join(correct_answers)

        if user_answers_set == correct_answers_set:
            st.success(f"🎉 **正解！**")
        else:
            st.error(f"❌ **不正解...** (あなたの回答: {user_answer_str} ／ 正解: {correct_answer_str})")
        
        ai_analysis = question.get('ai_analysis', {})
        st.markdown("#### AIによる答えの検証")
        verification = ai_analysis.get('ai_verification', {})
        status = verification.get('status', '不明')
        justification = verification.get('justification', '検証の理由がありません。')
        message = f"**AIの評価:** {justification}"
        if "一致" in status:
            st.info(message)
        elif "矛盾" in status or "判断不能" in status:
            st.warning(message)
            q_info = (question['question_id'], question['question_text'])
            if q_info not in st.session_state.stats['contradicted_questions']:
                st.session_state.stats['contradicted_questions'].append(q_info)
        else:
            st.error(message)

        st.markdown("#### 解説")
        st.write(question.get('japanese_explanation', '（日本語の解説が見つかりません）'))

        with st.expander("AIが厳選した関連ヘルプドキュメントを見る"):
            related_docs = ai_analysis.get('related_docs', [])
            if related_docs:
                for doc in related_docs:
                    st.caption(f"出典: {doc.get('title', 'N/A')}")
                    st.markdown(f"> **根拠:** {doc.get('supporting_text', 'N/A')}")
                    st.markdown(f"<a href='{doc.get('url', '#')}' target='_blank' rel='noopener noreferrer'>記事を読む ↗</a>", unsafe_allow_html=True)
                    st.divider()
            else:
                st.write("AIは、正答の根拠として適切なドキュメントを見つけられませんでした。")

        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ 前の問題へ", use_container_width=True, disabled=(st.session_state.current_index <= 0)):
                go_to_prev_question()
                st.rerun()
        with col2:
            active_list_for_nav = st.session_state.review_history if st.session_state.is_review_mode else st.session_state.history
            is_last_question_in_history = st.session_state.current_index >= len(active_list_for_nav) - 1
            has_unseen_questions = len(st.session_state.history) < len(questions_dict)
            
            if not is_last_question_in_history or (not st.session_state.is_review_mode and has_unseen_questions):
                if st.button("次の問題へ ➡️", use_container_width=True, type="primary"):
                    go_to_next_question()
                    st.rerun()