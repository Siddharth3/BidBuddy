import logging
import hashlib
import html
import ipaddress
from pathlib import Path
import uuid
import requests
import streamlit as st
from github_logger import log_interaction

from faq_engine import find_faq, answer_with_web

logger = logging.getLogger("bidbuddy.app")

# ============================================================
# 1. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Chalo BDBuddy",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# 2. APPLICATION SETTINGS
# ============================================================

COMPANY = "Chalo Mobility Pvt. Ltd."

BASE_DIR = Path(__file__).parent
LOGO_PATH = BASE_DIR / "assets" / "logo.png"

DEPARTMENTS = [
    "Operations",
    "Technology / IT",
    "Data & Analytics",
    "Finance",
    "HR",
    "Sales & Business Development",
    "Marketing",
    "Administration",
    "Other",
]

SUGGESTIONS = [
    "What documents are required for a tender submission?",
    "How do I check tender eligibility criteria?",
    "Where can I find company policies?",
]


# ============================================================
# 3. CUSTOM STYLING
# ============================================================

st.markdown(
    """
    <style>
        .stApp {
            background-color: #FFFDF9;
            color: #252525;
        }

        [data-testid="stHeader"] {
            background: rgba(255, 253, 249, 0.95);
        }

        .block-container {
            padding-top: 3rem;
            padding-bottom: 2rem;
            max-width: 1150px;
        }

        .brand-title {
            color: #F58220;
            font-size: 34px;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.35;
            margin: 0;
            padding-top: 4px;
            overflow: visible;
        }

        .brand-subtitle {
            color: #555555;
            font-size: 15px;
            margin-top: 3px;
        }

        .welcome-title {
            font-size: 28px;
            font-weight: 750;
            color: #292929;
            margin-bottom: 8px;
        }

        .muted-text {
            color: #666666;
            font-size: 14px;
            line-height: 1.6;
        }

        .feature-card {
            background: #FFFFFF;
            border: 1px solid #F1E5D8;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 10px;
        }

        div.stButton > button[kind="primary"],
        div.stFormSubmitButton > button[kind="primary"] {
            background: #F58220;
            border: 1px solid #F58220;
            color: white;
            border-radius: 8px;
            font-weight: 650;
            min-height: 44px;
        }

        div.stButton > button[kind="primary"]:hover,
        div.stFormSubmitButton > button[kind="primary"]:hover {
            background: #DE6D0B;
            border-color: #DE6D0B;
            color: white;
        }

        div[data-testid="stChatMessage"] {
            border-radius: 12px;
        }

        footer {
            visibility: hidden;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. BRAND HEADER
# ============================================================

def show_brand():
    left, right = st.columns(
        [1, 5],
        vertical_alignment="center",
    )

    with left:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=90)
        else:
            st.markdown(
                '<div style="font-size:42px; line-height:1.3;">🚌</div>',
                unsafe_allow_html=True,
            )

    with right:
        st.markdown(
            """
            <div style="padding-top: 6px; padding-bottom: 4px;">
                <div class="brand-title">BDBuddy</div>
                <div class="brand-subtitle">
                    Your internal knowledge assistant
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(COMPANY)
    st.divider()


# ============================================================
# 5. VISITOR PUBLIC IP DETECTION
# ============================================================

def get_visitor_ip():
    """Attempt to retrieve the visitor's public IP address."""

    try:
        context = st.context

        # Preferred option, when supported by the hosting platform.
        ip = getattr(context, "ip_address", None)

        # Fallback to proxy headers, if available.
        if not ip:
            headers = context.headers

            forwarded = headers.get("X-Forwarded-For", "")
            real_ip = headers.get("X-Real-IP", "")

            if forwarded:
                ip = forwarded.split(",")[0].strip()
            elif real_ip:
                ip = real_ip.strip()

        if not ip:
            return None

        parsed_ip = ipaddress.ip_address(ip)

        # Reject private, loopback, and other non-global IP addresses.
        if not parsed_ip.is_global:
            return None

        return str(parsed_ip)

    except Exception:
        return None


# ============================================================
# 6. APPROXIMATE LOCATION LOOKUP
# ============================================================


def get_ip_location(ip):
    """Retrieve approximate location while retaining the public IP."""

    result = {
        "status": "unavailable",
        "ip": ip,
        "city": None,
        "region": None,
        "country": None,
    }

    try:
        response = requests.get(
            f"https://ipapi.co/{ip}/json/",
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("error"):
            return result

        result.update({
            "status": "success",
            "city": data.get("city"),
            "region": data.get("region"),
            "country": data.get("country_name"),
        })

    except (requests.RequestException, ValueError):
        pass

    return result


# ============================================================
# 7. CHAT RESPONSE ENGINE
# ============================================================

def generate_assistant_response(question):
    """
    First use the approved internal FAQ.
    If there is no suitable FAQ, use Tavily + Gemini web fallback.
    """

    # Step 1: Search the approved internal FAQ.
    try:
        question_id = hashlib.sha256(
            " ".join(question.lower().split()).encode("utf-8")
        ).hexdigest()[:10]
        
        logger.info(
            "RESPONSE_START question_id=%s",
            question_id,
        )
        faq_result = find_faq(question)
        
    except Exception:
            # Continue to the web fallback if FAQ processing fails.
            logger.exception(
                "FAQ_PROCESSING_ERROR question_id=%s",
                question_id,
            )
            faq_result = None

    logger.info(
        "FAQ_RESULT question_id=%s matched=%s",
        question_id,
        bool(faq_result),
    )
    if faq_result:
        answer = faq_result.get("answer")

        if answer:
            logger.info(
                "RESPONSE_SOURCE question_id=%s source=faq",
                question_id,
            )
            return {
                "role": "assistant",
                "content": answer,
                "source": faq_result.get(
                    "source",
                    "Verified — Chalo BDBuddy",
                ),
                "sources": [],
                "answer_type": "faq",
            }

    # Step 2: No suitable FAQ found; try web search.
    try:
        web_result = answer_with_web(question)
    except Exception:
        web_result = None

    if web_result and web_result.get("success"):
        answer = web_result.get("answer", "").strip()

        if answer:
            # Retain only valid HTTP/HTTPS source links.
            valid_sources = []

            for item in web_result.get("sources", []):
                if not isinstance(item, dict):
                    continue

                url = item.get("url", "")

                if (
                    isinstance(url, str)
                    and url.startswith(("https://", "http://"))
                ):
                    valid_sources.append({
                        "title": item.get("title") or "Web source",
                        "url": url,
                    })
                    
            logger.info(
                "RESPONSE_SOURCE question_id=%s source=web",
                question_id,
            )
            
            return {
                "role": "assistant",
                "content": answer,
                "source": web_result.get(
                    "source",
                    "AI-generated from web sources — not an approved FAQ",
                ),
                "sources": valid_sources,
                "answer_type": "web",
            }

    # Step 3: Both paths failed or produced no usable answer.
    logger.warning(
        "RESPONSE_SOURCE question_id=%s source=unavailable",
        question_id,
    )

    return {
        "role": "assistant",
        "content": (
            "I couldn't find a reliable answer to your question right now. "
            "Please try rephrasing it or try again later. "
            "For official company information, please verify with the "
            "relevant internal team."
        ),
        "source": "No verified answer available",
        "sources": [],
        "answer_type": "unavailable",
    }



def process_question(question):
    """Generate an answer and log the interaction to GitHub."""

    question = question.strip()

    if not question:
        return

    st.session_state.messages.append({
        "role": "user",
        "content": question,
    })

    location = st.session_state.get("visitor_location") or {}

    location_text = ", ".join(
        item for item in [
            location.get("city"),
            location.get("region"),
            location.get("country"),
        ]
        if item
    )

    with st.spinner("BDBuddy is finding the best answer..."):
        response = generate_assistant_response(question)

    st.session_state.messages.append(response)

    # Log the interaction to the GitHub Excel workbook.
    try:
        employee = st.session_state.employee or {}

        source_urls = [
            item.get("url", "")
            for item in response.get("sources", [])
            if isinstance(item, dict) and item.get("url")
        ]

        log_interaction(
            user_name=employee.get("name", "Unknown"),
            department=employee.get("department", "Unknown"),
            conversation_id=st.session_state.conversation_id,
            question=question,
            answer=response.get("content", ""),
            answer_type=response.get("answer_type", "unknown"),
            sources=source_urls,
            public_ip=location.get("ip", ""),
            approximate_location=location_text,
        )

        logger.info("GitHub conversation logging succeeded.")

    except Exception:
        # Logging failures should not stop the chatbot from answering.
        logger.exception("GitHub conversation logging failed.")


# ============================================================
# 8. SESSION STATE
# ============================================================

if "employee" not in st.session_state:
    st.session_state.employee = None

if "visitor_location" not in st.session_state:
    st.session_state.visitor_location = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())


# ============================================================
# 9. ENTRY SCREEN
# ============================================================

if st.session_state.employee is None:

    show_brand()

    left, right = st.columns(
        [1.15, 1],
        gap="large",
    )

    # --------------------------------------------------------
    # LEFT SIDE: INTRODUCTION
    # --------------------------------------------------------

    with left:
        st.markdown(
            '<div class="welcome-title">Welcome to BDBuddy</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <p class="muted-text">
                Your internal knowledge assistant for tender-related
                information, bid preparation, business development,
                and company knowledge.
            </p>
            """,
            unsafe_allow_html=True,
        )

        st.write("")

        st.markdown(
            """
            <div class="feature-card">
                <strong>📄 Tender & RFP Support</strong><br>
                <span class="muted-text">
                    Find tender requirements, eligibility criteria,
                    submission documents, and certifications.
                </span>
            </div>

            <div class="feature-card">
                <strong>🤝 Business Development</strong><br>
                <span class="muted-text">
                    Access relevant proposal information,
                    service descriptions, and company capabilities.
                </span>
            </div>

            <div class="feature-card">
                <strong>📚 Company Knowledge</strong><br>
                <span class="muted-text">
                    Find internal information and reference material
                    from the available knowledge base.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # RIGHT SIDE: EMPLOYEE ENTRY FORM
    # --------------------------------------------------------

    with right:
        st.markdown("### Enter BDBuddy")

        st.caption("Enter your details to access the assistant.")

        with st.form("employee_entry"):

            name = st.text_input(
                "Full name *",
                placeholder="Enter your full name",
            )

            department = st.selectbox(
                "Department *",
                options=DEPARTMENTS,
            )

            st.divider()

            capture_location = st.checkbox(
                "I consent to public IP and approximate location lookup *",
                value=False,
            )

            st.caption(
                "Consent is required to continue. Your public IP may be "
                "used by an external service to estimate your location. "
                "Location lookup may fail or be inaccurate."
            )

            submitted = st.form_submit_button(
                "Enter BDBuddy →",
                type="primary",
                use_container_width=True,
            )

            # ------------------------------------------------
            # VALIDATE ENTRY
            # ------------------------------------------------

            if submitted:
                if not name.strip():
                    st.error("Please enter your full name.")

                elif not capture_location:
                    st.error("Please provide consent to continue.")

                else:
                    # Location lookup is best-effort. It must not block entry.
                    visitor_ip = get_visitor_ip()
                    location = {"status": "unavailable"}

                    if visitor_ip:
                        location = get_ip_location(visitor_ip)

                    st.session_state.employee = {
                        "name": name.strip(),
                        "department": department,
                    }

                    st.session_state.visitor_location = location
                    st.rerun()


# ============================================================
# 10. CHAT SCREEN
# ============================================================

else:

    employee = st.session_state.employee

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    with st.sidebar:

        show_brand()

        st.markdown("**Employee details**")
        st.write(employee["name"])
        st.caption(employee["department"])

        location = st.session_state.visitor_location

        if location:
            st.divider()
            st.markdown("**Connection details**")

            if location.get("status") == "success":

                st.caption(
                    f"Public IP: {location.get('ip', 'Unavailable')}"
                )

                place = ", ".join(
                    item
                    for item in [
                        location.get("city"),
                        location.get("region"),
                        location.get("country"),
                    ]
                    if item
                )

                st.caption(
                    f"Approximate location: {place or 'Unknown'}"
                )

            else:
                st.caption("IP/location lookup unavailable.")

        st.divider()

        if st.button("New chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_id = str(uuid.uuid4())
            st.rerun()

        if st.button("Exit BDBuddy", use_container_width=True):
            st.session_state.employee = None
            st.session_state.visitor_location = None
            st.session_state.messages = []
            st.rerun()

    # --------------------------------------------------------
    # MAIN CHAT AREA
    # --------------------------------------------------------

    show_brand()

    safe_name = html.escape(employee["name"])

    st.markdown(
        f'<p class="welcome-title">Hello, {safe_name} 👋</p>',
        unsafe_allow_html=True,
    )

    st.write("What would you like to know today?")

    # --------------------------------------------------------
    # SUGGESTED QUESTIONS
    # --------------------------------------------------------

    suggested_questions = [
        "Do we need an internet connection to run the ETIM?",
        "How are emergency alerts triggered, escalated, and resolved through the system?",
        "How many people use the Chalo App?",
        "How global is Chalo’s presence?"
    ]
    
    for question in suggested_questions:
        st.markdown(
            f"<div style='padding: 8px 0; color: #555; "
            f"font-size: 14px;'>{html.escape(question)}</div>",
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # DISPLAY CHAT HISTORY
    # --------------------------------------------------------

    for message in st.session_state.messages:

        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message["role"] == "assistant":

                source_label = message.get("source")

                if source_label:
                    st.caption(f"Source type: {source_label}")

                sources = message.get("sources", [])

                if sources:
                    st.markdown("**References**")

                    for source in sources:
                        title = source.get("title", "Web source")
                        url = source.get("url", "")

                        if url.startswith(("https://", "http://")):
                            st.markdown(f"- [{title}]({url})")

    # --------------------------------------------------------
    # CHAT INPUT
    # --------------------------------------------------------

    prompt = st.chat_input("Ask BDBuddy a question...")

    if prompt:
        process_question(prompt)
        st.rerun()
