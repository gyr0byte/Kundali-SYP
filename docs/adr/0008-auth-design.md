# ADR 0008: Authentication, Authorization, and Session Management Architecture

## Status
Accepted

## Context
The Kundali platform requires secure, robust authentication and role-based access control (RBAC) across three primary user tiers: standard users, credentialed Vedic astrologers, and administrators. The authentication layer must guard against brute-force attacks, token replay, timing side-channels, credential theft, and privilege escalation, while keeping the calculation engine completely decoupled and independent.

## Decision
1. **Password Hashing**: Adopt Argon2id (`time_cost=3`, `memory_cost=65536` KiB, `parallelism=4`) as the primary password derivation algorithm. Maintain constant-time verification behavior on missing accounts using dummy hash evaluation to mitigate timing enumeration attacks.
2. **Stateless Access Tokens**: Issue short-lived (15 minutes) HMAC-SHA256 (HS256) JWT access tokens encoding the user ID (`sub`) and role (`role`). Require `JWT_SECRET` of at least 32 characters on startup.
3. **Rotating Refresh Tokens with Family Revocation**: Use high-entropy 32-byte URL-safe refresh tokens with a 7-day lifetime. Only SHA-256 hashes are stored in the database. Tokens rotate on every refresh call. A `family_id` tracks rotation chains; presenting an already-rotated token immediately revokes all tokens within that family to thwart token reuse.
4. **Declarative Role and Permission Enforcers**: Enforce RBAC at the route handler level via FastAPI dependencies (`require_role`, `require_permission`). Map 12 discrete permissions across user, astrologer, and admin tiers. Astrologers inherit user capabilities and require admin approval before accessing review queue endpoints.
5. **Session Invalidation**: Store session state through refresh token records. Account deactivation, password changes, and password resets invalidate all active refresh tokens immediately.
6. **Data-Visibility Partitioning**: Enforce strict data boundaries: Astrologers access only derived chart facts and AI summaries (never raw birth data, coordinates, or user identity); administrators access account metadata only (never decrypted birth details).
7. **Environment-Sensitive Mailer**: Define a `Mailer` protocol with a `ConsoleMailer` implementation that prints password reset URLs only in the `dev` environment, dropping output in `prod` and `test` environments until a transactional provider is integrated.

## Consequences
* High cryptographic resilience against offline cracking and token replay attacks.
* Access tokens are stateless and expire naturally within 15 minutes; immediate revocation requires waiting for access token expiration or enforcing short expiration windows.
* In-memory rate limiting and console email output are suitable for single-node / development setups, but will require Redis and a transactional email provider for multi-instance production deployment.
