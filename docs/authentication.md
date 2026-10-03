# Authentication and tenant authorization

## Design

Module 2 uses email/password authentication and opaque, revocable server-side sessions. Passwords are normalized only as input values and hashed with Argon2id; they are never logged or returned. Email lookup uses a case-folded `normalized_email` column with a PostgreSQL unique constraint.

A session token contains 256 bits of cryptographically secure randomness. The raw token exists only in the browser's Secure-configurable, HttpOnly cookie. The database stores a SHA-256 token digest, which is safe for lookup because the source token has high entropy. No session token is placed in JSON, localStorage, or sessionStorage.

## Session lifecycle

Registration atomically commits the user, organization, owner membership, and initial session. Login verifies Argon2id credentials using one generic failure response and creates a new session. Requests hash the presented cookie and require a matching, unexpired session attached to an active user. `last_used_at` is refreshed only after a configurable interval to avoid a write on every request. Logout deletes the matching session and expires the cookie; repeating logout is safe.

Cookie-authenticated state changes validate `Origin`, falling back to the origin portion of `Referer`, against configured frontend origins. Cookies default to `SameSite=Lax`; production configuration rejects `Secure=false`.

## Organization membership model

Users and organizations are joined by one unique membership per pair. Roles are a PostgreSQL enum: `owner`, `admin`, and `member`. Deleting a user or organization cascades its memberships; deleting a user also removes their sessions. Organization slugs are unique and collision-safe. Renaming an organization deliberately keeps its slug stable.

## Tenant authorization rules

Reusable dependencies resolve the authenticated user, organization member, admin, and owner. An organization ID from a route is never trusted on its own. Membership is checked in the query for every tenant-scoped route. A caller without membership receives `404` so the API does not reveal whether another tenant exists. Members may read their organization and member list; only owners and admins may rename it.

These dependencies are intended for reuse by future customer and usage-event routes. There is no global mutable "current organization" state.

## Security trade-offs and deferred hardening

The in-memory login limiter offers a small single-process development guard but is not reliable across replicas or restarts. A production deployment needs shared edge or distributed rate limiting; Redis is deliberately not introduced in Module 2. Operational session cleanup can later delete expired rows in batches.

OAuth, MFA, email verification, password reset, invitations, device/session management, security notification email, advanced breached-password screening, and audit logging are deferred. HTTPS termination, trusted proxy configuration, secure cookie domains, secret rotation, database encryption/backups, and deployment-specific CSRF review remain production responsibilities.
