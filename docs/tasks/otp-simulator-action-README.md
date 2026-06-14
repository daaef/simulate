# OTP Request — Add simulator action field

> Completed: 2026-06-14  
> Files changed: `user_sim.py`  
> Checklist items fixed: 0 (change was already clean)

---

## What happened (Layman)

The simulator pretends to be a real user logging into the last-mile delivery app using a one-time password (OTP) — a short code sent to a phone number. The server that sends those OTPs now needs to know whether the request is coming from a real person or from the simulator, so it can handle the two cases differently. Previously the simulator sent only the phone number; now it also sends a label `"action": "simulator"` so the server can tell the request apart from a genuine user login.

---

## How it works (Pseudocode)

1. The simulator picks up the phone number to authenticate.
2. It builds a request body to send to the OTP-sending endpoint.
3. **Before:** the body contained only `{ phone_number }`.  
   **After:** the body contains `{ action: "simulator", phone_number }`.
4. The server receives the extra field and can route or log the request accordingly.
5. The rest of the OTP flow (receiving the code, verifying it) is unchanged.

---

## The implementation (Code-level)

**Changed files:**
- [user_sim.py:442](user_sim.py#L442) — `json_body` dict in the OTP send call extended with `"action": "simulator"`

**Key change:**
```python
# Before
json_body={"phone_number": effective_phone},

# After
json_body={"action": "simulator", "phone_number": effective_phone},
```

---

## Why this way (Advanced)

The server API contract now distinguishes simulator-originated OTP requests from real user requests via an `"action"` discriminator field. Adding it directly to the `json_body` dict at the single call site is the MES — there is only one place in the codebase that sends this request (`user_sim.py` line 442 inside the `for attempt in (1, 2)` retry loop), so no abstraction or constant is warranted. A named constant would be premature for a single-use string that mirrors a server-side enum value — the string's source of truth is the API, not this client. The change is additive and non-breaking: the server must already be tolerant of unknown fields, and the `"phone_number"` key is unchanged, so the existing OTP verify path and retry logic are completely unaffected.

---

## Verification

- [ ] Run the simulator against a test environment and observe the OTP request in the trace log — confirm the logged `json_body` shows `{"action": "simulator", "phone_number": "..."}`.
- [ ] Confirm the server returns a valid OTP (HTTP 200 / data present) with the new payload — the existing `if not otp: raise RuntimeError(...)` guard will surface any server rejection immediately.
- [ ] `python -m pytest tests/` passes with no new failures.
