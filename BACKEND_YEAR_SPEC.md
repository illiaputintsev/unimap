# Backend Specification: Module Year Property

## Issue
Modules displayed in the roadmap appear in the wrong year row because the API response doesn't include `year` data for each module.

## Required Change

### Affected Endpoints

1. **GET `/api/roadmaps/{roadmap_id}/`**
2. **GET `/api/roadmaps/{roadmap_id}/graph/`**
3. **POST `/api/catalog/courses/{course_id}/modules/graph/`**

### Module Object Schema

Each module in the response should include a `year` property (integer, 1-3):

```json
{
  "id": "module-123",
  "title": "Machine Learning",
  "description": "Introduction to ML concepts...",
  "order": 6,
  "year": 3,           // ← REQUIRED: Academic year (1, 2, or 3)
  "level": 3,          // Alternative: level also works
  "topics": [...]
}
```

### Frontend Fallback Behavior

The frontend checks for year information in this order:
1. `module.year` (preferred)
2. `module.level` (alternative)
3. **Fallback**: Infers year from array index position (causes incorrect placement)

### Example: Full Roadmap Response

```json
{
  "id": 42,
  "title": "Computer Science BSc",
  "course": {
    "title": "Computer Science",
    "university": "UCL"
  },
  "modules": [
    { "id": "1", "title": "Maths and Statistics", "year": 1, "order": 0, "topics": [...] },
    { "id": "2", "title": "Programming Practice", "year": 1, "order": 1, "topics": [...] },
    { "id": "3", "title": "Logic and Knowledge", "year": 1, "order": 2, "topics": [...] },
    { "id": "4", "title": "Introduction to AI", "year": 2, "order": 3, "topics": [...] },
    { "id": "5", "title": "Web and Internet Systems", "year": 2, "order": 4, "topics": [...] },
    { "id": "6", "title": "Foundations of Comp Theory", "year": 2, "order": 5, "topics": [...] },
    { "id": "7", "title": "Machine Learning", "year": 3, "order": 6, "topics": [...] },
    { "id": "8", "title": "Data Science", "year": 3, "order": 7, "topics": [...] },
    { "id": "9", "title": "Final Year Project", "year": 3, "order": 8, "topics": [...] }
  ],
  "edges": [
    { "source": "1", "target": "4" },
    { "source": "2", "target": "5" },
    { "source": "4", "target": "7" },
    { "source": "5", "target": "8" },
    { "source": "7", "target": "8" },
    { "source": "7", "target": "9" },
    { "source": "8", "target": "9" }
  ]
}
```

### Graph Endpoint Response

For `GET /api/roadmaps/{roadmap_id}/graph/`:

```json
{
  "roadmap_id": 42,
  "roadmap_title": "Computer Science BSc",
  "nodes": [
    { "id": "1", "title": "Maths and Statistics", "year": 1 },
    { "id": "7", "title": "Machine Learning", "year": 3 },
    ...
  ],
  "edges": [
    { "source": "1", "target": "4" },
    ...
  ]
}
```

## Implementation Notes

### Database Schema
Add a `year` column to the modules table:

```sql
ALTER TABLE modules ADD COLUMN year INTEGER DEFAULT 1 CHECK (year BETWEEN 1 AND 3);
```

### Data Sources
The `year` value can be determined from:
- UCAS course specification data
- University module catalog (typically includes level/year)
- Module code patterns (e.g., COMP1xxx = Year 1, COMP2xxx = Year 2)
- Manual curation per course

### Validation
- `year` must be an integer between 1 and 3
- All modules in a roadmap should have a `year` value
- `order` should be consistent with `year` (Year 1 modules should have lower order values)

## Testing

After implementing, verify:
1. Modules appear in correct year rows on the roadmap visualization
2. Year labels (Year 1, Year 2, Year 3) align with their respective module groups
3. Cross-year edges render correctly (e.g., Year 1 → Year 2 dependencies)
