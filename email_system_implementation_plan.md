# Email Notification System Implementation Plan

## Goal
Add configurable email notifications in the simulator with receiver management from the Config page and a manual "Send test email" action.

## Scope
- Config page controls for notification settings and receivers.
- Backend email sender using SMTP (Mailgun-compatible).
- Test-email endpoint and trigger button.
- Alert-triggered email sends for selected operational events.

## Configuration Model
Store in system settings (non-secret):
- `email_enabled` (bool)
- `email_from_email` (string)
- `email_from_name` (string, optional)
- `email_subject_prefix` (string, optional)
- `email_recipients` (string array)
- `email_event_triggers` (string array; e.g. `run_failed`, `schedule_launch_failed`, `critical_alert`)

Store in env/secrets only:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_TLS_MODE` (`starttls` or `ssl`)

## Backend Changes
1. Add system settings helpers for email config read/write (similar to timezone settings pattern).
2. Create email sender utility:
   - SMTP connection
   - timeout + retry
   - structured logging
3. Add API routes:
   - `GET /api/v1/system/email`
   - `PUT /api/v1/system/email`
   - `POST /api/v1/system/email/test`
4. Add event dispatcher hooks:
   - run terminal failure path
   - schedule launch failure path
   - critical alert path (if present from alerts payload)
5. Add payload templates:
   - concise subject and plain-text body
   - include run/schedule identifiers, status, timestamp, and relevant link

## Frontend Changes
1. Add Email Notifications panel in Config page:
   - enable toggle
   - from email/name
   - recipients input (comma/newline split)
   - trigger selection
2. Add `Send test email` button with success/error feedback.
3. Add API client methods for email settings/test endpoint.

## Validation Rules
- Reject invalid email formats in API.
- Require at least one recipient when enabled.
- Require `from_email` when enabled.
- Return clear errors if SMTP env secrets are missing.

## Security and Ops
- Never expose SMTP password in UI or API responses.
- Mask sensitive values in logs.
- Add rate limiting/cooldown for test-email endpoint.
- Rotate credentials if ever exposed.

## Testing Plan
- Unit tests:
  - settings validation
  - recipient parser
  - template rendering
- API tests:
  - get/update email settings
  - test-email endpoint success/failure
- Integration test:
  - mocked SMTP send on trigger events
- Manual QA:
  - save config
  - send test email
  - trigger a failure event and confirm delivery

## Rollout
1. Deploy with feature disabled by default.
2. Configure recipients/from address.
3. Run test-email check.
4. Enable selected event triggers.
5. Monitor logs and delivery failures.
