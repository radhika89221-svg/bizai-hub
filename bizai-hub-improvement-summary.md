# BizAI-Hub Improvement Plan

## 1) Core infrastructure (need immediately)

1. Add user accounts + login
   - flask-login + flask-sqlalchemy
   - User model + persisted request history
2. Add API key/auth guard (protect endpoints)
3. Add rate limiting
   - flask-limiter (e.g., 20/day free)
4. Add usage quota tracking
   - free vs paid
   - daily reset

## 2) Backend quality & reliability

1. Switch from model roulette → stable model
   - e.g., anthropic/claude-3.5-haiku or preferred
2. Normalize API response structure
   - always { success, result, error? }
3. Add input validation on all endpoints
   - required fields, max length, safe text, sanitize
4. Add robust error handling
   - 400/429/500 clearly
5. Add structured logging
   - includes user ID, action, latency, errors

## 3) Feature upgrades (current endpoints)

### a) Content writer
- content_type pre-check
- detect blank or prompt injection
- history save and version / repeat

### b) Chatbot
- sanitize message, enforce max length
- contextual memory by user session
- fallback on provider failure

### c) Sentiment
- replace TextBlob with transformer or provider sentiment appropriately
- include confidence
- add top_keywords/emotion

### d) Image generation
- fallback service (reduce Pollinations dependence)
- caching + hash key
- progress UI / async (upload + poll)
- file storage for repeated
- size + format options
- throttle frequency

### e) Sales predictor
- statsmodels ARIMA/Holt-Winters
- low-data fallback linear
- predictive interval
- trend + recommendations
- CSV upload & graph
- store history per user

### f) Audio tools
- implement endpoint
- text-to-speech / speech-to-text
- upload audio process + response

## 4) UX & product polish

- user dashboard (history, quotas, credits)
- onboarding + FAQ
- responsive UI + error states
- generate-again button
- export (docx/pdf/clipboard)

## 5) Production hardening

- requirements cleanup
- env config (OPENROUTER_KEY, SECRET_KEY)
- remove print production
- logging library
- CORS domain
- HTTPS
- E2E tests
- CI lint/test

## 6) Monetization setup

- Stripe checkout/subscription
- account free/premium
- feature gating
- email/usage analytics
- referral

## Quick wins (1-2 days)

1. Add auth + DB + history
2. Add rate limiter + API guard
3. Add quota model
4. requirements/test cleanup
5. one model + no roulette
6. README/API docs

## Backups

- app_original.py baseline

## Next step

Phase 3 patch with auth+DB+quota.