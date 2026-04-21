import re
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from ai_core import call_model, read_store, write_store
from pdf_gen import create_pdf

# Set to True to print every request/response to the terminal for debugging
DEBUG_LOG = False

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

SYSTEM_MSG = {
    "role": "system",
    "content": (
        "You are the MyEdMaster Legal Advice chatbot. "
        "Give clear legal information in plain language for business and education topics. "
        "You are not a lawyer and cannot create an attorney-client relationship. "
        "Tell users to contact a licensed attorney for final, jurisdiction-specific legal decisions."
    ),
}

DOCUMENT_SYSTEM_MSG = {
    "role": "system",
    "content": (
        "You are a legal document drafting assistant. Based on the conversation history, "
        "generate the requested legal document. Follow these rules strictly:\n"
        "- First line: document title only\n"
        "- Use UPPERCASE for section headers\n"
        "- Number each section (1. SECTION TITLE, 2. SECTION TITLE, etc.)\n"
        "- Where specific details like names, dates, amounts, or addresses are unknown, "
        "insert a blank: _________________________\n"
        "- Write in formal legal language\n"
        "- Do NOT use markdown formatting (no **, no #, no *, no ```)\n"
        "- Include standard legal clauses appropriate for the document type\n"
        "- End with signature blocks if applicable"
    ),
}

DOCUMENT_INTAKE_SYSTEM_MSG = {
    "role": "system",
    "content": (
        "You are MyEdMaster's document intake assistant. The user wants a legal document "
        "drafted as a PDF later. You are NOT writing the document yet — only gathering facts.\n\n"
        "In every reply:\n"
        "- Acknowledge the type of document they need (or clarify if unclear).\n"
        "- Give a short, plain-language background: what the document is for and which issues "
        "usually matter.\n"
        "- Ask focused follow-up questions adapted to their situation. Examples: for a roommate "
        "lease, ask whether they are a college student, on- vs off-campus, state or city, "
        "landlord involvement, rent split, term dates, utilities, guests, pets, and house rules. "
        "For other documents, ask what a lawyer in that area would need (parties, jurisdiction, "
        "dollar amounts, deadlines, risks).\n"
        "- Ask several concrete questions per message when helpful; you may go back and forth "
        "across multiple turns until details are sufficient.\n"
        "- Do not draft clauses, numbered sections, or signature blocks. No markdown (no **, #, "
        "*, or code fences).\n"
        "- End with one brief sentence that they can click Generate PDF when ready.\n\n"
        "You are not a lawyer; note that they should verify jurisdiction-specific points with "
        "local counsel."
    ),
}

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")

# Temporary in-memory store for generated PDFs (cleared on restart)
_pdf_store = {}


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


def _chat_title(messages):
    for m in messages:
        if m["role"] == "user":
            text = m["content"].strip()
            return (text[:48] + "...") if len(text) > 48 else text
    return "New chat"


# ── Chat API ──

@app.route("/api/chats", methods=["GET"])
def list_chats():
    store = read_store()
    chats = [
        {
            "id": cid,
            "title": d.get("title", "New chat"),
            "created": d.get("created", ""),
            "document_intake": d.get("document_intake", False),
        }
        for cid, d in store["chats"].items()
    ]
    chats.sort(key=lambda x: x["created"], reverse=True)
    return jsonify({"chats": chats, "active": store.get("active")})


@app.route("/api/chats", methods=["POST"])
def create_chat():
    store = read_store()
    cid = uuid.uuid4().hex[:12]
    store["chats"][cid] = {
        "title": "New chat",
        "created": datetime.now().isoformat(),
        "messages": [dict(SYSTEM_MSG)],
        "document_intake": False,
    }
    store["active"] = cid
    write_store(store)
    return jsonify({"id": cid}), 201


@app.route("/api/chats/<chat_id>", methods=["DELETE"])
def delete_chat(chat_id):
    store = read_store()
    if chat_id not in store["chats"]:
        return jsonify({"error": "Not found"}), 404
    del store["chats"][chat_id]
    if store["active"] == chat_id:
        store["active"] = None
    write_store(store)
    return jsonify({"ok": True})


@app.route("/api/chats/<chat_id>/messages", methods=["GET"])
def get_messages(chat_id):
    store = read_store()
    if chat_id not in store["chats"]:
        return jsonify({"error": "Not found"}), 404
    store["active"] = chat_id
    write_store(store)
    chat = store["chats"][chat_id]
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in chat["messages"]
        if m["role"] != "system"
    ]
    return jsonify(
        {
            "messages": messages,
            "document_intake": chat.get("document_intake", False),
        }
    )


@app.route("/api/chats/<chat_id>/messages", methods=["POST"])
def send_message(chat_id):
    store = read_store()
    if chat_id not in store["chats"]:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json()
    user_text = (body.get("message") or "").strip()
    if not user_text:
        return jsonify({"error": "Empty message"}), 400

    if DEBUG_LOG:
        print(f"\n[USER → {chat_id}] {user_text}")

    messages = store["chats"][chat_id]["messages"]
    messages.append({"role": "user", "content": user_text})

    try:
        reply = call_model(messages)
    except Exception as e:
        messages.pop()
        if DEBUG_LOG:
            print(f"[ERROR] {e}")
        return jsonify({"error": str(e)}), 502

    if DEBUG_LOG:
        print(f"[BOT  → {chat_id}] {reply[:120]}{'...' if len(reply) > 120 else ''}\n")

    messages.append({"role": "assistant", "content": reply})
    store["chats"][chat_id]["title"] = _chat_title(messages)
    write_store(store)
    return jsonify({"reply": reply})


# ── Document generation API ──

def _strip_markdown(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    return text


@app.route("/api/chats/<chat_id>/document", methods=["POST"])
def generate_document(chat_id):
    store = read_store()
    if chat_id not in store["chats"]:
        return jsonify({"error": "Not found"}), 404

    body = request.get_json() or {}
    finalize = bool(body.get("finalize"))
    user_text = (body.get("message") or "").strip()

    chat = store["chats"][chat_id]
    chat_messages = chat["messages"]

    if finalize:
        if not chat.get("document_intake"):
            return jsonify(
                {"error": "Describe the document you need first (document intake)."}
            ), 400

        final_user = user_text or (
            "Generate the complete legal PDF document from our discussion. "
            "Apply all drafting rules from your instructions."
        )

        if DEBUG_LOG:
            print(f"\n[DOC FINALIZE → {chat_id}] {final_user[:80]}…" if len(final_user) > 80 else f"\n[DOC FINALIZE → {chat_id}] {final_user}")

        chat_messages.append({"role": "user", "content": final_user})

        context = [m for m in chat_messages if m["role"] != "system"]
        prompt_messages = [DOCUMENT_SYSTEM_MSG, *context]

        try:
            raw_reply = call_model(prompt_messages)
        except Exception as e:
            chat_messages.pop()
            if DEBUG_LOG:
                print(f"[ERROR] {e}")
            return jsonify({"error": str(e)}), 502

        doc_text = _strip_markdown(raw_reply)

        lines = doc_text.strip().split("\n", 1)
        title = lines[0].strip()
        doc_body = lines[1].strip() if len(lines) > 1 else ""

        try:
            pdf_bytes = create_pdf(title, doc_body)
        except Exception as e:
            chat_messages.pop()
            if DEBUG_LOG:
                print(f"[PDF ERROR] {e}")
            return jsonify({"error": f"PDF generation failed: {e}"}), 500

        doc_id = uuid.uuid4().hex[:12]
        _pdf_store[doc_id] = pdf_bytes

        if DEBUG_LOG:
            print(f"[DOC GEN → {doc_id}] {title}\n")

        chat_messages.append({"role": "assistant", "content": f"[Document generated] {title}"})
        chat["document_intake"] = False
        chat["title"] = _chat_title(chat_messages)
        write_store(store)

        return jsonify(
            {
                "reply": doc_text,
                "doc_id": doc_id,
                "title": title,
                "document_intake": False,
                "phase": "complete",
            }
        )

    # Intake: Q&A until the user chooses Generate PDF
    if not user_text:
        return jsonify({"error": "Empty message"}), 400

    if DEBUG_LOG:
        print(f"\n[DOC INTAKE → {chat_id}] {user_text}")

    chat_messages.append({"role": "user", "content": user_text})

    context = [m for m in chat_messages if m["role"] != "system"]
    prompt_messages = [DOCUMENT_INTAKE_SYSTEM_MSG, *context]

    try:
        reply = call_model(prompt_messages)
    except Exception as e:
        chat_messages.pop()
        if DEBUG_LOG:
            print(f"[ERROR] {e}")
        return jsonify({"error": str(e)}), 502

    chat_messages.append({"role": "assistant", "content": reply})
    chat["document_intake"] = True
    chat["title"] = _chat_title(chat_messages)
    write_store(store)

    return jsonify(
        {
            "reply": reply,
            "document_intake": True,
            "phase": "intake",
        }
    )


@app.route("/api/documents/<doc_id>")
def download_document(doc_id):
    pdf_bytes = _pdf_store.get(doc_id)
    if not pdf_bytes:
        return jsonify({"error": "Document expired or not found"}), 404
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=MyEdMaster_Document.pdf"},
    )


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
