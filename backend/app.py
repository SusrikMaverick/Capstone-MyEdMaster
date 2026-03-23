import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from ai_core import call_model, read_store, write_store

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

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


def _chat_title(messages):
    for m in messages:
        if m["role"] == "user":
            text = m["content"].strip()
            return (text[:48] + "...") if len(text) > 48 else text
    return "New chat"


@app.route("/api/chats", methods=["GET"])
def list_chats():
    store = read_store()
    chats = [
        {"id": cid, "title": d.get("title", "New chat"), "created": d.get("created", "")}
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
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in store["chats"][chat_id]["messages"]
        if m["role"] != "system"
    ]
    return jsonify({"messages": messages})


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


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
