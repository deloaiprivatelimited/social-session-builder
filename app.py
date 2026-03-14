"""
Session Builder - Flask Backend
Run: python app.py
"""

import certifi
from flask import Flask, jsonify, request
from flask_cors import CORS
from mongoengine import (
    connect, Document, StringField, IntField,
    BooleanField, ListField, EmbeddedDocument,
    EmbeddedDocumentField, DateTimeField
)
from datetime import datetime
from bson import ObjectId
import json

app = Flask(__name__)
CORS(app)

# ─────────────────────────────────────────────
# DB CONNECTION
# ─────────────────────────────────────────────

MONGO_URI = "mongodb+srv://user:user@cluster0.rgocxdb.mongodb.net/education_db?retryWrites=true&w=majority"

connect(host=MONGO_URI, tlsCAFile=certifi.where())


# ─────────────────────────────────────────────
# EXISTING MODEL (read-only source)
# ─────────────────────────────────────────────

class Module(Document):
    class_name     = StringField(required=True)
    chapter_number = StringField(required=True)
    chapter_title  = StringField()
    module_id      = StringField(required=True, unique=True)
    module_number  = IntField()
    heading        = StringField()
    content        = StringField()
    section_gap_detected = BooleanField(default=False)

    meta = {
        "collection": "modules",
        "indexes": ["class_name", "chapter_number", "module_id"]
    }


# ─────────────────────────────────────────────
# SESSION MODELS
# ─────────────────────────────────────────────

class SessionItem(EmbeddedDocument):
    """
    One item in a session — either a single module or a merge of several.
    position : order in the session (0-based)
    is_merge : True when this item fuses multiple modules
    module_ids: list of source module_ids (length 1 for single, >1 for merge)
    merged_heading : custom heading chosen by user for merged item
    merged_content : concatenated content (auto-generated on save)
    """
    position        = IntField(required=True)
    is_merge        = BooleanField(default=False)
    module_ids      = ListField(StringField())
    merged_heading  = StringField()
    merged_content  = StringField()


class Session(Document):
    session_name   = StringField(required=True)
    description    = StringField()
    class_name     = StringField()
    chapter_number = StringField()
    items          = ListField(EmbeddedDocumentField(SessionItem))
    created_at     = DateTimeField(default=datetime.utcnow)
    updated_at     = DateTimeField(default=datetime.utcnow)

    meta = {
        "collection": "sessions",
        "indexes": ["session_name", "class_name"]
    }


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def oid(doc_id):
    return str(doc_id)


def module_to_dict(m):
    return {
        "id":             str(m.id),
        "module_id":      m.module_id,
        "module_number":  m.module_number,
        "class_name":     m.class_name,
        "chapter_number": m.chapter_number,
        "chapter_title":  m.chapter_title,
        "heading":        m.heading,
        "content":        m.content,
        "section_gap_detected": m.section_gap_detected,
    }


def session_to_dict(s):
    return {
        "id":             str(s.id),
        "session_name":   s.session_name,
        "description":    s.description,
        "class_name":     s.class_name,
        "chapter_number": s.chapter_number,
        "created_at":     s.created_at.isoformat() if s.created_at else None,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
        "items": [
            {
                "position":       item.position,
                "is_merge":       item.is_merge,
                "module_ids":     item.module_ids,
                "merged_heading": item.merged_heading,
                "merged_content": item.merged_content,
            }
            for item in s.items
        ],
    }


# ─────────────────────────────────────────────
# MODULE ROUTES
# ─────────────────────────────────────────────

@app.route("/api/classes", methods=["GET"])
def get_classes():
    """Return distinct class names."""
    classes = Module.objects.distinct("class_name")
    return jsonify(sorted(classes))


@app.route("/api/chapters", methods=["GET"])
def get_chapters():
    """Return chapters for a given class."""
    class_name = request.args.get("class_name")
    if not class_name:
        return jsonify({"error": "class_name required"}), 400

    pipeline = [
        {"$match": {"class_name": class_name}},
        {"$group": {
            "_id": "$chapter_number",
            "chapter_title": {"$first": "$chapter_title"}
        }},
        {"$sort": {"_id": 1}}
    ]
    results = list(Module.objects.aggregate(pipeline))
    chapters = [
        {"chapter_number": r["_id"], "chapter_title": r.get("chapter_title", "")}
        for r in results
    ]
    return jsonify(chapters)


@app.route("/api/modules", methods=["GET"])
def get_modules():
    """Return modules for given class + one or more chapters."""
    class_name = request.args.get("class_name")
    chapters   = request.args.getlist("chapter_number")   # ?chapter_number=1&chapter_number=2

    if not class_name:
        return jsonify({"error": "class_name required"}), 400

    query = Module.objects(class_name=class_name)
    if chapters:
        query = query.filter(chapter_number__in=chapters)

    modules = query.order_by("chapter_number", "module_number")
    return jsonify([module_to_dict(m) for m in modules])


# ─────────────────────────────────────────────
# SESSION ROUTES
# ─────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    sessions = Session.objects.order_by("-created_at")
    return jsonify([session_to_dict(s) for s in sessions])


@app.route("/api/sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    try:
        s = Session.objects.get(id=session_id)
    except Exception:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session_to_dict(s))


@app.route("/api/sessions", methods=["POST"])
def create_session():
    """
    Body:
    {
      "session_name": "Ancient History Ch3",
      "description": "...",
      "class_name": "Class 6",
      "chapter_number": "3",
      "items": [
        { "position": 0, "is_merge": false, "module_ids": ["mod_001"], "merged_heading": "" },
        { "position": 1, "is_merge": true,  "module_ids": ["mod_002","mod_003"], "merged_heading": "Combined Topic" }
      ]
    }
    """
    data = request.json
    if not data.get("session_name"):
        return jsonify({"error": "session_name required"}), 400

    items = _build_items(data.get("items", []))

    session = Session(
        session_name   = data["session_name"],
        description    = data.get("description", ""),
        class_name     = data.get("class_name", ""),
        chapter_number = data.get("chapter_number", ""),
        items          = items,
    )
    session.save()
    return jsonify(session_to_dict(session)), 201


@app.route("/api/sessions/<session_id>", methods=["PUT"])
def update_session(session_id):
    try:
        session = Session.objects.get(id=session_id)
    except Exception:
        return jsonify({"error": "Session not found"}), 404

    data = request.json
    if "session_name" in data:
        session.session_name = data["session_name"]
    if "description" in data:
        session.description = data["description"]
    if "class_name" in data:
        session.class_name = data["class_name"]
    if "chapter_number" in data:
        session.chapter_number = data["chapter_number"]
    if "items" in data:
        session.items = _build_items(data["items"])

    session.updated_at = datetime.utcnow()
    session.save()
    return jsonify(session_to_dict(session))


@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    try:
        s = Session.objects.get(id=session_id)
        s.delete()
        return jsonify({"deleted": True})
    except Exception:
        return jsonify({"error": "Session not found"}), 404


# ─────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────

def _build_items(raw_items):
    """
    For merged items, fetch all modules and concatenate their content.
    """
    items = []
    for raw in raw_items:
        module_ids = raw.get("module_ids", [])
        is_merge   = raw.get("is_merge", False) or len(module_ids) > 1

        merged_heading = raw.get("merged_heading", "")
        merged_content = raw.get("merged_content", "")

        if is_merge and module_ids:
            # Auto-build merged content from DB
            mods = Module.objects(module_id__in=module_ids)
            mod_map = {m.module_id: m for m in mods}
            # preserve order of module_ids
            parts = []
            headings = []
            for mid in module_ids:
                m = mod_map.get(mid)
                if m:
                    headings.append(m.heading or "")
                    parts.append(f"### {m.heading}\n\n{m.content}" if m.heading else m.content or "")
            if not merged_heading:
                merged_heading = " + ".join(h for h in headings if h)
            merged_content = "\n\n---\n\n".join(parts)

        items.append(SessionItem(
            position        = raw.get("position", len(items)),
            is_merge        = is_merge,
            module_ids      = module_ids,
            merged_heading  = merged_heading,
            merged_content  = merged_content,
        ))
    return items


# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("🚀  Session Builder API running at http://localhost:5000")
    app.run(debug=True, port=5000)
