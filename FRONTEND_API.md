# StudentRoadmap Frontend API

This document describes the API contract for the current deployed backend.

## Base URL

`https://studentroadmap-api-m5hqauiyxa-nw.a.run.app`

## Auth

- API auth uses JWT bearer tokens.
- Include access token in protected requests:
  - `Authorization: Bearer <access_token>`
- Content type for POST/PATCH:
  - `Content-Type: application/json`

## Endpoints

### 1) Register

`POST /api/auth/register/`

Auth: public

Request:

```json
{
  "username": "testuser1",
  "email": "testuser1@example.com",
  "password": "strongpass123"
}
```

Success (`201`):

```json
{
  "id": 1,
  "username": "testuser1",
  "email": "testuser1@example.com"
}
```

### 2) Get JWT token pair

`POST /api/auth/token/`

Auth: public

Request:

```json
{
  "username": "testuser1",
  "password": "strongpass123"
}
```

Success (`200`):

```json
{
  "refresh": "<refresh_token>",
  "access": "<access_token>"
}
```

### 3) Refresh access token

`POST /api/auth/token/refresh/`

Auth: public

Request:

```json
{
  "refresh": "<refresh_token>"
}
```

Success (`200`):

```json
{
  "access": "<new_access_token>"
}
```

### 4) Universities search

`GET /api/catalog/universities/?q=<query>`

Auth: public

Example:

`GET /api/catalog/universities/?q=king`

Success (`200`):

```json
[
  {
    "id": 40,
    "name": "King's College London",
    "discover_uni_id": "10003645",
    "country": "UK"
  }
]
```

### 5) Courses search

`GET /api/catalog/courses/?university_id=<id>&q=<query>`

Auth: public

Example:

`GET /api/catalog/courses/?university_id=40&q=artificial`

Success (`200`):

```json
[
  {
    "id": 3469,
    "title": "Artificial Intelligence",
    "university": 40,
    "university_name": "King's College London",
    "discover_uni_course_id": "....",
    "subject_area": "...",
    "duration_years": 3,
    "study_mode": "FT",
    "course_url": "https://..."
  }
]
```

### 6) Generate module draft for selected course

`POST /api/catalog/courses/{course_id}/modules/draft/`

Auth: required

Request body (all optional):

```json
{
  "refresh": true,
  "insecure": false,
  "timeout": 15,
  "context_text": "",
  "use_ai": true
}
```

Success (`200`) shape:

```json
{
  "course_id": 3469,
  "course_title": "Artificial Intelligence",
  "university": "King's College London",
  "scraped_now": true,
  "draft_modules_count": 8,
  "draft_modules": ["..."],
  "modules_count": 8,
  "modules": ["..."],
  "raw_modules_count": 20,
  "raw_modules": ["..."],
  "draft_source": "gemini",
  "draft_model": "gemini-2.5-flash",
  "years": [
    {
      "year": "Year 1",
      "required": ["..."],
      "optional": []
    }
  ],
  "draft_years": [
    {
      "year": "Year 1",
      "required": ["..."],
      "optional": []
    }
  ],
  "confidence_percent": 84.5,
  "needs_user_confirmation": false,
  "draft_notes": ""
}
```

Error notes:

- `429`: Gemini quota exceeded
- `503`: Gemini unavailable/not configured

### 7) Confirm final modules (user-edited)

`POST /api/catalog/courses/{course_id}/modules/confirm/`

Auth: required

Request:

```json
{
  "modules": [
    "Logic and Knowledge Representation",
    "Machine Learning"
  ]
}
```

Success (`200`):

```json
{
  "course_id": 3469,
  "course_title": "Artificial Intelligence",
  "university": "King's College London",
  "confirmed": true,
  "modules_count": 2,
  "modules": [
    "Logic and Knowledge Representation",
    "Machine Learning"
  ],
  "modules_last_scraped_at": "2026-02-22T00:00:00Z"
}
```

### 8) Combined modules endpoint (legacy/alternate)

`POST /api/catalog/courses/{course_id}/modules/`

Also accepts no trailing slash:

`POST /api/catalog/courses/{course_id}/modules`

Auth: required

Behavior: scrape + draft response in one call. For new frontend flow, prefer `/modules/draft/` then `/modules/confirm/`.

### 9) Generate roadmap

`POST /api/roadmaps/generate/`

Auth: required

UK/discover-uni based request:

```json
{
  "title": "My AI Roadmap",
  "course_id": 3469,
  "career_goal": "ML Engineer"
}
```

Manual/non-UK request:

```json
{
  "manual_course_title": "Computer Science",
  "module_names": [
    "Programming Foundations",
    "Data Structures",
    "Databases"
  ],
  "career_goal": "Backend Engineer"
}
```

Success (`201`): returns full roadmap object (see response schema below).

### 10) List my roadmaps

`GET /api/roadmaps/`

Auth: required

Success (`200`): array of roadmap objects.

### 11) Roadmap details

`GET /api/roadmaps/{roadmap_id}/`

Auth: required

Success (`200`): single roadmap object.

### 12) Get graph payload for one roadmap

`GET /api/roadmaps/{roadmap_id}/graph/`

Auth: required

Success (`200`):

```json
{
  "roadmap_id": 123,
  "roadmap_title": "Computer Science Roadmap",
  "overall_progress_percent": 34.2,
  "nodes": [
    {
      "id": 1,
      "type": "module",
      "title": "Programming Foundations",
      "description": "",
      "order": 0,
      "parent_module_id": null,
      "progress_percent": 50.0,
      "topics_count": 3
    },
    {
      "id": 2,
      "type": "topic",
      "title": "Control Flow",
      "description": "",
      "order": 0,
      "parent_module_id": 1,
      "mastery_percent": 70.0,
      "impact_weight_percent": 70.0
    }
  ],
  "edges": [
    {
      "id": 55,
      "source": 1,
      "target": 2,
      "edge_type": "contains",
      "influence_percent": 100.0,
      "rationale": "Module contains this topic."
    }
  ]
}
```

### 13) Get graph summary

`GET /api/roadmaps/{roadmap_id}/graph/summary/`

Auth: required

Success (`200`):

```json
{
  "roadmap_id": 123,
  "modules_count": 7,
  "topics_count": 21,
  "edges_count": 30,
  "overall_progress_percent": 34.2
}
```

### 14) Update topic progress (graph endpoint)

`PATCH /api/roadmaps/{roadmap_id}/graph/topics/{topic_id}/progress/`

Auth: required

Request:

```json
{
  "mastery_percent": 72.5
}
```

Success (`200`): returns updated graph payload (`/graph/` response shape).

### 15) Update topic progress (legacy endpoint)

`PATCH /api/roadmaps/topics/{topic_id}/progress/`

Auth: required

Request:

```json
{
  "mastery_percent": 72.5
}
```

Success (`200`): returns full roadmap detail payload.

## Roadmap Response Schema

```ts
type Roadmap = {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  generation_source: "gemini" | "fallback" | "manual";
  generation_notes: string;
  manual_course_title: string;
  course: null | {
    id: number;
    title: string;
    university: string;
  };
  overall_progress_percent: number;
  modules: Array<{
    id: number;
    title: string;
    description: string;
    order: number;
    progress_percent: number;
    topics: Array<{
      id: number;
      title: string;
      description: string;
      order: number;
      mastery_percent: number;
      impact_weight_percent: number;
    }>;
  }>;
  edges: Array<{
    id: number;
    source: number;
    target: number;
    edge_type: "contains" | "prerequisite" | "career";
    influence_percent: number;
    rationale: string;
  }>;
};
```

## Recommended Frontend Flow

### UK user flow

1. Register/login
2. Search university
3. Search course in selected university
4. Request modules draft
5. Let user edit/confirm modules
6. Generate roadmap
7. Render modules/topics graph
8. Save mastery updates via topic progress endpoint

### Manual flow (non-UK or missing course)

1. Login
2. User enters manual course title + module list
3. Generate roadmap with `manual_course_title` and `module_names`
4. Track topic progress the same way

## Frontend Notes

- If protected endpoint returns `401`, refresh token then retry once.
- `needs_user_confirmation=true` means UI should show editable review before proceeding.
- `draft_source` may be `gemini`, `gemini_inferred`, or `heuristic`.
- `POST /api/catalog/discover-uni/sync/` exists but is admin-only and not required for normal frontend flow.
- For graph UI, prefer `/api/roadmaps/{roadmap_id}/graph/` + `/graph/topics/{topic_id}/progress/`.
