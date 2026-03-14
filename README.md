# Session Builder

Build teaching sessions by dragging & dropping modules from MongoDB.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open `index.html` in your browser (or serve it):

```bash
# Option A — just open the file directly in Chrome/Firefox
open index.html

# Option B — serve it (avoids any CORS edge cases)
python -m http.server 8080
# then visit http://localhost:8080
```

## How it works

### Backend (Flask — app.py)
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/classes` | GET | List all distinct class names |
| `/api/chapters?class_name=X` | GET | Chapters for a class |
| `/api/modules?class_name=X&chapter_number=1` | GET | Modules (can pass multiple chapters) |
| `/api/sessions` | GET | List all sessions |
| `/api/sessions` | POST | Create a session |
| `/api/sessions/<id>` | GET | Get one session |
| `/api/sessions/<id>` | PUT | Update session |
| `/api/sessions/<id>` | DELETE | Delete session |

### Session data model (MongoDB)
```
Session {
  session_name, description, class_name, chapter_number,
  items: [
    {
      position,           # order in session
      is_merge,           # true = fused module
      module_ids: [...],  # source module IDs
      merged_heading,     # heading shown in session
      merged_content,     # auto-concatenated content
    }
  ]
}
```

## Workflow
1. Pick a class from the dropdown
2. Tick one or more chapters → click **Load Modules**
3. Drag modules from the left panel into the builder (or click **+**)
4. Reorder with ↑↓ buttons or drag cards within the builder
5. To **merge**: click **⊕ Merge Mode**, tick 2+ cards, optionally type a merged heading, click **Merge Selected**
6. Type a session name and click **💾 Save Session**
7. View / load / delete saved sessions via **📋 Saved Sessions**
