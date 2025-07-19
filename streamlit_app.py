import os
import yaml
import random
import streamlit as st

st.set_page_config(layout="wide")

EXAM_QUESTIONS_FILE = os.path.join("Salesforce_Question", "salesforce_exam_questions_final.yaml")

@st.cache_resource
def load_processed_data():
    if not os.path.exists(EXAM_QUESTIONS_FILE):
        st.error(f"'{EXAM_QUESTIONS_FILE}'が見つかりません。先にpreprocess_exam_data.pyを実行してください。")
        return None, None
    with open(EXAM_QUESTIONS_FILE, 'r', encoding='utf-8') as f:
        exam_questions = yaml.safe_load(f)
    questions_dict = {q['question_id']: q for q in exam_questions}
    sorted_questions_list = sorted(exam_questions, key=lambda q: q['question_id'])
    return questions_dict, sorted_questions_list

# CSSで色付けは「選択肢表示コンテナ内の特定クラスだけ」に限定。
# ボタンなど他のUI要素には絶対影響しないように。
st.markdown("""
<style>
    /* サイドバーの問題ボタン */
    section[data-testid="stSidebar"] .stButton > button {
        text-align: left !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block !important;
        width: 100% !important;
        justify-content: flex-start !important;
        border: 1px solid #DCDCDC !important;
        margin-bottom: 4px !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div:first-child {
        border-top: none !important;
    }

    /* 選択肢表示コンテナ限定 */
    .choice-container .correct-answer {
        background-color: #d4edda !important;
        color: #155724 !important;
        padding: 6px;
        border-radius: 5px;
        margin-bottom: 6px;
        font-weight: bold;
    }
    .choice-container .wrong-answer {
        background-color: #f8d7da !important;
        color: #721c24 !important;
        padding: 6px;
        border-radius: 5px;
        margin-bottom: 6px;
        font-weight: bold;
    }
    .choice-container .normal-answer {
        padding: 6px;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

questions_dict, sorted_questions_list = load_processed_data()
if not questions_dict:
    st.stop()

# セッション初期化
for key, default in {
    'page': 'start',
    'history': [],
    'current_index': -1,
    'answer_submitted': False,
    'user_answers': [],
    'answered_ids': set(),
    'wrong_answer_ids': set(),
    'is_review_mode': False,
    'review_history': [],
    'all_user_answers': {},
    'stats': {'contradicted_questions': []}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def get_current_question():
    if st.session_state.current_index == -1:
        return None
    active_list = st.session_state.review_history if st.session_state.is_review_mode else st.session_state.history
    if not active_list or st.session_state.current_index >= len(active_list):
        return None
    return questions_dict.get(active_list[st.session_state.current_index])

def go_to_question_by_id(q_id):
    st.session_state.page = 'quiz'
    st.session_state.is_review_mode = False
    st.session_state.answer_submitted = q_id in st.session_state.answered_ids
    if q_id not in st.session_state.history:
        st.session_state.history.append(q_id)
    st.session_state.current_index = st.session_state.history.index(q_id)
    st.session_state.user_answers = st.session_state.all_user_answers.get(q_id, [])

def go_to_next_question():
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
    if st.session_state.current_index > 0:
        st.session_state.current_index -= 1
        st.session_state.answer_submitted = True

# --- サイドバー ---
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

    for q in sorted_questions_list:
        q_id = q['question_id']
        prefix = "✅ " if q_id in st.session_state.answered_ids else "🟧 "
        label = f"{prefix}問 {q_id}: {q['question_text'][:30]}..."
        if st.button(label, key=f"jump_{q_id}", use_container_width=True):
            go_to_question_by_id(q_id)
            st.rerun()

# --- メイン画面 ---
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
                st.session_state.user_answers = sorted([k for k, v in user_selections.items() if v])

                if is_multiple_choice:
                    if len(st.session_state.user_answers) < num_correct_answers:
                        st.error(f"エラー: 正解は **{num_correct_answers}個** です。少なくともそれだけ選んでください。")
                    elif len(st.session_state.user_answers) > num_correct_answers:
                        st.error(f"エラー: 正解は **{num_correct_answers}個** です。選択肢はそれ以下にしてください。")
                    else:
                        st.session_state.answer_submitted = True
                        st.session_state.answered_ids.add(question['question_id'])
                        is_correct = (st.session_state.user_answers == correct_answers)
                        if not is_correct:
                            st.session_state.wrong_answer_ids.add(question['question_id'])
                        else:
                            st.session_state.wrong_answer_ids.discard(question['question_id'])
                        st.rerun()
                else:
                    if len(st.session_state.user_answers) != 1:
                        st.error("エラー: この問題では1つの選択肢のみ選べます。")
                    else:
                        st.session_state.answer_submitted = True
                        st.session_state.answered_ids.add(question['question_id'])
                        is_correct = (st.session_state.user_answers == correct_answers)
                        if not is_correct:
                            st.session_state.wrong_answer_ids.add(question['question_id'])
                        else:
                            st.session_state.wrong_answer_ids.discard(question['question_id'])
                        st.rerun()

    else:
        # 色付け用divで囲む（CSSスコープ限定）
        st.markdown('<div class="choice-container">', unsafe_allow_html=True)

        user_answers_set = set(st.session_state.user_answers)
        correct_answers_set = set(correct_answers)
        for key in choice_keys:
            text = f"{key}. {choices[key]}"
            if key in user_answers_set:
                if user_answers_set == correct_answers_set:
                    st.markdown(f'<div class="correct-answer">{text}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="wrong-answer">{text}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="normal-answer">{text}</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 分析結果")

    if st.session_state.answer_submitted:
        user_answer_str = ", ".join(st.session_state.user_answers)
        correct_answer_str = ", ".join(correct_answers)
        user_answers_set = set(st.session_state.user_answers)
        correct_answers_set = set(correct_answers)

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
