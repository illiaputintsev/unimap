# Module Page API (`module.html`) - Frontend Handoff

This file documents the API + local state contract used by `/Users/illiaputintsev/studentroadmap/frontend/module.html`.

It covers:

- quiz generation (all 3 modes)
- PDF note upload/list/delete
- topic generation
- topic editing behavior (currently local-only)
- roadmap progress sync after quiz submit

Use this together with `/Users/illiaputintsev/studentroadmap/FRONTEND_API.md` and `/Users/illiaputintsev/studentroadmap/GRAPH_API.md`.

## Base URL

Uses the same backend base URL as `/Users/illiaputintsev/studentroadmap/FRONTEND_API.md`.

## Auth

Backend module endpoints require JWT auth.

- Header: `Authorization: Bearer <access_token>`
- Unauthenticated behavior in `module.html`:
  - topic/quiz generation falls back to local generator
  - PDF notes are stored locally only (no backend upload)

## Frontend API Methods (`ApiService`)

Implemented in `/Users/illiaputintsev/studentroadmap/frontend/api-service.js`.

- `ApiService.generateModuleTopics(payload)`
- `ApiService.generateModuleQuiz(payload)`
- `ApiService.listModuleNotes({ moduleId, roadmapId })`
- `ApiService.uploadModuleNote(formData)`
- `ApiService.deleteModuleNote(noteId)`
- `ApiService.updateRoadmapGraphTopicProgress(roadmapId, topicId, masteryPercent)` (progress sync)
- `ApiService.updateTopicProgress(topicId, masteryPercent)` (legacy fallback progress sync)

## 1) Generate Topics (Gemini-backed)

Endpoint:

`POST /api/quizzes/module-topics/generate/`

Auth: required

### Request body

```json
{
  "module_title": "Machine Learning",
  "roadmap_title": "Roadmap 123",
  "existing_topics": [
    { "title": "Linear Regression", "why_it_matters": "Foundation for supervised learning" }
  ],
  "note_excerpts": [
    { "name": "lecture1.pdf", "excerpt": "Supervised learning maps inputs to outputs..." }
  ],
  "count": 10
}
```

### Success (`200`)

```json
{
  "module_title": "Machine Learning",
  "topics": [
    {
      "title": "Supervised Learning Basics",
      "why_it_matters": "Helps build intuition for prediction problems"
    }
  ],
  "topics_count": 10,
  "source": "gemini",
  "model": "gemini-2.5-flash",
  "note": ""
}
```

### Frontend behavior

- `module.html` merges generated topics with existing topics (dedupe by title).
- Users can edit/add/remove topics after generation.
- Topic edits are currently local-only (see Local Topic Editing section).

## 2) Generate Quiz (All 3 Modes)

Endpoint:

`POST /api/quizzes/module-quiz/generate/`

Auth: required

This is the single backend endpoint used for:

- Practice Quiz (all topics)
- Focused Topic Quiz (one topic)
- Mock Exam

### Quiz mode mapping (frontend -> backend)

- Practice Quiz: `quiz_mode = "practice"`
- Focused Topic Quiz: `quiz_mode = "topic"`
- Mock Exam: `quiz_mode = "mock_exam"`

### Request body (common shape)

```json
{
  "module_title": "Machine Learning",
  "roadmap_title": "Roadmap 123",
  "quiz_mode": "practice",
  "topics": ["Linear Regression", "Logistic Regression", "Overfitting"],
  "note_excerpts": [
    { "name": "lecture1.pdf", "excerpt": "Bias-variance tradeoff..." }
  ],
  "mistakes": [
    {
      "topic": "Linear Regression",
      "question": "Which assumption is violated?",
      "count": 2,
      "last_user_answer": "A",
      "correct_answer": "C"
    }
  ],
  "question_count": 8
}
```

### Success (`200`)

```json
{
  "module_title": "Machine Learning",
  "questions": [
    {
      "id": "q-1",
      "topic": "Linear Regression",
      "question": "Which statement is correct?",
      "options": ["A", "B", "C", "D"],
      "correct": 2,
      "explanation": "..."
    }
  ],
  "questions_count": 8,
  "quiz_mode": "practice",
  "source": "gemini",
  "model": "gemini-2.5-flash",
  "note": ""
}
```

Notes:

- Frontend accepts either `correct` or `correct_index` from backend and normalizes it.
- If backend is unavailable/unauthenticated, `module.html` uses local fallback quiz generation.

## 3) PDF Notes API (Upload/List/Delete)

Notes are not stored as DB blobs.

- PDF file is stored in Django file storage (local media by default, cloud if configured).
- Metadata + extracted text excerpt are stored in DB.

### 3.1 List Notes

Endpoint:

`GET /api/quizzes/module-notes/?module_id=<moduleId>&roadmap_id=<roadmapId>`

Auth: required

Query params:

- `module_id` (required)
- `roadmap_id` (optional)

If `roadmap_id` is omitted, backend returns notes for the same `module_id` with `roadmap = null` (local-scope notes).

### Success (`200`)

```json
[
  {
    "id": 12,
    "roadmap_id": 123,
    "module_id": "7",
    "module_title": "Machine Learning",
    "file_name": "lecture1.pdf",
    "file_url": "https://.../media/module_notes/...",
    "content_type": "application/pdf",
    "file_size": 345678,
    "pages_parsed": 6,
    "char_count": 6800,
    "extracted_text_excerpt": "Supervised learning...",
    "created_at": "2026-02-22T10:00:00Z",
    "updated_at": "2026-02-22T10:00:00Z"
  }
]
```

### 3.2 Upload Note (PDF + extracted text snippet)

Endpoint:

`POST /api/quizzes/module-notes/`

Auth: required

Content type: `multipart/form-data`

### FormData fields

- `file` (required, PDF)
- `module_id` (required)
- `module_title` (optional)
- `roadmap_id` (optional)
- `pages_parsed` (optional, integer)
- `char_count` (optional, integer)
- `extracted_text_excerpt` (optional, max ~7000 chars, frontend already truncates)

### Success (`201`)

Returns the same note object shape as list endpoint.

### Frontend behavior

- `module.html` extracts text client-side (PDF.js) before upload.
- If upload fails, note is still kept locally (`storage: local`) so quizzes can still use the text excerpt.

### 3.3 Delete Note

Endpoint:

`DELETE /api/quizzes/module-notes/{note_id}/`

Auth: required

Success: `204 No Content`

Backend also deletes the underlying file from storage (best effort).

## 4) Topic Editing (Current Status: Local Only)

There is currently no backend CRUD endpoint for module topics in `module.html`.

Topic editing is stored in browser localStorage (scoped per user + roadmap + module).

### Local topic operations in `module.html`

- Add topic
- Edit topic title / notes (`why`)
- Duplicate topic
- Delete topic
- Reorder is not implemented (current order is list order)

### Local storage keys used by `module.html`

- Context from roadmap click:
  - `modulePageContext:{roadmapId|local}:{moduleId}`
- Workspace state:
  - `moduleWorkspace:v1:{userIdentity}:{roadmapId|local}:{moduleId}`

### Stored local state (high level)

```json
{
  "topics": [],
  "notes": [],
  "attempts": [],
  "mistakeBank": [],
  "topicStats": {},
  "activity": [],
  "lastGenerated": {
    "topicsSource": "",
    "quizSource": "",
    "note": ""
  }
}
```

## 5) Quiz Modes in `module.html` (UI Logic)

Current UI split (important for frontend work):

- Practice Quiz (All Topics): separate panel/state
- Focused Topic Quiz: separate panel/state inside Topics section
- Mock Exam: separate panel/state

They all call `POST /api/quizzes/module-quiz/generate/` with different `quiz_mode`.

## 6) Roadmap Progress Sync After Quiz Submit

`module.html` may receive `topicId` and `roadmap_id` in query params.

After quiz submit, frontend attempts to sync progress:

1. `PATCH /api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/`
2. If that fails and legacy method exists, fallback to:
   - `PATCH /api/roadmaps/topics/{topic_id}/progress/`

Frontend also writes a local fallback snapshot:

- localStorage key: `quiz-{moduleId}`

This is used by roadmap UI badges/progress when backend progress is missing.

## 7) Error Handling Notes (Frontend)

- `401`: refresh token and retry once (`ApiService` already handles this)
- `400`: validation issue (`module_title`, `module_id`, etc.)
- `429`: quota exceeded (Gemini)
- `503`: AI/service unavailable

Recommended UI behavior:

- show backend error message if available
- keep local fallback generators enabled
- do not block topic editing if backend generation fails

## 8) Example Frontend Calls

### Generate Practice Quiz

```js
const resp = await ApiService.generateModuleQuiz({
  module_title: "Machine Learning",
  roadmap_title: "Roadmap 123",
  quiz_mode: "practice",
  topics: ["Linear Regression", "Logistic Regression"],
  note_excerpts: [],
  mistakes: [],
  question_count: 8
});
```

### Generate Focused Topic Quiz

```js
const resp = await ApiService.generateModuleQuiz({
  module_title: "Machine Learning",
  roadmap_title: "Roadmap 123",
  quiz_mode: "topic",
  topics: ["Linear Regression"],
  note_excerpts: [],
  mistakes: [],
  question_count: 5
});
```

### Upload PDF Note

```js
const formData = new FormData();
formData.append("file", file);
formData.append("module_id", "7");
formData.append("module_title", "Machine Learning");
formData.append("roadmap_id", "123");
formData.append("pages_parsed", "6");
formData.append("char_count", "6800");
formData.append("extracted_text_excerpt", excerpt.slice(0, 7000));

const resp = await ApiService.uploadModuleNote(formData);
```

## 9) What Is Not Implemented Yet (Backend)

These are frontend-local today (not API-backed yet):

- save edited topics to DB
- save custom topic order to DB
- save module workspace state (attempts/mistakeBank/topicStats) to DB

If needed, we can add dedicated backend endpoints for module workspace persistence next.
