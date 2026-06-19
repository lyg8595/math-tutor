import streamlit as st
from streamlit_drawable_canvas import st_canvas
import requests
import json
import base64
import re
import time
import traceback
from datetime import datetime
from PIL import Image
import io
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="고2 수학 형성평가 AI 튜터", layout="centered", page_icon="✏️", initial_sidebar_state="collapsed")

# --- 2. 설정값 ---
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_MODEL = "gpt-4.1"
GOOGLE_SHEET_NAME = "수학튜터기록"
SERVICE_ACCOUNT_FILE = "service_account.json"
TEACHER_PASSWORD = "teacher1234"
ROSTER_SHEET = "명단"

HEADERS = [
    "시간", "학번", "이름",
    "문제 요약", "관련 성취기준", "대화 횟수", "학생 성찰",
    "성취 수준", "주요 취약점", "생기부 초안",
    "전체 대화 기록"
]

ACHIEVEMENT_STANDARDS = """
[2022 개정 교육과정 '대수' 성취기준 코드와 일반 성취수준 기준]

성취기준 코드(가장 가까운 것 선택):
- 지수·로그: [12대수01-01]거듭제곱근 [12대수01-03]지수법칙 [12대수01-04]로그 [12대수01-05]상용로그 [12대수01-07]지수로그함수 그래프 [12대수01-08]지수로그함수 활용
- 삼각함수: [12대수02-01]호도법 [12대수02-02]삼각함수 개념·그래프 [12대수02-03]사인·코사인법칙
- 수열: [12대수03-02]등차수열 [12대수03-03]등비수열 [12대수03-04]합의기호∑ [12대수03-05]여러가지 수열의 합 [12대수03-07]수학적 귀납법

일반 성취수준 등급(공통 기준):
 A: 개념·성질을 스스로 설명하고, 다양한/복합 문제를 논리적으로 해결
 B: 개념을 이해하고, 표준적인 문제를 정확히 해결
 C: 개념을 알고, 간단한 문제를 해결
 D: 뜻을 알고, 안내가 있으면 간단한 문제를 부분적으로 해결
 E: 안내된 절차를 따라야 겨우 해결
"""

SYSTEM_INSTRUCTION = f"""
너는 고등학교 2학년 학생들의 수학 학습을 돕는 친절하고 전문적인 1:1 맞춤형 수학 교사이다.
학생이 문제(사진 또는 텍스트)와 풀이 과정을 제출하면 아래 원칙을 철저히 지켜라.

[대화 태도]
- 말투는 '부드러운 해체'로 일관되게 유지하라. 예: "~해", "~해보자", "~할 수 있을까?", "좋아, 잘했어". 존댓말과 반말을 섞지 말고 처음부터 끝까지 담백하고 친근한 해체로만 대화하라.
- 한 번에 길게 쏟아내지 말고, 짧게 주고받으며 티키타카로 진행하라.
- 한 번의 답변에서는 '핵심 힌트 하나 + 이어지는 질문 하나' 정도로 끝내고 학생의 반응을 기다려라.

[손글씨·수식 인식 주의]
- 손글씨/사진 수식을 읽을 때 루트(√), 분수, 지수, 첨자, 절댓값을 정확히 구분하라. √13을 13으로 잘못 읽지 마라.
- 수식이 애매하면 단정하지 말고 "이거 √13 맞아?"처럼 먼저 확인 질문을 던져라.

[비계 설정(scaffolding) — 매우 중요]
1. 최종 정답이나 완성된 식을 직접 알려주지 마라. 힌트 질문과 부분적 단서만 단계적으로 제공하라.
2. 가장 중요한 건 학생이 '스스로 식·관계식을 세우는 것'이다. 식을 네가 먼저 제시하지 마라("이 식 계산해볼래?" 금지). 대신 "주어진 조건이 뭐야?", "그 조건을 식으로 어떻게 옮길까?" 같은 질문으로 사고를 끌어내라. 단순 계산은 학생이 식을 다 세운 뒤에만 다뤄라.
3. 수준에 따라 조절: 잘 따라오면 질문만; 막히면 단계를 더 잘게 쪼개되 식은 주지 마라; 개념 자체를 모르면 그 개념을 친절하고 자세히 예시로 설명한 뒤 다시 문제로 돌아와 적용하게 하라.
4. 틀려도 바로 고치지 말고 어디를 다시 볼지 질문으로 짚어줘라.

[출력] 수식은 줄바꿈 $$수식$$, 문장 안 $수식$ 형식. 기호 내부 불필요한 공백 금지.

[성취수준 판정 — 아래 기준 근거]
{ACHIEVEMENT_STANDARDS}

[진단 데이터 — 매 답변 맨 끝에 반드시 첨부 (학생 화면엔 숨겨짐). 초반엔 잠정으로라도 채워라]
   ---
   [교사용 진단 데이터]
   - 다룬 문제 요약: (한 줄)
   - 관련 성취기준: (가장 가까운 코드+이름. 예: [12대수03-02] 등차수열. 모르면 '파악 중')
   - 주요 취약점: ('식 세우기'/'계산'/'개념 결손' 중 어디인지 구체적으로. 모르면 '파악 중')
   - 성취 수준: (A~E 한 글자 + 근거를 괄호로. 예: B(개념 이해, 표준 문제 해결). 이르면 잠정)
   - 학교기록부 초안: (해결 과정·태도·성장 담은 공문서체 서술, 150자 내외)
"""

def optimize_image(pil_img, max_w, quality):
    img = pil_img.convert("RGB")
    if img.width > max_w:
        ratio = max_w / float(img.width)
        h = int(float(img.height) * ratio)
        img = img.resize((max_w, h), Image.Resampling.LANCZOS)
    return img

def pil_to_jpeg_bytes(pil_img, quality):
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return buf

def call_openai_rest_api(api_key, sys_instruct, history, img_list, user_msg):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    messages = [{"role": "system", "content": sys_instruct}]
    for role, text in history[-8:]:
        api_role = "assistant" if role == "assistant" else "user"
        messages.append({"role": api_role, "content": text})
    user_content = [{"type": "text", "text": (user_msg if user_msg else "[이미지 제출]")}]
    for img_obj in img_list:
        if img_obj is None:
            continue
        small = optimize_image(img_obj, max_w=768, quality=80)
        b = pil_to_jpeg_bytes(small, quality=80).getvalue()
        img_str = base64.b64encode(b).decode("utf-8")
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}})
    messages.append({"role": "user", "content": user_content})
    payload = {"model": OPENAI_MODEL, "messages": messages, "max_tokens": 1200}
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def extract_problem(api_key, pil_img):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    small = optimize_image(pil_img, max_w=1024, quality=90)
    b = pil_to_jpeg_bytes(small, quality=90).getvalue()
    img_str = base64.b64encode(b).decode("utf-8")
    instruction = (
        "이 사진에서 '수학 문제(문항)'만 찾아 텍스트로 옮겨 적어줘. "
        "학생이 손으로 쓴 풀이는 빼고, 주어진 문제 문항만 추출해. "
        "특히 루트(√), 분수, 지수, 첨자를 정확히 구분해서 읽어. √13을 13으로 잘못 읽지 않도록 주의해. "
        "수식은 문장 안은 $수식$, 별도 줄은 $$수식$$ 형식으로. "
        "도형이나 그림이 있으면 '(도형 있음)'이라고만 덧붙여. "
        "문제가 없으면 '문제 없음'이라고만 답하고, 그 외 다른 말은 붙이지 마."
    )
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}},
        ]}],
        "max_tokens": 500,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

def generate_student_report(api_key, student_name, records_text):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    instruction = (
        f"다음은 '{student_name}' 학생이 AI 수학 튜터와 학습한 누적 기록이야. "
        "교사가 학생에게 피드백할 때 쓸 종합 리포트를 작성해줘. 포함할 것: "
        "1) 반복 강점, 2) 반복 취약점(식 세우기/계산/개념 중 어디인지), "
        "3) 성취수준 변화 흐름, 4) 다음 지도에서 집중할 구체적 제안 2~3가지. "
        "교사가 바로 참고할 실용적 문체로 400자 내외.\n\n"
        f"[학습 기록]\n{records_text}"
    )
    payload = {"model": OPENAI_MODEL, "messages": [{"role": "user", "content": instruction}], "max_tokens": 800}
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

@st.cache_resource
def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open(GOOGLE_SHEET_NAME)

def check_roster(student_id, student_name):
    try:
        sh = get_gsheet()
        try:
            ws = sh.worksheet(ROSTER_SHEET)
        except gspread.WorksheetNotFound:
            return True
        rows = ws.get_all_values()
        if len(rows) <= 1:
            return True
        for row in rows[1:]:
            if len(row) >= 2:
                if str(row[0]).strip() == str(student_id).strip() and str(row[1]).strip() == str(student_name).strip():
                    return True
        return False
    except Exception:
        return True

def cleanup_default_sheet(sh):
    for name in ["시트1", "Sheet1"]:
        try:
            default_ws = sh.worksheet(name)
        except gspread.WorksheetNotFound:
            continue
        if len(sh.worksheets()) > 1:
            values = default_ws.get_all_values()
            if len(values) == 0 or (len(values) == 1 and not any(values[0])):
                try:
                    sh.del_worksheet(default_ws)
                except Exception:
                    pass

def get_or_create_worksheet(sh, ban_name):
    try:
        ws = sh.worksheet(ban_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ban_name, rows=2000, cols=len(HEADERS))
        ws.append_row(HEADERS)
        cleanup_default_sheet(sh)
        return ws
    if not ws.row_values(1):
        ws.append_row(HEADERS)
    return ws

def parse_diagnostic(text):
    def extract(label):
        pattern = rf"-\s*{label}\s*:\s*(.+?)(?=\n\s*-\s|\Z)"
        m = re.search(pattern, text, flags=re.DOTALL)
        return m.group(1).strip() if m else ""
    return {
        "problem_summary": extract("다룬 문제 요약"),
        "standard": extract("관련 성취기준"),
        "weakness": extract("주요 취약점"),
        "achievement": extract("성취 수준"),
        "record_draft": extract("학교기록부 초안"),
    }

def strip_diagnostic(text):
    if "[교사용 진단 데이터]" in text:
        idx = text.find("---")
        if idx >= 0:
            return text[:idx].strip()
    return text.strip()

defaults = {
    "logged_in": False, "student_id": "", "student_name": "", "ban": "",
    "chat_history": [], "latest_ai_diagnostic": "", "post_save_message": None,
    "canvas_key": "canvas_0", "show_canvas": False,
    "sheet_row": None, "self_reflection": "",
    "extracted_problem": "", "display_images": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

query_params = st.query_params
teacher_mode = (query_params.get("teacher", "") == TEACHER_PASSWORD)

if teacher_mode:
    st.title("📊 교사용 대시보드")
    st.caption("구글 시트에 누적된 학습 기록 · 성취수준은 2022 개정 교육과정 '대수' 기준")

    try:
        sh = get_gsheet()
        ws_list = sh.worksheets()
    except Exception as e:
        st.error(f"구글 연결 실패: {e}")
        st.stop()

    all_rows = []
    class_data = []
    for ws in ws_list:
        if ws.title in ("테스트", "시트1", "Sheet1", ROSTER_SHEET):
            continue
        values = ws.get_all_values()
        if len(values) >= 2:
            df = pd.DataFrame(values[1:], columns=values[0])
            df["__반__"] = ws.title
            class_data.append((ws.title, df))
            all_rows.append(df)

    if not class_data:
        st.info("아직 저장된 기록이 없습니다.")
        st.stop()

    all_df = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    view = st.radio("보기 선택", ["📋 반별 보기", "👤 학생별 종합 리포트"], horizontal=True)

    if view == "📋 반별 보기":
        tabs = st.tabs([t for t, _ in class_data])
        for tab, (title, df) in zip(tabs, class_data):
            with tab:
                c1, c2, c3 = st.columns(3)
                c1.metric("총 학습 기록", len(df))
                if "학번" in df.columns:
                    c2.metric("참여 학생 수", df["학번"].nunique())
                if "대화 횟수" in df.columns:
                    try:
                        c3.metric("평균 대화 횟수", round(pd.to_numeric(df["대화 횟수"], errors="coerce").mean(), 1))
                    except Exception:
                        pass
                if "성취 수준" in df.columns:
                    st.write("**성취 수준 분포**")
                    lv = df["성취 수준"].astype(str).str[0].replace("", "미평가")
                    st.bar_chart(lv.value_counts().sort_index())
                st.write("**요약 표**")
                summary_cols = ["시간", "학번", "이름", "문제 요약", "관련 성취기준", "대화 횟수", "학생 성찰", "성취 수준", "주요 취약점"]
                existing = [c for c in summary_cols if c in df.columns]
                st.dataframe(df[existing], use_container_width=True, hide_index=True)
                st.write("**학생별 상세**")
                for _, row in df.iloc[::-1].iterrows():
                    label = f"🕐 {row.get('시간','')} | {row.get('학번','')} {row.get('이름','')} | {row.get('문제 요약','')}"
                    with st.expander(label):
                        st.markdown(f"- **관련 성취기준**: {row.get('관련 성취기준','')}")
                        st.markdown(f"- **성취 수준**: {row.get('성취 수준','')}")
                        st.markdown(f"- **주요 취약점**: {row.get('주요 취약점','')}")
                        st.markdown(f"- **학생 성찰**: {row.get('학생 성찰','')}")
                        st.markdown(f"- **대화 횟수**: {row.get('대화 횟수','')}")
                        st.markdown("**📝 생기부 초안**")
                        st.info(row.get("생기부 초안", ""))
                        st.markdown("**💬 전체 대화 기록**")
                        st.text(row.get("전체 대화 기록", ""))
    else:
        if "학번" not in all_df.columns:
            st.info("학번 정보가 없습니다.")
            st.stop()
        all_df["__label__"] = all_df["학번"].astype(str) + " " + all_df.get("이름", "").astype(str)
        labels = sorted(all_df["__label__"].unique())
        chosen = st.selectbox("학생 선택", labels)
        chosen_id = chosen.split(" ")[0]
        sdf = all_df[all_df["학번"].astype(str) == chosen_id].copy()
        sname = sdf["이름"].iloc[0] if "이름" in sdf.columns and len(sdf) else ""

        st.subheader(f"👤 {chosen} — 종합 분석")
        c1, c2 = st.columns(2)
        c1.metric("총 학습 세션", len(sdf))
        if "대화 횟수" in sdf.columns:
            try:
                c2.metric("평균 대화 횟수", round(pd.to_numeric(sdf["대화 횟수"], errors="coerce").mean(), 1))
            except Exception:
                pass
        if "성취 수준" in sdf.columns and "시간" in sdf.columns:
            st.write("**성취 수준 변화 (시간순)**")
            st.dataframe(sdf.sort_values("시간")[["시간", "문제 요약", "성취 수준"]], use_container_width=True, hide_index=True)
        if "주요 취약점" in sdf.columns:
            st.write("**자주 나타난 취약점**")
            counts = {"식 세우기": 0, "계산": 0, "개념": 0}
            for w in sdf["주요 취약점"].astype(str):
                if "식" in w and "세우" in w:
                    counts["식 세우기"] += 1
                if "계산" in w:
                    counts["계산"] += 1
                if "개념" in w:
                    counts["개념"] += 1
            st.bar_chart(pd.Series(counts))
        if "문제 요약" in sdf.columns:
            st.write("**다룬 문제 목록**")
            for p in sdf["문제 요약"].tolist():
                st.markdown(f"- {p}")
        st.write("---")
        if st.button("🤖 AI 종합 피드백 생성하기"):
            records_text = ""
            for _, row in sdf.iterrows():
                records_text += (
                    f"[{row.get('시간','')}] 문제: {row.get('문제 요약','')} / "
                    f"성취수준: {row.get('성취 수준','')} / 취약점: {row.get('주요 취약점','')}\n"
                )
            try:
                with st.spinner("학생의 누적 기록을 분석하는 중..."):
                    report = generate_student_report(OPENAI_API_KEY, sname, records_text)
                st.markdown("**📑 AI 종합 피드백**")
                st.success(report)
            except Exception as e:
                st.error(f"리포트 생성 오류: {e}")

    st.write("---")
    st.caption(f"📂 구글 시트: **{GOOGLE_SHEET_NAME}**")
    st.stop()

if not st.session_state["logged_in"]:
    st.title("👨‍🏫 고2 수학 형성평가 AI 튜터")
    st.write("학습을 시작하기 위해 아래 정보를 입력해 주세요.")
    student_id = st.text_input("학번 (예: 20415)", max_chars=5)
    student_name = st.text_input("이름")
    if st.button("입력 완료"):
        if not (len(student_id) == 5 and student_id.isdigit() and student_name.strip()):
            st.error("올바른 학번(5자리 숫자)과 이름을 입력해 주세요.")
        elif not check_roster(student_id, student_name.strip()):
            st.error("명단에 없거나 학번과 이름이 일치하지 않습니다. 선생님께 문의하세요.")
        else:
            st.session_state["logged_in"] = True
            st.session_state["student_id"] = student_id
            st.session_state["student_name"] = student_name.strip()
            st.session_state["ban"] = f"2학년 {int(student_id[1:3])}반"
            st.rerun()
    st.stop()

if st.session_state["post_save_message"]:
    mtype, mtext = st.session_state["post_save_message"]
    (st.success if mtype == "success" else st.error)(mtext, icon=("✅" if mtype=="success" else "❌"))
    st.session_state["post_save_message"] = None

st.write(f"📌 **{st.session_state['ban']} {st.session_state['student_id']} {st.session_state['student_name']} 학생** 접속 중")
st.title("✏️ 수학 형성평가 튜터링룸")

if st.session_state["extracted_problem"] and st.session_state["extracted_problem"] != "문제 없음":
    st.info(f"【인식된 문제】\n\n{st.session_state['extracted_problem']}")

if st.session_state["display_images"]:
    st.write("**📎 첨부한 이미지**")
    for im in st.session_state["display_images"]:
        st.image(im, use_container_width=True)

def autosave():
    try:
        sh = get_gsheet()
        ws = get_or_create_worksheet(sh, st.session_state["ban"])
        diag = parse_diagnostic(st.session_state["latest_ai_diagnostic"])
        conv_lines = []
        for role, text in st.session_state["chat_history"]:
            if "[교사용 진단 데이터]" in text:
                continue
            speaker = "학생" if role == "user" else "AI 선생님"
            conv_lines.append(f"[{speaker}] {text}")
        conversation_text = "\n\n".join(conv_lines)
        student_turns = sum(1 for r, _ in st.session_state["chat_history"] if r == "user")
        problem = st.session_state["extracted_problem"] if st.session_state["extracted_problem"] not in ("", "문제 없음") else (diag["problem_summary"] or "(파악 중)")
        row_values = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            st.session_state["student_id"],
            st.session_state["student_name"],
            problem,
            diag["standard"],
            student_turns,
            st.session_state["self_reflection"],
            diag["achievement"],
            diag["weakness"],
            diag["record_draft"],
            conversation_text,
        ]
        if st.session_state["sheet_row"] is None:
            ws.append_row([str(v) for v in row_values], value_input_option="USER_ENTERED")
            st.session_state["sheet_row"] = len(ws.get_all_values())
        else:
            r = st.session_state["sheet_row"]
            ws.update(f"A{r}:K{r}", [[str(v) for v in row_values]], value_input_option="USER_ENTERED")
        return True, None
    except Exception:
        return False, traceback.format_exc()

def reset_for_new_problem():
    st.session_state["chat_history"] = []
    st.session_state["latest_ai_diagnostic"] = ""
    st.session_state["sheet_row"] = None
    st.session_state["self_reflection"] = ""
    st.session_state["extracted_problem"] = ""
    st.session_state["display_images"] = []
    st.session_state["canvas_key"] = f"canvas_{int(time.time()*1000)}"

for role, text in st.session_state["chat_history"]:
    if "[교사용 진단 데이터]" in text:
        continue
    avatar = "🧑‍🎓" if role == "user" else "👩‍🏫"
    with st.chat_message(role, avatar=avatar):
        st.markdown(text)

if not st.session_state["chat_history"]:
    with st.chat_message("assistant", avatar="👩‍🏫"):
        st.markdown("안녕! 😊 오늘 풀어볼 수학 문제를 알려줘. 사진으로 올려도 되고, 직접 타이핑해도 돼. 어떤 문제가 궁금해?")

toggle_label = "🖌️ 손글씨 풀이판 닫기" if st.session_state["show_canvas"] else "🖌️ 손글씨로 풀이 적기"
if st.button(toggle_label):
    st.session_state["show_canvas"] = not st.session_state["show_canvas"]
    st.rerun()

canvas_result = None
if st.session_state["show_canvas"]:
    c1, c2, c3 = st.columns([2.3, 1.7, 1.4])
    with c1:
        tool = st.radio("도구", ["✏️ 펜", "🧽 지우개"], horizontal=True, key="canvas_tool",
                        help="지우개를 고르고 칠하듯이 문지르면 그 부분이 지워져요.")
    with c2:
        stroke_width = st.slider("선 굵기", 1, 30, 4, key="stroke_width_slider")
    with c3:
        st.write("")
        if st.button("🗑️ 전체 지우기", use_container_width=True):
            st.session_state["canvas_key"] = f"canvas_{int(time.time()*1000)}"
            st.rerun()

    if tool == "🧽 지우개":
        eraser_width = max(stroke_width, 15)
        canvas_result = st_canvas(
            fill_color="rgba(255,255,255,0)", stroke_width=eraser_width, stroke_color="#FFFFFF",
            background_color="#FFFFFF", update_streamlit=True, height=300, width=680,
            drawing_mode="freedraw", key=st.session_state["canvas_key"],
        )
        st.caption("🧽 지우개로 칠하듯이 문질러서 지우세요. 다 지우려면 위의 '🗑️ 전체 지우기'를 누르세요.")
    else:
        canvas_result = st_canvas(
            fill_color="rgba(255,255,255,0)", stroke_width=stroke_width, stroke_color="#000000",
            background_color="#FFFFFF", update_streamlit=True, height=300, width=680,
            drawing_mode="freedraw", key=st.session_state["canvas_key"],
        )
        st.caption("✍️ 손글씨를 그렸으면, 아래 채팅창에 하고 싶은 말을 적고 보내면 그림이 함께 전송돼. (예: '이렇게 푸는 거 맞아?')")

chat_value = st.chat_input(
    "메시지를 입력하세요 (＋ 버튼으로 사진 첨부 가능)",
    accept_file=True, file_type=["png", "jpg", "jpeg"],
)

if chat_value:
    user_text = (chat_value.text or "").strip() if hasattr(chat_value, "text") else str(chat_value).strip()
    attached = chat_value.files if hasattr(chat_value, "files") else []

    photo_image = None
    if attached:
        photo_image = Image.open(attached[0]).convert("RGB")
        st.session_state["display_images"].append(photo_image)
        if not st.session_state["extracted_problem"]:
            try:
                prob = extract_problem(OPENAI_API_KEY, photo_image)
                if prob and prob != "문제 없음":
                    st.session_state["extracted_problem"] = prob
            except Exception:
                pass

    canvas_image = None
    if canvas_result is not None and canvas_result.json_data is not None:
        objs = canvas_result.json_data.get("objects", [])
        if len(objs) > 0 and canvas_result.image_data is not None:
            canvas_image = Image.fromarray(canvas_result.image_data.astype('uint8'), 'RGBA').convert("RGB")
            st.session_state["display_images"].append(canvas_image)

    images = [im for im in [photo_image, canvas_image] if im is not None]

    if not user_text and not images:
        st.warning("메시지를 입력하거나 사진/손글씨를 첨부해주세요.")
    else:
        marks = []
        if user_text:
            marks.append(user_text)
        if photo_image is not None:
            marks.append("_[📷 사진 첨부]_")
        if canvas_image is not None:
            marks.append("_[🖌️ 손글씨 첨부]_")
        st.session_state["chat_history"].append(("user", "\n\n".join(marks)))

        try:
            with st.spinner("선생님이 생각 중이에요..."):
                ai_reply = call_openai_rest_api(
                    OPENAI_API_KEY, SYSTEM_INSTRUCTION,
                    st.session_state["chat_history"], images,
                    user_text if user_text else ""
                )
            if "[교사용 진단 데이터]" in ai_reply:
                st.session_state["latest_ai_diagnostic"] = ai_reply[ai_reply.find("---"):]
                st.session_state["chat_history"].append(("assistant", strip_diagnostic(ai_reply)))
            else:
                st.session_state["chat_history"].append(("assistant", ai_reply))
            autosave()
            if canvas_image is not None:
                st.session_state["canvas_key"] = f"canvas_{int(time.time()*1000)}"
            st.rerun()
        except Exception as e:
            st.error(f"AI 응답 중 오류: {e}")

st.write("---")
st.caption("✨ (선택) 이 문제 학습이 끝났다면 나의 상태를 골라주세요.")
col1, col2, col3 = st.columns(3)
clicked = None
with col1:
    if st.button("😎 혼자서도 완벽히!", key="r1", use_container_width=True):
        clicked = "완벽 이해 (😎)"
with col2:
    if st.button("🤔 이해는 했지만 헷갈림", key="r2", use_container_width=True):
        clicked = "보완 필요 (🤔)"
with col3:
    if st.button("😭 기초 개념이 더 필요", key="r3", use_container_width=True):
        clicked = "기초 부족 (😭)"

if clicked:
    st.session_state["self_reflection"] = clicked
    ok, err = autosave()
    if ok:
        st.session_state["post_save_message"] = ("success", "성찰이 기록되었습니다! 계속 대화하거나 아래 '새 문제 시작'을 누르세요.")
    else:
        st.session_state["post_save_message"] = ("error", f"저장 실패:\n{err}")
    st.rerun()

if st.session_state["chat_history"]:
    if st.button("🔄 새 문제 시작하기"):
        reset_for_new_problem()
        st.rerun()