# `api_docs/` per-file JSON schema

One file per use case, at `api_docs/internal/<group>/<use_case>.json` or `api_docs/external/<group>/<use_case>.json`. `build_docs.py` validates every file against this shape and regenerates `manifest.json`.

```jsonc
{
  "useCase": "checkout_payment_intent",       // required, matches the filename stem
  "group": "payment",                          // required, matches the parent folder name
  "part": "internal",                          // required, "internal" | "external" — which API this file documents
  "endpoint": {                                 // required
    "method": "POST",                           // GET|POST|PATCH|DELETE|PUT|WSS
    "host": "lastmile.fainzy.tech",             // fainzy.tech | lastmile.fainzy.tech | localhost:PORT (for internal)
    "path": "/v1/core/create/payment-intent/"
  },
  "usedIn": {                                   // required
    "screen": "Checkout page",
    "chain": ["checkout_page.dart -> Make payment", "CheckoutBloc.on<MakePayment> (checkout_bloc.dart:112)", "..."]
  },
  "trigger": "User taps Make payment after placing an order",   // required, plain English
  "params": {                                   // required (empty objects allowed)
    "path": {}, "query": {}, "body": { "order_id": 517707, "...": "real value used in capture" }
  },
  "auth": {                                     // required
    "header": "Authorization",                  // "Authorization" | "Fainzy-Token" | "n/a" (socket)
    "value": null,                               // null until captured; real raw token value after
    "howObtained": "POST /v1/auth/users/auth/ (login)"
  },
  "sensitivePaths": ["auth.value", "response.data.client_secret"],  // required (array, may be empty)
  "alsoTriggeredBy": null,                      // null or array of "file:line -- description" strings
  "capture": {                                  // required
    "verifiedAt": null,                          // null until captured; ISO8601 with offset after
    "status": null,                              // null until captured; HTTP status int after
    "tool": "capture_session.py",
    "flavor": "development"
  },
  "response": null,                             // null until captured; full raw response body after
  "badge": "MUTATION -- gated behind --include-mutations",  // optional, short human-readable flag (DESCRIPTIVE ONLY)
  "expectedNon2xx": true,                        // optional; ONLY set when the endpoint genuinely returns non-2xx
  "note": "..."                                  // optional, free text (used by the socket file)
}
```

## Differences from `last_mile_user/api_docs/SCHEMA.md`

The **only addition** is the top-level `"part": "internal" | "external"` field. All other fields carry over unchanged — read the reference implementation's schema to understand `usedIn.chain`, `sensitivePaths` JSONPath syntax, and the distinction between `badge` (purely descriptive UI text, never excuses a failure) vs. `expectedNon2xx` (the only thing that tells `--strict` a non-2xx status is acceptable).

## Validation modes (`build_docs.py`)

- **Structural (default):** every required top-level key present (including `part`), `useCase`/`group`/`part` match the file's own path, `sensitivePaths` entries are dot/`[]` JSONPath-lite strings, `endpoint.method` is one of the allowed values. `capture.verifiedAt`/`response` may be `null` (skeleton state).
- **`--strict`:** additionally requires `capture.verifiedAt` to be today-or-recent, `capture.status` to be 200/201 **unless `expectedNon2xx: true`** is set (a `badge` alone does NOT excuse it), and `response` to be non-null and non-empty. Run `--strict` after a capture pass, not against fresh skeletons.

## `sensitivePaths`

Dot + `[]` JSONPath-lite, rooted at the file itself (so `auth.value` and `response.data.token` are both valid, `response.data[].card.fingerprint` reaches into an array of objects). This is the only redaction mechanism the viewer (Stage 6) uses — masks the referenced value behind a 👁 eye toggle; the underlying JSON always stores the real value.
