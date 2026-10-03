# Projects and usage-event ingestion

## Tenant and project model

Projects belong to one organization and have a development, staging, or production environment. Project slugs are unique within an organization and stay fixed when the project name changes. Owners and admins create/update projects and manage keys; members may list/read projects and events. Every dashboard project query joins the current user to a membership in the project's organization. Inaccessible projects and events return `404`.

Usage events store both organization and project IDs. A composite foreign key ensures that the event's organization matches its project even if an internal writer makes a mistake. The ingestion request does not accept either ID; both come from the authenticated API key.

## Key lifecycle and rotation

A project key has the form `aipm_<environment>_<16-hex-character-prefix>_<random-secret>`. The secret contains 256 bits of randomness. The public prefix enables one indexed candidate lookup. The server compares the SHA-256 hash of the complete presented key to the stored hash using constant-time comparison. A fast cryptographic hash is appropriate here because the generated secret has high entropy; Argon2id is reserved for low-entropy human passwords.

The raw key is returned in the creation response only. The browser keeps it temporarily in component memory until the one-time panel is dismissed; it is never put in URLs or browser storage. Listing returns only safe metadata. Revoked or expired keys return the same generic `invalid_api_key` response as unknown keys. A disabled project returns `project_inactive`. Successful authentication refreshes `last_used_at` only after a configurable interval. Keys may be created before use, rotated by overlap, and then revoked. Revocation is idempotent and cannot be reversed.

Dashboard session cookies never authenticate ingestion. Project keys never authenticate dashboard routes. Authorization headers and ingestion bodies are not logged by application code.

## Normalized event schema

The stable ingestion schema is version `1`. Required fields are `client_event_id`, `provider`, `model`, `feature`, `status`, `input_tokens`, `output_tokens`, and a timezone-aware `occurred_at`. Optional fields are `customer_external_id`, `operation`, `cached_input_tokens`, `reasoning_tokens`, `provider_reported_total_tokens`, `duration_ms`, `provider_request_id`, `error_code`, and `tags`.

`provider` is a bounded lowercase identifier. Examples are `openai`, `anthropic`, `google`, `azure_openai`, `aws_bedrock`, and `other`; future providers can use the same shape. Token fields are independent. Cached input tokens may be a subset of input tokens, and reasoning tokens may be included in provider output; the server does not sum them. A provider-reported total is preserved separately. No monetary cost field exists in this module.

Token fields are bounded non-negative integers. Tags are at most 20 flat string pairs with keys up to 64 characters and values up to 256 characters. Content-related tag names are rejected. Client timestamps are converted to UTC and must be no more than five minutes in the future or 365 days in the past by default; `received_at` and `created_at` are server-generated. The request schema forbids unrecognized fields, including `prompt`, `messages`, `input_text`, `output_text`, `completion`, `response_body`, `content`, documents, embeddings, and tenant IDs. `customer_external_id` should preferably be an internal opaque identifier rather than an email address.

## Idempotency and batches

Within a project, `client_event_id` is unique in PostgreSQL. The server fingerprints the canonical normalized payload with SHA-256, including normalized UTC time and sorted tags. An `INSERT ... ON CONFLICT DO NOTHING` handles concurrent retries under the database constraint, followed by one batched lookup and fingerprint comparison. First submission returns `201` for a single event; an identical retry returns `200` with the existing ID. A changed payload returns `409 duplicate_event_conflict`.

Batches default to a maximum of 100 events and 1 MiB per request. The body limit is enforced before JSON parsing. All items are validated before insertion. One bulk insert and one lookup handle the batch; any conflicting fingerprint rolls back every new row in that batch. Identical IDs inside a batch are collapsed for insertion and reported in input order as one created item followed by existing items. Per-event results contain only IDs, client event IDs, and creation status.

## Query behavior and operations

Project event listing defaults to the most recent 30 days, ordered by `(occurred_at DESC, id DESC)`. The opaque cursor encodes that pair to keep pagination deterministic when timestamps tie. Pages default to 25 with a configurable maximum of 100. Filters are exact matches for provider, model, feature, customer external ID, and status, plus a bounded date range. Project and organization time indexes support future data access patterns; there is no aggregation here.

Production deployments need distributed rate limiting at the application gateway or a future shared layer. The current body, batch, field, timestamp, and query limits protect local operation but do not replace network-level controls. Provider API calls, adapters, SDKs, cost calculation, pricing, revenue, charts, alerts, queues, and Redis are deferred.
