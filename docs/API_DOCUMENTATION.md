# Tizahab API Documentation

Base API URL in local development: `http://localhost:8000/api`

The current implementation uses JWT authentication for protected endpoints.

## Authentication Model

Authorization header for protected endpoints:

```http
Authorization: Bearer <access_token>
```

Token lifetimes from `config/settings.py`:

- Access token: 15 minutes
- Refresh token: 7 days

Frontend request behavior from `static/js/api.js`:

- Requests use a shared helper
- On `401`, the helper calls `POST /api/auth/token/refresh/`
- If refresh succeeds, the original request is retried
- If refresh fails, the helper attempts to obtain tokens from the Django session, then redirects to `/login/` if authentication cannot be restored

## Validation Rules

Unified validation behavior in the current backend:

- Invalid category input returns HTTP `400`
- Invalid date input returns HTTP `400`
- Invalid `trip_duration` input returns HTTP `400`
- There is no silent fallback for invalid values

All invalid inputs return HTTP `400` with descriptive messages unless the request fails for a different reason such as missing authentication or no matching recommendations.

## Valid Categories

Canonical categories: `culture`, `heritage`, `entertainment`, `food`, `shopping`,
`nature`, `family`, `events`. Legacy inputs such as `restaurant` and `cafe` normalize
to `food`; API responses use canonical values.

Plans support 1–30 days and validate availability on each assigned day. Price
limits apply per place; unknown prices remain eligible and are explicitly labeled.
Explicit rating and known-price limits are never relaxed to fill a plan. Supporting
meal/attraction suggestions can supplement the selected interests.

## Endpoints

### Independent named trips

The public `/trips/` planner uses these endpoints. The older daily-plan endpoints
documented below remain available for the classic planner.

| Method and path | Access | Behavior |
|---|---|---|
| `POST /api/trips/preview/` | Guest or user | Validate, generate or preview date changes; never saves a trip |
| `GET /api/trips/` | Owner | List active trips; `?archived=1` lists archived trips |
| `POST /api/trips/` | Signed in | Save a new independent trip |
| `GET /api/trips/<id>/` | Owner | Read a trip with days, activities and unscheduled selections |
| `PUT /api/trips/<id>/` | Owner | Save a complete trip document with its current `revision` |
| `DELETE /api/trips/<id>/` | Owner | Archive, with `confirmed: true` and current `revision`; preserves activities |
| `PATCH /api/trips/<id>/` | Owner | Restore, with `action: "restore"`, `confirmed: true` and current `revision` |

A trip document contains `name`, `start_date`, `duration`, `preferences`, ordered
`days` with activity `event_id` / `locked` values, and `unscheduled`. Preview requests
wrap it as `trip` with `action: "generate"`, `"dates"` or `"validate"`. Generation
can specify a zero-based `day_index`. Date previews also take `start_date` and
`duration`. Conflict previews require explicit confirmation before affected
selections move to Unscheduled Places; the client subsequently saves the document.

Stale writes return `409`; unavailable objects and other users' private trips return
`404`, including for administrators. Archived trips must be restored before editing.
Guest drafts live in browser storage, not this API. Failed saved-trip edits have
same-tab session recovery; logging out clears that recovery copy.

### `POST /api/auth/signup/`

Creates a user and returns JWT tokens.

Request body:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "password2": "StrongPass123!"
}
```

Validation rules:

- `email` is required and must be unique
- `password` and `password2` are required
- `password` and `password2` must match
- Django password validators are applied

Success response: `201 Created`

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

Example `400 Bad Request`:

```json
{
  "non_field_errors": [
    "Passwords do not match."
  ]
}
```

### `POST /api/auth/login/`

Authenticates by email and password and returns JWT tokens.

Request body:

```json
{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

Validation rules:

- `email` is required
- `password` is required
- Credentials must match an existing user

Success response: `200 OK`

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

Example `400 Bad Request`:

```json
{
  "non_field_errors": [
    "Invalid email or password."
  ]
}
```

### `GET /api/auth/preferences/`

Returns the authenticated user's preferences. If no row exists yet, the backend creates one and returns defaults.

Request format:

- No request body
- Requires JWT authentication

Success response: `200 OK`

```json
{
  "preferred_language": "en",
  "budget_min": null,
  "budget_max": null,
  "interests": [],
  "min_rating": null,
  "trip_duration": 1
}
```

Validation rules:

- Authentication is required
- This endpoint does not take query parameters or a request body

Example `400 Bad Request`:

This endpoint does not currently define request-body validation for `GET`. Validation errors are produced on `POST` and `PUT` instead.

### `POST /api/auth/preferences/`

Partially updates or creates preferences for the authenticated user. `PUT` is routed to the same behavior.

Request body:

```json
{
  "preferred_language": "ar",
  "budget_min": 50,
  "budget_max": 300,
  "interests": ["food", "culture"],
  "min_rating": 4.0,
  "trip_duration": 3
}
```

Validation rules:

- `interests` must be an array
- Every interest must be one of the valid backend categories
- `budget_min` and `budget_max` must be non-negative when provided
- `budget_min` cannot be greater than `budget_max`
- `trip_duration` must be between `1` and `30`

Success response: `200 OK` or `201 Created`

```json
{
  "preferred_language": "ar",
  "budget_min": 50,
  "budget_max": 300,
  "interests": ["food", "culture"],
  "min_rating": "4.0",
  "trip_duration": 3
}
```

Example `400 Bad Request` for invalid category:

```json
{
  "interests": [
    "Invalid interests: ['invalid']. Valid options: ['culture', 'heritage', 'entertainment', 'food', 'shopping', 'nature', 'family', 'events']"
  ]
}
```

Example `400 Bad Request` for invalid trip duration:

```json
{
  "trip_duration": [
    "trip_duration must be between 1 and 30."
  ]
}
```

### `GET /api/events/`

Returns a paginated list of events. This endpoint is public.

Query parameters:

- `category` optional
- `date` optional, format `YYYY-MM-DD`
- `search` optional

Example request:

```http
GET /api/events/?category=food&date=2026-06-15&search=riyadh
```

Validation rules:

- `category` must be one of the valid categories
- `date` must use `YYYY-MM-DD`

Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Example Place",
      "category": "food",
      "description": "A sample place",
      "date": "2026-06-15T10:00:00Z",
      "start_date": null,
      "end_date": null,
      "location": "Riyadh",
      "price": "50.00",
      "price_range": "",
      "latitude": 24.7136,
      "longitude": 46.6753,
      "rating": "4.3"
    }
  ]
}
```

Example `400 Bad Request` for invalid category:

```json
{
  "detail": "Invalid category. Valid options: ['culture', 'heritage', 'entertainment', 'food', 'shopping', 'nature', 'family', 'events']"
}
```

Example `400 Bad Request` for invalid date:

```json
{
  "detail": "Invalid date format. Use YYYY-MM-DD."
}
```

### `GET /api/events/filtered/`

Returns a paginated list of events filtered by the authenticated user's saved preferences.

Current behavior:

- Filters by saved interest categories when present
- Applies saved `budget_min` and `budget_max`
- Includes events with `price = null` during budget filtering
- Optionally filters by date range

Query parameters:

- `date_from` optional, format `YYYY-MM-DD`
- `date_to` optional, format `YYYY-MM-DD`

Example request:

```http
GET /api/events/filtered/?date_from=2026-06-15&date_to=2026-06-20
```

Validation rules:

- Requires JWT authentication
- `date_from` and `date_to` must use `YYYY-MM-DD`
- `date_from` cannot be later than `date_to`

Success response: `200 OK`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Example Place",
      "category": "food",
      "description": "A sample place",
      "date": "2026-06-15T10:00:00Z",
      "start_date": null,
      "end_date": null,
      "location": "Riyadh",
      "price": "50.00",
      "price_range": "",
      "latitude": 24.7136,
      "longitude": 46.6753,
      "rating": "4.3"
    }
  ]
}
```

Example `400 Bad Request` for invalid date:

```json
{
  "detail": "Invalid date_from format. Use YYYY-MM-DD."
}
```

Example `400 Bad Request` for invalid date range:

```json
{
  "detail": "date_from cannot be later than date_to."
}
```

### `GET /api/daily-plan/`

Returns the authenticated user's daily plans ordered by date descending.

Request format:

- No request body
- Requires JWT authentication

Success response: `200 OK`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 10,
      "date": "2026-06-15",
      "events": [
        {
          "id": 1,
          "title": "Example Place",
          "category": "food",
          "description": "A sample place",
          "date": "2026-06-15T10:00:00Z",
          "start_date": null,
          "end_date": null,
          "location": "Riyadh",
          "price": "50.00",
          "price_range": "",
          "latitude": 24.7136,
          "longitude": 46.6753,
          "rating": "4.3"
        }
      ],
      "created_at": "2026-06-14T12:00:00Z"
    }
  ]
}
```

Validation rules:

- Authentication is required
- This endpoint does not currently define `GET` input validation

Example `400 Bad Request`:

This endpoint does not currently define request-body validation for `GET`. Validation errors are produced on `POST /api/daily-plan/`.

### `POST /api/daily-plan/`

Creates a daily plan manually.

Request body:

```json
{
  "date": "2026-06-15",
  "events": [1, 2, 3]
}
```

Current serializer behavior:

- Write operations accept event IDs
- Read responses return full event objects

Validation rules:

- `date` is required and must be a valid date
- Each event ID must reference an existing event
- A user can only have one plan per date

Success response: `201 Created`

```json
{
  "id": 10,
  "date": "2026-06-15",
  "events": [
    {
      "id": 1,
      "title": "Example Place",
      "category": "food",
      "description": "A sample place",
      "date": "2026-06-15T10:00:00Z",
      "start_date": null,
      "end_date": null,
      "location": "Riyadh",
      "price": "50.00",
      "price_range": "",
      "latitude": 24.7136,
      "longitude": 46.6753,
      "rating": "4.3"
    }
  ],
  "created_at": "2026-06-14T12:00:00Z"
}
```

Example `400 Bad Request` for invalid date:

```json
{
  "date": [
    "Date has wrong format. Use one of these formats instead: YYYY-MM-DD."
  ]
}
```

### `POST /api/daily-plan/generate/`

Generates or regenerates one day's plan from the user's saved preferences.

Request body:

```json
{
  "date": "2026-06-15"
}
```

Optional request fields supported by the current code:

- `seed`
- `exclude_plan_dates`

Current recommendation behavior:

- Uses saved preference categories
- Applies budget filters while keeping events with `price = null`
- Penalizes events used in the previous 7 days
- Selects one event per interest category first
- Fills remaining slots from remaining candidates
- Returns up to 5 events

Validation rules:

- Requires JWT authentication
- `date` is required
- `date` must use `YYYY-MM-DD`
- Past dates are rejected
- `exclude_plan_dates`, when present, must be a list of `YYYY-MM-DD` values
- Missing saved interests returns `400`
- No matching recommendations returns `404`

Success response: `201 Created` on first create, `200 OK` on update

```json
{
  "id": 10,
  "date": "2026-06-15",
  "events": [
    {
      "id": 1,
      "title": "Example Place",
      "category": "food",
      "description": "A sample place",
      "date": "2026-06-15T10:00:00Z",
      "start_date": null,
      "end_date": null,
      "location": "Riyadh",
      "price": "50.00",
      "price_range": "",
      "latitude": 24.7136,
      "longitude": 46.6753,
      "rating": "4.3"
    }
  ],
  "count": 1
}
```

Example `400 Bad Request` for invalid date:

```json
{
  "detail": "Invalid date format. Expected YYYY-MM-DD"
}
```

Example `400 Bad Request` for missing date:

```json
{
  "detail": "Date is required. Format: YYYY-MM-DD"
}
```

### `POST /api/daily-plan/generate-multiday/`

Generates and saves multiple daily plans in one request.

Request body:

```json
{
  "start_date": "2026-06-15",
  "trip_duration": 3
}
```

Current behavior:

- Uses the request `trip_duration` when provided
- Otherwise uses the saved preference `trip_duration`
- Generates consecutive daily plans starting from `start_date`
- Excludes events already selected earlier in the same generated trip
- Replaces existing plans only within the requested generated date range

Validation rules:

- Requires JWT authentication
- `start_date` is required
- `start_date` must use `YYYY-MM-DD`
- Past dates are rejected
- `trip_duration` must be an integer between `1` and `30`
- Missing saved interests returns `400`
- No matching recommendations across the generated trip returns `404`

Success response: `201 Created` on first create, `200 OK` when replacing existing plans in the requested range

```json
{
  "trip_duration": 3,
  "start_date": "2026-06-15",
  "plans": [
    {
      "id": 21,
      "date": "2026-06-15",
      "events": [
        {
          "id": 1,
          "title": "Example Place",
          "category": "food",
          "description": "A sample place",
          "date": "2026-06-15T10:00:00Z",
          "start_date": null,
          "end_date": null,
          "location": "Riyadh",
          "price": "50.00",
          "price_range": "",
          "latitude": 24.7136,
          "longitude": 46.6753,
          "rating": "4.3"
        }
      ],
      "count": 1
    }
  ],
  "total_events": 3
}
```

Example `400 Bad Request` for invalid date:

```json
{
  "detail": "Invalid start_date format. Expected YYYY-MM-DD"
}
```

Example `400 Bad Request` for invalid trip duration:

```json
{
  "detail": "trip_duration must be an integer between 1 and 30."
}
```

## Related Auth Endpoint

### `POST /api/auth/token/refresh/`

Exchanges a refresh token for a new access token.

Request body:

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

Success response: `200 OK`

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```
