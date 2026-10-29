
import base64
import io
from datetime import datetime
from urllib.parse import quote

import requests
import streamlit as st
from openpyxl import Workbook, load_workbook


def log_interaction(
    user_name,
    department,
    conversation_id,
    question,
    answer,
    answer_type,
    sources=None,
):
    """Append one BidBuddy interaction to an Excel file in GitHub."""

    token = st.secrets["GITHUB_TOKEN"]
    repo = st.secrets["GITHUB_REPO"]
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    file_path = st.secrets.get(
        "GITHUB_XLSX_PATH",
        "data/bidbuddy_conversations.xlsx",
    )

    api_url = (
        f"https://api.github.com/repos/{repo}/contents/"
        f"{quote(file_path, safe='/')}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Retrieve the existing workbook, if present.
    response = requests.get(
        api_url,
        headers=headers,
        params={"ref": branch},
        timeout=30,
    )

    file_sha = None

    if response.status_code == 200:
        file_info = response.json()
        file_sha = file_info["sha"]
        file_bytes = base64.b64decode(file_info["content"])

        workbook = load_workbook(io.BytesIO(file_bytes))
        sheet = workbook.active

    elif response.status_code == 404:
        # Create a new workbook for the first interaction.
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Conversations"

        sheet.append([
            "Timestamp",
            "User Name",
            "Department",
            "Conversation ID",
            "Question",
            "Answer",
            "Answer Type",
            "Sources",
            "Public IP",
            "Approximate Location",
        ])

    else:
        raise RuntimeError(
            f"Could not read GitHub workbook (HTTP "
            f"{response.status_code}). Check repository settings "
            "and token permissions."
        )

    # Append the new interaction.
    if sheet.max_row == 1 and sheet["A1"].value != "Timestamp":
        sheet.append([
            "Timestamp",
            "User Name",
            "Department",
            "Conversation ID",
            "Question",
            "Answer",
            "Answer Type",
            "Sources",
            "Public IP",
            "Approximate Location",
        ])

    source_text = (
        "\n".join(sources)
        if isinstance(sources, (list, tuple))
        else (sources or "")
    )

    sheet.append([
        datetime.now().astimezone().isoformat(timespec="seconds"),
        user_name,
        department,
        conversation_id,
        question,
        answer,
        answer_type,
        source_text,
    ])

    # Serialize the workbook in memory.
    buffer = io.BytesIO()
    workbook.save(buffer)
    encoded_content = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    payload = {
        "message": "Log BidBuddy conversation",
        "content": encoded_content,
        "branch": branch,
    }

    if file_sha:
        payload["sha"] = file_sha

    # Create or update the workbook on GitHub.
    save_response = requests.put(
        api_url,
        headers=headers,
        json=payload,
        timeout=30,
    )

    if save_response.status_code not in (200, 201):
        raise RuntimeError(
            f"Could not save GitHub workbook (HTTP "
            f"{save_response.status_code})."
        )

    return True
