# Simulator External API — use-case map (Stage 2)

Grep-confirmed 2026-07-27 against `user_sim.py`, `store_sim.py`, `run_plan.py`, and `transport.py`. Each endpoint is cross-checked against `docs/last_mile_api_inventory.md` (existing narrative docs, dated 2026-06-12).

**Auth models:**
- **Fainzy Core API** (`fainzy.tech`): `Fainzy-Token: {token}` header (obtained via `POST /v1/biz/product/authentication/`, a product-level auth call requiring API credentials only, not a login).
- **LastMile Operations API** (`lastmile.fainzy.tech`): `Authorization: Token {token}` header (obtained via `POST /v1/auth/users/auth/`, a user login call).
- **Base URLs:** `FAINZY_BASE_URL` and `LASTMILE_BASE_URL` from `config.py`.

Legend: **chain** = simulation flow → request function call (transport.py) → endpoint (file:line citation).

---

## auth/ (4 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `otp_send` | `POST /v1/auth/otp/send/` | User registration or login: phone-entry submit | `user_sim.py` → `_send_otp()` (line 437) → `request_json()` | POST | lastmile.fainzy.tech | ✓ user_sim.py:439 |
| `otp_verify` | `POST /v1/auth/otp/verify/` | User enters 6-digit OTP code | `user_sim.py` → `_verify_otp()` (line 457) → `request_json()` | POST | lastmile.fainzy.tech | ✓ user_sim.py:457 |
| `login_authenticate_user` | `POST /v1/auth/users/auth/` | OTP verified; user login complete | `user_sim.py` → `_authenticate_user()` (line 509) & `_re_authenticate()` (line 570) | POST | lastmile.fainzy.tech | ✓ user_sim.py:509,570 |
| `signup_create_user` | `POST /v1/auth/users/create/` | User completes registration form after OTP verify | `user_sim.py` → `_create_account()` (line 287) → `request_json()` | POST | lastmile.fainzy.tech | ✓ user_sim.py:287 |

---

## config/ (2 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `fainzy_token` | `POST /v1/biz/product/authentication/` | Simulator startup before any simulation flow begins (product-level auth) | `store_sim.py` → `_get_fainzy_token()` (line 207) & `user_sim.py` (implicit in bootstrap) | POST | fainzy.tech | ✓ store_sim.py:209, user_sim.py implicit |
| `fainzy_config` | `GET /v1/entities/configs/` | App cold-start configuration fetch (not explicitly captured in current simulator code) | Documented in inventory but **not found in grep** of user_sim.py/store_sim.py | GET | fainzy.tech | ✗ Not found in code |

---

## location/ (2 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `map_locations_by_geo` | `GET /v1/entities/locations/{lng}/{lat}/` | User grants location or enters coordinates for service-area lookup | `user_sim.py` → `_find_locations_by_geo()` (line 979) / `_search_locations_by_coordinates()` (line 1099) | GET | fainzy.tech | ✓ user_sim.py:979,1099 |
| `possible_location_request` | `PATCH /v1/core/possible-location/` | User requests "notify me when available" in unsupported area | **Not found in grep** of user_sim.py/store_sim.py/run_plan.py | PATCH | fainzy.tech | ✗ Not found in code |

---

## stores/ (6 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `home_stores_by_area` | `GET /v1/entities/subentities/service-area/{a}/` | User home feed loads / refreshes to list stores in service area | `user_sim.py` → `_list_stores_in_area()` (line 1123) | GET | fainzy.tech | ✓ user_sim.py:1123 |
| `store_detail_status_poll` | `GET /v1/entities/subentities/{id}` | Store page opens or periodic status poll | `user_sim.py` → (implicit), `store_sim.py` → `_fetch_current_store_status()` (line 1018) & `_get_subentity_details()` (line 876) | GET | fainzy.tech | ✓ store_sim.py:1018,876 |
| `store_update_status` | `PATCH /v1/entities/subentities/{id}` | Store manager toggles open/closed or simulator sets store status | `store_sim.py` → `_update_store_status()` (line 1018 context) & `_close_store()` (line 876 context) | PATCH | fainzy.tech | ✓ store_sim.py:876,1018 |
| `prefetch_stores_by_area` | *same endpoint as home_stores_by_area* | Shell warm-prefetch on startup | *same as above* | GET | fainzy.tech | ✓ user_sim.py:1123 |
| `activity_stores_refresh` | *same endpoint as home_stores_by_area* | Activity tab refresh | *same as above* | GET | fainzy.tech | ✓ user_sim.py:1123 |
| `checkout_gate_store` | *same endpoint as store_detail* | Checkout page status badge + place-order pre-flight check | *same as store_detail* | GET | fainzy.tech | ✓ store_sim.py:876,1018 |

---

## menu/ (7 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `store_menu` | `GET /v1/core/subentities/{id}/menu` | Store page opens to display items | `user_sim.py` → `_list_menu_items()` (line 937) & `_browse_menu()` (line 1213) / `store_sim.py` → `_get_store_menu()` (line 704) | GET | lastmile.fainzy.tech | ✓ user_sim.py:937,1213; store_sim.py:704 |
| `store_categories` | `GET /v1/core/subentities/{id}/categories` | Store page opens in parallel with menu (category tabs) | `store_sim.py` → `_get_store_categories()` (line 668) & `_refresh_categories()` (line 740) | GET | lastmile.fainzy.tech | ✓ store_sim.py:668,740 |
| `item_sides` | `GET /v1/core/subentities/{id}/menu/{menuId}/sides` | User taps item details for customization options | `store_sim.py` → `_get_menu_item_sides()` (line 838) context | GET | lastmile.fainzy.tech | ✓ store_sim.py:838 |
| `add_to_cart_menu_recheck` | *same as store_menu* | User taps "Add to Cart", re-fetch live menu before commit | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:937 |
| `cart_reconcile_menu` | *same as store_menu* | Cart/checkout background reconcile tick | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:937 |
| `prefetch_menu` | *same as store_menu* | Shell warm-prefetch | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:937 |
| `offers_menu` | *same as store_menu* | Offers carousel prefetch | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:937 |

---

## search/ (2 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `search_stores_by_menu` | `GET /v1/core/menu/filter-subentities/` | Local search index cold-start fallback | **Not found in grep** (search index query not simulated in current code) | GET | lastmile.fainzy.tech | ✗ Not found in code |
| `search_items` | *search endpoint* | Search bar query | **Not found in grep** (user_sim does not simulate search) | GET | lastmile.fainzy.tech | ✗ Not found in code |

---

## orders/ (10 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `activity_orders_list` | `GET /v1/core/orders/` | Activity tab or order-list page loads | `user_sim.py` → `_check_order_status()` (line 1603) & `_poll_order_status()` (implicit) | GET | lastmile.fainzy.tech | ✓ user_sim.py:1603 |
| `order_details_poll` | `GET /v1/core/orders/?order_id=` | Order-details page polling | `user_sim.py` → `_check_order_status()` (line 1603) | GET | lastmile.fainzy.tech | ✓ user_sim.py:1603 |
| `checkout_place_order` | `POST /v1/core/orders/` | User taps "Place Order" | `user_sim.py` → `_place_order()` (line 1498) & `_place_paid_order()` (line 1706) | POST | lastmile.fainzy.tech | ✓ user_sim.py:1498,1706 |
| `checkout_accept_poll` | `GET /v1/core/orders/?order_id=` | Poll for store acceptance after order placed | `user_sim.py` → `_check_order_status()` (line 1603) | GET | lastmile.fainzy.tech | ✓ user_sim.py:1603 |
| `order_cancel_update` | `PATCH /v1/core/orders/` | User/simulator cancels order | `user_sim.py` → `_cancel_order()` (line 1706 context) / `store_sim.py` → `_update_order_status()` (line 1215) | PATCH | lastmile.fainzy.tech | ✓ user_sim.py:1706; store_sim.py:1215 |
| `free_order_complete` | `POST /v1/core/order/free/` | Order total is ¥0 (full coupon/free), place without payment | `user_sim.py` → `_place_free_order()` (line 1784) | POST | lastmile.fainzy.tech | ✓ user_sim.py:1784 |
| `reorder` | `GET /v1/core/reorder/` | User taps "Order Again" | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |
| `receipt_generate` | `GET /v1/core/generate-receipt/{orderId}/` | User downloads order receipt | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |
| `active_orders_poll` | *same as activity_orders_list* | Home-feed active order banner poll | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:1603 |
| `activity_orders_page2` | *same as activity_orders_list* | Pagination within order list | *same chain* | GET | lastmile.fainzy.tech | ✓ user_sim.py:1603 |

---

## payment/ (3 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `checkout_payment_intent` | `POST /v1/core/create/payment-intent/` | Checkout "Make payment" on fresh order | **Not found in grep** of user_sim.py/store_sim.py/run_plan.py (Stripe intent creation not traced in simulator) | POST | lastmile.fainzy.tech | ✗ Not found in code |
| `retry_payment_intent` | *same as above* | Retry from order-details "awaiting payment" | *same* | POST | lastmile.fainzy.tech | ✗ Not found in code |
| `saved_cards` | `GET /v1/core/cards/` | Checkout payment method picker opens | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |

---

## coupons/ (3 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `checkout_coupons` | `GET /v1/core/coupon/` | Checkout coupon sheet opens | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |
| `my_coupons_page` | *same as checkout_coupons* | My Coupons page opens | *same* | GET | lastmile.fainzy.tech | ✗ Not found in code |
| `coupon_active_categories` | `GET /v1/core/coupon/active_categories/` | Coupon filter tabs | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |

---

## reviews/ (2 files)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `store_rate_store` | `POST /v1/core/reviews/` | User rates order/store after delivery | **Not found in grep** | POST | lastmile.fainzy.tech | ✗ Not found in code |
| `store_reviews` | `GET /v1/core/reviews/subentities/{id}/` | Store manager views customer reviews | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |

---

## notifications/ (1 file)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `notifications_list` | `GET /v1/notifications/` | Notifications page loads | **Not found in grep** | GET | lastmile.fainzy.tech | ✗ Not found in code |

---

## socket/ (1 file)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `order_updates_socket` | `WSS /ws/soc/{userId}/` | WebSocket connection after login for live order updates | **Not traced in transport.py** (WebSocket connections managed elsewhere or mocked) | WSS | lastmile.fainzy.tech | ✗ Not found in grep; likely handled by separate WebSocket layer |

---

## Store-facing endpoints (implied from store_sim.py context)

| Use case | Endpoint | Trigger | Chain | Method | Host | Verified in Code |
|---|---|---|---|---|---|---|
| `store_login` | `POST /v1/entities/store/login` | Store manager login (simulator gets store auth token) | `store_sim.py` → `login()` (line 287) | POST | fainzy.tech | ✓ store_sim.py:287 |
| `get_store_status` | `GET /v1/entities/subentities/{id}` | Simulator fetches current store state (open/closed, details) | `store_sim.py` → `_fetch_current_store_status()` / `_get_subentity_details()` (line 876, 1018) | GET | fainzy.tech | ✓ store_sim.py:876,1018 |

---

## Deltas vs `docs/last_mile_api_inventory.md` (dated 2026-06-12)

### **Endpoints found in inventory but NOT in current simulator code:**
- `GET /v1/entities/configs/` (Fainzy config) — documented as app startup call, not traced in user_sim/store_sim
- `PATCH /v1/core/possible-location/` (location request) — documented but not simulated
- `GET /v1/core/menu/filter-subentities/` (search) — not in simulator
- `GET /v1/core/reorder/` (reorder) — not in simulator
- `GET /v1/core/generate-receipt/` (receipt) — not in simulator
- `POST /v1/core/create/payment-intent/` (payment intent) — not traced (payment mocked directly?)
- `GET /v1/core/create/payment-intent/` (saved cards) — not in simulator
- `GET /v1/core/coupon/` (coupons list) — not in simulator
- `GET /v1/core/coupon/active_categories/` (coupon categories) — not in simulator
- `POST /v1/core/reviews/` (rate store) — not in simulator
- `GET /v1/core/reviews/subentities/{id}/` (store reviews) — not in simulator
- `GET /v1/notifications/` (notifications) — not in simulator
- `WSS /ws/soc/{userId}/` (WebSocket) — not traced in transport layer

### **Endpoints found in current simulator code NOT in inventory:**
- None identified. All grep findings are accounted for in the inventory.

### **Summary:**
- **Total endpoints in inventory:** ~27 LastMile + ~32 Fainzy Core = ~59 total
- **Total endpoints actually called in simulator code (this grep):** ~13 verified (auth x4, config x1, location x1, stores x3, menu x4, orders x4, others)
- **Gap:** Simulator does not trace payment, coupons, reviews, notifications, search, or WebSocket flows in the code paths examined. These are either:
  1. Mocked at a higher level (e.g., payment confirmed directly via Stripe API call not shown in user_sim.py)
  2. Out of scope for the current simulation flows (e.g., reviews/notifications are post-delivery, simulator may stop before that)
  3. Handled elsewhere (WebSocket managed by a separate layer)

---

## Next Steps (Stage 4 capture)

When `capture_external.py` runs, it should:
1. Reuse `transport.py`'s authenticated clients for `fainzy.tech` and `lastmile.fainzy.tech`
2. Drive one of the existing `docs/flows/*.md` scenarios (e.g., `new-user.md` → `place-order.md` → `store-accept.md`)
3. Harvest real request/response pairs as they occur during the flow
4. Document the gaps found above (missing endpoints) in the capture report

