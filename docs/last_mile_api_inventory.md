# Last Mile System — API Reference & Use Cases

**Projects covered:** last_mile_user · last_mile_store · dashboard · simulate  
**Date:** 2026-06-12  
**Backends:** Fainzy Core API · LastMile Operations API · Web/CMS API · WebSockets · Google Maps · Stripe · Firebase · Simulator Internal API

---

## How to read this document

Each endpoint entry contains:

- **When it is called** — the exact user action or system event that triggers the request.
- **What it does** — what the server processes and returns.
- **Used by** — which app(s) make the call.

Endpoints are grouped by the feature flow they belong to, not just by HTTP resource.

---

# Part 1 — Fainzy Core API

**Base URL:** `https://fainzy.tech/v1/`  
**Purpose:** Manages entity identity (businesses, stores, users), product catalogue (menus, categories, sides, images), pricing, business operations (KYC, bank details, payouts), and location discovery.  
**Auth:** `Authorization: Token {token}` for most calls. Some store-facing calls use `Fainzy-Token: {token}`.

---

## A. App Bootstrap & Configuration

These calls happen once at app startup, before the user interacts with anything. They establish the base configuration that all other features depend on.

---

### `GET https://fainzy.tech/v1/entities/configs/`

**When:** Called immediately when the user app, store app, or dashboard loads — before rendering any screen.  
**What it does:** Returns the global Fainzy configuration object: feature flags, supported currencies, service parameters, and environment-level settings. Without this, the app does not know which features are active or how to configure payments and locations.  
**Used by:** user app, store app, dashboard

---

### `POST https://fainzy.tech/v1/biz/product/authentication/`

**When:** Called at startup, right after `https://fainzy.tech/v1/entities/configs/`, using machine credentials (not the end user's login). Also called by the simulator before any simulation flow begins.  
**What it does:** Exchanges a product-level credential (API key or product identifier) for a short-lived service token. This token is then attached to all subsequent API calls as the base auth layer. In the dashboard, the query param `?product=dashboard` scopes the token to dashboard-level permissions.  
**Used by:** user app, store app, dashboard, simulator

---

## B. User Account Management

Covers the full lifecycle of a customer account: registration, phone verification, login, password recovery, and account deletion.

---

### `POST https://lastmile.fainzy.tech/v1/auth/otp/send/` *(LastMile API)*

**When:** Called when a new user enters their phone number on the registration screen, or when an existing user requests a one-time code to log in.  
**What it does:** Sends an SMS OTP to the provided phone number. The code expires after a short window. No account is created at this stage.  
**Used by:** user app, simulator

---

### `POST https://lastmile.fainzy.tech/v1/auth/otp/verify/` *(LastMile API)*

**When:** Called immediately after the user enters the OTP code they received by SMS.  
**What it does:** Validates the OTP against the one sent. On success, either confirms the phone number is valid (for registration) or returns a session token (for login-via-OTP flows). On failure, returns an error that prompts a retry or resend.  
**Used by:** user app, simulator

---

### `POST https://lastmile.fainzy.tech/v1/auth/users/create/` *(LastMile API)*

**When:** Called after OTP verification when the user completes the registration form (name, email, password).  
**What it does:** Creates a new customer account with the verified phone number and supplied profile data. Returns the new user's ID and auth token, logging them in immediately after registration.  
**Used by:** user app, simulator

---

### `PATCH https://lastmile.fainzy.tech/v1/auth/users/create/` *(LastMile API)*

**When:** Called when an authenticated user edits their profile — changing their name, email, or any personal detail.  
**What it does:** Updates the fields sent in the request body on the existing user record. Returns the updated profile.  
**Used by:** user app

---

### `DELETE https://lastmile.fainzy.tech/v1/auth/users/create/` *(LastMile API)*

**When:** Called when an authenticated user chooses "Delete my account" in settings.  
**What it does:** Marks the account as deleted, terminates the session, and revokes the auth token. The user is logged out and the app returns to the landing screen.  
**Used by:** user app

---

### `POST https://lastmile.fainzy.tech/v1/auth/users/auth/` *(LastMile API)*

**When:** Called when a returning user submits their phone number and password on the login screen.  
**What it does:** Validates credentials and returns an auth token on success. This token is stored locally and attached to all subsequent requests until logout or token expiry.  
**Used by:** user app, simulator

---

### `POST https://lastmile.fainzy.tech/v1/auth/users/reactivate/` *(LastMile API)*

**When:** Called when a previously deactivated user attempts to log in and the app detects their account status is inactive.  
**What it does:** Re-enables the account and restores access. The user may be prompted to confirm reactivation before this is called.  
**Used by:** user app

---

### `POST https://lastmile.fainzy.tech/v1/auth/password/reset/` *(LastMile API)*

**When:** Called when the user taps "Forgot password" and submits their registered phone number or email.  
**What it does:** Sends a password reset link or code to the user's contact method. Does not immediately change the password.  
**Used by:** user app

---

### `POST https://lastmile.fainzy.tech/v1/auth/password/resetconfirm/` *(LastMile API)*

**When:** Called when the user submits a new password together with the reset token they received.  
**What it does:** Validates the reset token and, if valid, updates the password. On success the user can log in with their new credentials.  
**Used by:** user app

---

## C. Entity & Store Identity (Business Accounts)

These endpoints manage the identity and profile of stores and business owners — distinct from customer accounts.

---

### `POST https://fainzy.tech/v1/entities/create`

**When:** Called when a new business owner completes the onboarding sign-up form on the dashboard.  
**What it does:** Creates a new entity (business) record with the provided business name, contact info, and initial settings. Returns the entity ID used in all subsequent business-level operations.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/entities/login`

**When:** Called when a business owner submits their credentials on the dashboard login page.  
**What it does:** Authenticates the entity (business) account and returns a session token with entity-level permissions. This is distinct from the LastMile user auth — it gates access to the business dashboard.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/entities/store/login`

**When:** Called when a store manager opens the store app and logs in with their store credentials.  
**What it does:** Authenticates the store account, fetches the store's profile (subentity data, settings, status), and returns an auth token scoped to that store. The simulator calls this at the start of a store simulation flow.  
**Used by:** store app, simulator

---

### `POST https://fainzy.tech/v1/entities/activate/account/{id}/email_verification/`

**When:** Called when a business owner clicks the email verification link sent after registration.  
**What it does:** Marks the entity's email address as verified, unlocking features that require a verified identity (e.g., KYC submission, payouts).  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/entities/details/{userId}`

**When:** Called when the dashboard loads the account settings or profile page for the logged-in business owner.  
**What it does:** Returns the full entity profile: business name, contact details, verification status, linked stores, and account settings.  
**Used by:** dashboard

---

### `PATCH https://fainzy.tech/v1/entities/details/{entityId}/`

**When:** Called when a business owner saves changes on the profile or settings page.  
**What it does:** Updates any combination of the entity's fields (name, contact info, preferences). Only the fields included in the request body are changed.  
**Used by:** dashboard

---

### `PATCH https://fainzy.tech/v1/entities/details/reset_profile_picture/`

**When:** Called when a business owner clicks "Remove photo" on their profile.  
**What it does:** Clears the profile picture, reverting to the default avatar. Does not require a new image to be provided.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/entities/details/change_password/`

**When:** Called when the business owner submits the "Change password" form on account settings.  
**What it does:** Validates the current password and, if correct, replaces it with the new one. Requires the user to be authenticated.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/entities/password/reset` / `POST https://fainzy.tech/v1/entities/password/resetconfirm/` / `POST https://fainzy.tech/v1/entities/password/resetvalidate_token/`

**When:** Called in sequence when a business owner uses the "Forgot password" flow on the dashboard login page.  
**What it does:** `https://fainzy.tech/v1/reset` sends the reset email. `https://fainzy.tech/v1/resetvalidate_token` checks that the token from the email is still valid. `https://fainzy.tech/v1/resetconfirm` sets the new password. All three must succeed in order before access is restored.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/entities/subentities`

**When:** Called when the dashboard needs to list all stores (subentities) belonging to the logged-in entity, e.g. on the store selector or the stores overview page.  
**What it does:** Returns an array of all subentity records linked to the entity: store names, IDs, statuses, and summary info.  
**Used by:** dashboard

---

### `PATCH https://fainzy.tech/v1/entities/subentities/{id}`

**When:** Called when a store manager opens or closes their store (toggles the "Open / Closed" switch), or when the simulator sets a store's status as part of a simulation flow.  
**What it does:** Updates one or more fields on the subentity record — most commonly the `is_open` flag, but can also update operating hours, contact info, or other store-level settings.  
**Used by:** store app, simulator

---

## D. Location & Store Discovery

The flow a customer goes through before they see any stores: granting location access, finding what service areas are nearby, and listing available stores.

---

### `GET https://fainzy.tech/v1/entities/locations/{lng}/{lat}/`

**When:** Called as soon as the user grants location permission (or after they manually enter an address), to determine which Fainzy service areas are near them.  
**What it does:** Takes GPS coordinates and returns the service area(s) that cover that location, including the service area ID needed for the next call. If no service area covers the coordinates, the app shows the "unavailable area" screen.  
**Query params:** `search_radius` — adjusts how wide the lookup is.  
**Used by:** user app, simulator

---

### `GET https://fainzy.tech/v1/entities/subentities/service-area/{serviceAreaId}/`

**When:** Called immediately after a service area is confirmed, to populate the home screen store list.  
**What it does:** Returns all stores (subentities) operating within the given service area, with their names, categories, images, rating, open/closed status, and delivery estimates. This is the primary feed the customer scrolls through.  
**Used by:** user app, simulator

---

### `GET https://fainzy.tech/v1/core/menu/filter-subentities/`

**When:** Called when the user types in the search bar on the home screen — searching either for a dish name or a store name.  
**What it does:** Returns stores whose menus or names match the `search` query, optionally filtered by `location`. Enables the "search for jollof rice and get all stores that have it" experience.  
**Query params:** `search`, `location`  
**Used by:** user app

---

### `PATCH https://fainzy.tech/v1/core/possible-location/`

**When:** Called when a user in an unsupported area submits a "Notify me when available" request.  
**What it does:** Records the user's location as a demand signal so operations can prioritise expansion. Does not create an order or subscription.  
**Used by:** user app

---

### `POST https://fainzy.tech/v1/biz/possible-location/`

**When:** Called from the dashboard when operations staff manually log an unserved location request.  
**What it does:** Same purpose as the user-facing version above, but submitted with business credentials.  
**Used by:** dashboard

---

## E. Menu, Categories & Sides Management

Everything related to building and maintaining what a store sells. Both the store app and dashboard can manage these; the user app reads them.

---

### `GET https://fainzy.tech/v1/core/subentities/{id}/categories`

**When:** Called when the store menu screen loads — both in the user app (to render filter tabs) and in the store/dashboard (to list categories for editing).  
**What it does:** Returns all category records for the given store: category name, ID, display order, and whether it is currently active.  
**Used by:** user app, store app, dashboard

---

### `POST https://fainzy.tech/v1/core/subentities/{id}/categories`

**When:** Called when a store manager or dashboard admin creates a new category (e.g., "Drinks", "Desserts") in the menu editor.  
**What it does:** Creates a new category record under the specified store, returns the new category ID for immediate use when adding menu items to it.  
**Used by:** store app, dashboard, simulator

---

### `PATCH https://fainzy.tech/v1/core/subentities/{id}/categories/{categoryId}`

**When:** Called when a dashboard admin renames a category, reorders it, or toggles its active state.  
**What it does:** Updates the specified fields on the category. Changes are reflected immediately in the user app's category tabs on next load.  
**Used by:** dashboard

---

### `DELETE https://fainzy.tech/v1/core/subentities/{id}/categories/{categoryId}`

**When:** Called when a dashboard admin permanently removes a category that is no longer needed.  
**What it does:** Deletes the category record. Behaviour of associated menu items (orphaned or also deleted) depends on the server implementation.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/core/subentities/{id}/menu`

**When:** Called when a user opens a store page to view its menu, when a store manager loads the menu editor, or at the start of a simulator flow to list available items.  
**What it does:** Returns all menu items for the store, each with name, description, price, image, availability flag, and category association. Accepts an optional `categoryId` param to return items for one category only.  
**Used by:** user app, store app, dashboard, simulator

---

### `POST https://fainzy.tech/v1/core/subentities/{id}/menu`

**When:** Called when a store manager or dashboard admin adds a new item to the menu.  
**What it does:** Creates a new menu item record (name, description, price, category, images). The item is immediately visible in the user app once created.  
**Used by:** store app, dashboard, simulator

---

### `PATCH https://fainzy.tech/v1/core/subentities/{id}/menu/{menuId}`

**When:** Called when a store manager edits an existing item — changing its price, description, availability status, or category. Also called by the simulator to toggle item availability as part of a test scenario.  
**What it does:** Updates the specified fields on the menu item. A common use is flipping `is_available` to mark an item as sold out without deleting it.  
**Used by:** store app, dashboard, simulator

---

### `DELETE https://fainzy.tech/v1/core/subentities/{id}/menu/{menuId}`

**When:** Called when a store manager or dashboard admin permanently removes a menu item.  
**What it does:** Deletes the menu item record. This is irreversible; managers typically use PATCH to mark items unavailable rather than deleting.  
**Used by:** store app, dashboard

---

### `GET https://fainzy.tech/v1/core/subentities/{id}/menu/{menuId}/sides`

**When:** Called when a user taps on a menu item that has customisation options (e.g., choosing a size, extra sauce). Also called in the store editor when viewing the sides linked to an item.  
**What it does:** Returns all side/add-on options associated with the item: names, prices, and whether they are required or optional selections.  
**Used by:** user app, store app

---

### `POST https://fainzy.tech/v1/core/subentities/{id}/sides`

**When:** Called when a store manager or dashboard admin adds a new side/add-on option to a menu item.  
**What it does:** Creates a new side record and links it to the parent menu item. Customers will see it as a selectable option when ordering that item.  
**Used by:** store app, dashboard

---

### `PATCH https://fainzy.tech/v1/core/subentities/{id}/sides/{sideId}`

**When:** Called when a store manager edits a side — changing its name, price, or availability.  
**What it does:** Updates the specified fields on the side record.  
**Used by:** store app

---

### `DELETE https://fainzy.tech/v1/core/subentities/{id}/sides/{sideId}`

**When:** Called when a store manager removes a side option that is no longer offered.  
**What it does:** Deletes the side record. The option disappears from the item's customisation screen in the user app.  
**Used by:** store app

---

### `POST https://fainzy.tech/v1/core/subentities/{id}/images`

**When:** Called when a store manager uploads a photo for a menu item or for the store itself.  
**What it does:** Accepts a multipart form upload, stores the image, and returns an image ID and URL. The URL is then associated with the menu item or store profile.  
**Used by:** store app

---

### `DELETE https://fainzy.tech/v1/core/subentities/{id}/images/{imageId}`

**When:** Called when a store manager removes a photo from a menu item or store profile.  
**What it does:** Deletes the image record and its stored file. The item reverts to showing no image or a placeholder.  
**Used by:** store app

---

## F. Pricing & Business Setup

Endpoints used during onboarding and for configuring business-level financial details.

---

### `GET https://fainzy.tech/v1/biz/pricing/0/`

**When:** Called in the user app when the checkout screen loads, to display current delivery fees and pricing tiers.  
**What it does:** Returns the active pricing configuration: delivery fee tiers, minimum order values, and service charges for the customer's currency. The `0` path segment is parameterised by currency ID.  
**Used by:** user app

---

### `GET https://fainzy.tech/v1/biz/pricing/products/`

**When:** Called during dashboard onboarding when the business owner is choosing a subscription plan.  
**What it does:** Returns available product/subscription tiers with their prices, features, and billing cycles.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/biz/supported-countries/`

**When:** Called on the onboarding "Select your country" screen.  
**What it does:** Returns the list of countries where Fainzy operates, with their currency codes and any country-specific settings. Drives the country picker UI.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/biz/bank-detail/{currency}/`

**When:** Called when the business owner views their payout bank details, or when onboarding asks them to set up a bank account for a specific currency.  
**What it does:** Returns the current bank account record for that currency: account name, number, bank name, and verification status.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/biz/update/bank-details/`

**When:** Called when the business owner submits or updates their primary bank account for receiving payouts.  
**What it does:** Creates or replaces the bank account record for the entity. Triggers a verification check on the bank details before payouts are enabled.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/biz/update/bank-details/create_another_account`

**When:** Called when a business owner with multiple currencies adds an additional bank account to receive payouts in a different currency.  
**What it does:** Creates a new bank account record alongside the existing one, without replacing it.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/biz/kyc/verification/`

**When:** Called when the business owner submits their identity and business documents (e.g., CAC certificate, ID) through the KYC verification flow.  
**What it does:** Uploads the documents and queues them for review. The entity's KYC status changes to "pending" until the review is complete. Full payout access requires a verified KYC status.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/biz/subscriptions/`

**When:** Called when a business owner selects and confirms a subscription plan on the dashboard.  
**What it does:** Creates a subscription record linking the entity to the chosen product tier. Activates the corresponding feature set for their account.  
**Used by:** dashboard

---

### `POST https://fainzy.tech/v1/biz/payment-intent/` *(Fainzy API — business billing)*

**When:** Called when a business owner is about to pay for a subscription or a platform fee on the dashboard.  
**What it does:** Creates a Stripe payment intent for the business billing charge and returns the client secret needed to complete the payment on the client side.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/biz/payouts/`

**When:** Called when the business owner opens the Payouts section of the dashboard.  
**What it does:** Returns a paginated list of all payout transactions: amounts, dates, statuses (pending, processed, failed), and destination bank accounts.  
**Used by:** dashboard

---

### `GET https://fainzy.tech/v1/biz/dashboard/unassigned/entity/stores/`

**When:** Called when the dashboard needs to show stores that have not yet been linked to an entity account — typically during the onboarding store assignment step.  
**What it does:** Returns stores that exist in the system but have no parent entity, allowing the business owner to claim and link them.  
**Used by:** dashboard

---

---

# Part 2 — LastMile Operations API

**Base URL:** `https://lastmile.fainzy.tech/v1/`  
**Purpose:** Handles the live operational layer of the delivery platform — order lifecycle, real-time rider dispatch, payments, reviews, notifications, and analytics.  
**Auth:** `Authorization: Token {token}`

---

## G. Order Placement & Lifecycle

The sequence from a customer tapping "Place Order" to a store completing it.

---

### `POST https://lastmile.fainzy.tech/v1/core/create/payment-intent/`

**When:** Called when a customer taps "Proceed to checkout" on a paid order.  
**What it does:** Creates a Stripe payment intent on the server side and returns a client secret. The app uses this secret to render the Stripe payment sheet (card entry UI). No money is charged at this point — the charge is only captured when the order is confirmed.  
**Used by:** user app, simulator

---

### `POST https://lastmile.fainzy.tech/v1/core/orders/`

**When:** Called when the customer confirms their order — after payment details are entered and they tap "Place Order".  
**What it does:** Creates the order record with all items, quantities, selected sides, delivery address, and payment intent ID. Returns the order ID and initial status (`pending`). This triggers the real-time notification to the store.  
**Used by:** user app, simulator

---

### `POST https://lastmile.fainzy.tech/v1/core/order/free/`

**When:** Called instead of the standard order endpoint when the order total is zero (e.g., fully covered by a coupon or a free promo).  
**What it does:** Creates the order record without requiring a payment intent. Completes immediately since no payment processing is needed.  
**Used by:** user app, simulator

---

### `GET https://lastmile.fainzy.tech/v1/core/orders/`

**When:** Called in multiple contexts:
- User app: when the customer opens the "My Orders" screen, or polls for the status of an active order.
- Store app: when the store dashboard loads to show the current queue of incoming orders.
- Dashboard: when the analytics view queries orders within a date range.
- Simulator: to validate that an order was placed and to check its current status.  

**What it does:** Returns a filtered, paginated list of orders. Key query params: `order_id` (fetch a single order), `subentity_id` (store's orders), `filter` (status filter: pending, accepted, completed, etc.), `page` (pagination), `start_date` / `end_date` (analytics range).  
**Used by:** user app, store app, dashboard, simulator

---

### `PATCH https://lastmile.fainzy.tech/v1/core/orders/`

**When:** Called whenever an order's status changes:
- Store accepts an order → status becomes `accepted`.
- Store marks food as ready → status becomes `ready`.
- Rider picks up → `picked_up`.
- Delivered → `completed`.
- Cancelled by store or customer → `cancelled`.  

**What it does:** Updates the order's status field and timestamps accordingly. Each status transition triggers a WebSocket push to the relevant parties (customer, store).  
**Query param:** `order_id`  
**Used by:** user app (cancellation), store app, simulator

---

### `GET https://lastmile.fainzy.tech/v1/core/reorder/`

**When:** Called when the customer taps "Reorder" on a past order in their order history.  
**What it does:** Returns the items from the original order with their current prices and availability. The app pre-populates the cart with these items so the customer can review and modify before placing a new order.  
**Used by:** user app

---

## H. Payments, Coupons & Saved Cards

---

### `GET https://lastmile.fainzy.tech/v1/core/coupon/`

**When:** Called when the customer opens the "Apply coupon" screen on checkout.  
**What it does:** Returns all coupons currently available to the customer: codes, discount amounts or percentages, expiry dates, and any conditions (minimum order value, applicable stores or categories).  
**Used by:** user app

---

### `GET https://lastmile.fainzy.tech/v1/core/coupon/active_categories/`

**When:** Called alongside `https://lastmile.fainzy.tech/v1/core/coupon/` when the coupon screen needs to show filter tabs by category (e.g., "All", "Food", "Drinks").  
**What it does:** Returns the distinct categories that have active coupons, used to build the filter UI.  
**Used by:** user app

---

### `GET https://lastmile.fainzy.tech/v1/core/cards/`

**When:** Called when the payment screen loads and needs to show the customer's saved payment cards.  
**What it does:** Returns the list of tokenised card records on file: last four digits, card brand, and expiry date. Allows the customer to select a saved card without re-entering details.  
**Used by:** user app

---

## I. Reviews & Receipts

---

### `POST https://lastmile.fainzy.tech/v1/core/reviews/`

**When:** Called when a customer submits a star rating and optional written review after an order is delivered.  
**What it does:** Creates a review record linked to the store and the completed order. The rating contributes to the store's aggregate score shown on the home screen.  
**Used by:** user app

---

### `GET https://lastmile.fainzy.tech/v1/core/reviews/subentities/{id}/`

**When:** Called when a store manager opens the Reviews section in the store app dashboard.  
**What it does:** Returns all customer reviews for the specified store: ratings, written comments, reviewer names (or anonymised), and timestamps.  
**Used by:** store app

---

### `GET https://lastmile.fainzy.tech/v1/core/generate-receipt/{orderId}/`

**When:** Called when the customer taps "Download receipt" on a completed order.  
**What it does:** Generates and returns a PDF receipt for the order: items, prices, delivery fee, payment method, and order reference. The app opens or shares this file.  
**Used by:** user app

---

## J. Notifications

---

### `GET https://lastmile.fainzy.tech/v1/notifications/`

**When:** Called when the customer or store manager opens the Notifications screen, and on app resume to check for new alerts.  
**What it does:** Returns a paginated list of notifications: order updates, promotional messages, system alerts, and their read/unread status.  
**Used by:** user app, store app

---

## K. Store Statistics & Analytics

---

### `GET https://lastmile.fainzy.tech/v1/statistics/subentities/{id}/`

**When:** Called when the store manager opens the main Statistics screen in the store app.  
**What it does:** Returns aggregate order metrics for the store: total orders, completed vs cancelled counts, average delivery time, and peak hour breakdowns over a configurable time window.  
**Used by:** store app

---

### `GET https://lastmile.fainzy.tech/v1/statistics/subentities/{id}/revenue/`

**When:** Called when the store manager opens the Revenue tab within Statistics.  
**What it does:** Returns revenue data broken down by day/week/month: gross revenue, net revenue after fees, and trend comparisons with the previous period.  
**Used by:** store app

---

### `GET https://lastmile.fainzy.tech/v1/statistics/subentities/{id}/top-customers/`

**When:** Called when the store manager opens the Customers tab within Statistics.  
**What it does:** Returns a ranked list of the store's highest-value or most frequent customers: order count, total spend, and last order date. Useful for loyalty or retention insight.  
**Used by:** store app

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/home/`

**When:** Called when the dashboard home screen loads for a logged-in business owner.  
**What it does:** Returns the top-level KPI summary card data across all their stores for the selected date range: total orders, total revenue, average order value, and period-over-period comparison.  
**Query params:** `store_id`, `main_start_date`, `end_date`, `secondary_start_date`, `secondary_end_date`  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/orders/`

**When:** Called when the dashboard opens the Orders Analytics page.  
**What it does:** Returns a time-series breakdown of orders for the specified store and date range: order volume by day, fulfilment rate, cancellation rate, and status distribution.  
**Query params:** `subentity_id`, `start_date`, `end_date`  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/all_stores_review/`

**When:** Called when the dashboard loads the Reviews analytics page for an entity with multiple stores.  
**What it does:** Returns aggregated review data across all specified stores: average ratings, review counts, and sentiment trends.  
**Query params:** `ids` (comma-separated store IDs)  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/ratings/`

**When:** Called alongside `https://lastmile.fainzy.tech/v1/all_stores_review/` to get the rating distribution breakdown (1–5 stars).  
**What it does:** Returns star-rating distribution counts per store, enabling the "% of 5-star reviews" type display.  
**Query params:** `ids`  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/payment/{id}/`

**When:** Called when the dashboard opens the Payments analytics view.  
**What it does:** Returns payment method breakdowns, revenue totals, and transaction statuses for the specified store(s) over the date range.  
**Query params:** `ids`, `start_date`, `end_date`  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/menu/`

**When:** Called when the dashboard opens the Menu Analytics page.  
**What it does:** Returns performance data per menu item across all selected stores: order frequency, revenue contribution, and which items are declining in popularity.  
**Used by:** dashboard

---

### `GET https://lastmile.fainzy.tech/v1/core/analytics/category/`

**When:** Called to populate category-level performance breakdowns on the analytics screens.  
**What it does:** Returns aggregate order and revenue figures grouped by menu category.  
**Used by:** dashboard

---

---

# Part 3 — Web / CMS API

**Base URL:** `https://web.fainzy.tech/v1/`  
**Purpose:** Serves marketing copy, translated UI strings, and newsletter management for the customer-facing website and the dashboard.

---

### `GET https://web.fainzy.tech/v1/site/content`

**When:** Called when any page that uses dynamic CMS-managed content loads.  
**What it does:** Returns the site's static content blocks — hero text, feature descriptions, legal copy — used to populate content-managed sections of the dashboard UI without a redeploy.  
**Used by:** dashboard

---

### `GET https://web.fainzy.tech/v1/dashboard/dashboard-content/?lang={lang}`

**When:** Called on dashboard load with the user's selected language to fetch localised UI strings.  
**What it does:** Returns translated labels, messages, and UI copy for the entire dashboard in the requested language. Enables multi-language support without shipping separate builds.  
**Used by:** dashboard

---

### `POST https://web.fainzy.tech/v1/site/newsletters/subscribe`

**When:** Called when a visitor on the marketing site or dashboard submits their email in a newsletter sign-up form.  
**What it does:** Adds the email address to the Fainzy newsletter subscriber list. Returns a success confirmation; no opt-in token is required.  
**Used by:** dashboard

---

---

# Part 4 — WebSocket Connections

**Base URL:** `wss://lastmile.fainzy.tech`  
**Protocol:** Secure WebSocket (WSS)  
**Reconnection:** Exponential backoff with a 30-second maximum delay. All connections use broadcast streams so multiple listeners (e.g., notification handler + order screen) can subscribe without multiple connections.

---

### `wss://lastmile.fainzy.tech/ws/soc/{userId}/`

**When:** Opened as soon as the customer places an order and remains open until the order is delivered or cancelled.  
**What it does:** Pushes real-time status updates to the customer without polling: `accepted` (store confirmed), `ready` (food prepared), `picked_up` (rider has collected), `delivered`, `cancelled`. Each event updates the live order tracking screen immediately.  
**Used by:** user app, simulator

---

### `wss://lastmile.fainzy.tech/ws/soc/store_{storeId}/`

**When:** Opened when the store manager starts the store app and keeps running as long as the app is in the foreground (or background on mobile).  
**What it does:** Delivers incoming order notifications in real time — a new order event fires immediately when a customer places an order. The store can then accept or reject without any polling. Also delivers order status updates triggered by other parties (e.g., rider events).  
**Used by:** store app, simulator

---

### `wss://lastmile.fainzy.tech/ws/soc/store_statistics_{storeId}/`

**When:** Opened when the store manager is viewing the live statistics dashboard.  
**What it does:** Streams live updates to key metrics — order count, revenue totals — so the statistics screen refreshes in real time without manual refresh. Closes when the manager navigates away from the statistics screen.  
**Used by:** store app, simulator

---

---

# Part 5 — Third-Party Services

---

## L. Google Maps Platform

**Base URL:** `https://maps.googleapis.com/maps/api/`  
**Auth:** `key={apiKey}` query parameter

---

### `GET https://maps.googleapis.com/maps/api/geocode/json`

**When:** Called after the user drops a pin on the map or the device GPS returns coordinates, to translate coordinates into a human-readable address.  
**What it does:** Reverse-geocodes a `latlng` pair into a formatted street address, city, and country. The result is shown in the delivery address field so the customer can confirm their location before ordering.  
**Query params:** `latlng`, `key`, `language`  
**Used by:** user app, store app (store setup address picker)

---

### `GET https://maps.googleapis.com/maps/api/place/autocomplete/json`

**When:** Called on every keystroke as the user types in the address search box.  
**What it does:** Returns up to 5 place predictions that match the partial input, each with a `place_id` and display text. The results power the address autocomplete dropdown.  
**Query params:** `input`, `key`, `sessiontoken`, `language`  
**Used by:** user app, store app

---

### `GET https://maps.googleapis.com/maps/api/place/details/json`

**When:** Called when the user taps one of the autocomplete suggestions.  
**What it does:** Fetches the full details for the selected place using its `place_id`: formatted address, GPS coordinates, and address components. The coordinates are then used to pin the delivery location on the map.  
**Query params:** `place_id`, `key`, `language`  
**Used by:** user app, store app

---

## M. Stripe

**Base URL:** `https://api.stripe.com/v1/`  
**Auth:** HTTP Basic with the Stripe secret key

---

### `POST https://api.stripe.com/v1/payment_intents/{id}/confirm`

**When:** Called by the simulator after it has retrieved a payment intent client secret from the LastMile API. In the real user app, this confirmation step is handled by the Stripe SDK internally; the simulator calls it directly to simulate a successful card payment without a real device.  
**What it does:** Confirms and captures the payment for the payment intent. On success, Stripe marks the intent as `succeeded` and the order flow continues to fulfilment.  
**Used by:** simulator

---

## N. Firebase

---

### Firebase Remote Config

**When:** Called at app startup, right after the initial config fetch.  
**What it does:** Fetches server-side feature flags and configuration values (e.g., minimum app version, kill-switch flags, A/B test parameters). The app uses these to enable or disable features without requiring an app store update.  
**Used by:** user app, store app

---

---

# Part 6 — Simulator Internal API

**Purpose:** The simulator is a test orchestration tool that drives the Fainzy last-mile system through automated scenarios (full order flows, store management, payment simulations). It exposes its own management API for running, scheduling, and inspecting simulations.  
**Base path:** `/api/v1/api/v1/`  
**Auth:** JWT Bearer token

---

## O. Simulator Authentication

---

### `POST /api/v1/auth/register`

**When:** Called by an administrator setting up a new simulator instance for the first time, or adding a new team member who needs access to the simulator dashboard.  
**What it does:** Creates an admin user account for the simulator web UI. These accounts are distinct from Fainzy user/store accounts.

---

### `POST /api/v1/auth/login`

**When:** Called when an operator opens the simulator dashboard and submits their credentials.  
**What it does:** Authenticates the operator and returns a JWT access token and a refresh token. The access token is sent with every subsequent simulator API call.

---

### `POST /api/v1/auth/refresh`

**When:** Called automatically by the simulator dashboard client when the JWT access token is about to expire.  
**What it does:** Exchanges a valid refresh token for a new access token, extending the session without requiring a re-login.

---

### `POST /api/v1/auth/logout`

**When:** Called when the operator clicks "Log out" on the simulator dashboard.  
**What it does:** Invalidates the current session tokens server-side.

---

### `GET /api/v1/auth/session` / `GET /api/v1/auth/me`

**When:** Called on dashboard load to restore the session state and display the logged-in operator's name and role.  
**What it does:** Returns the current session validity and the user's profile data.

---

## P. Simulation Runs

A "run" is a single execution of a simulation flow — e.g., one complete end-to-end order from user registration through to delivery.

---

### `GET /api/v1/flows`

**When:** Called when the operator is creating a new run and needs to choose which simulation scenario to execute.  
**What it does:** Returns all available simulation flows (scripts): their names, descriptions, configurable parameters, and expected duration. Each flow maps to a specific test scenario (e.g., "full_order_flow", "store_rejection_scenario").

---

### `POST /api/v1/runs`

**When:** Called when the operator clicks "Start simulation" after selecting a flow and configuring parameters.  
**What it does:** Creates a new run record, queues the selected simulation flow for execution, and returns the run ID. The simulation begins immediately or as soon as a worker is available.

---

### `GET /api/v1/runs` / `GET /api/v1/runs/count`

**When:** Called when the operator opens the Runs list page on the simulator dashboard.  
**What it does:** Returns paginated run records with their statuses (queued, running, completed, failed), start times, and flow types. The count endpoint provides the total for pagination headers.

---

### `GET /api/v1/runs/{id}`

**When:** Called when the operator clicks into a specific run to view its detail page.  
**What it does:** Returns the full run record: flow type, configuration, status, timing, the actors used (simulated user, store, robot), and a summary of outcomes.

---

### `GET /api/v1/runs/{id}/log`

**When:** Called when the operator opens the "Logs" tab on a run detail page, or when monitoring a run in progress.  
**What it does:** Returns the real-time log output from the simulation: step-by-step event descriptions, API calls made, WebSocket messages received, and any assertion failures.

---

### `GET /api/v1/runs/{id}/metrics`

**When:** Called when the operator opens the "Metrics" tab on a completed run.  
**What it does:** Returns quantitative measurements from the run: API response times, WebSocket event latencies, order-to-acceptance time, acceptance-to-delivery time, and any SLA violations detected.

---

### `GET /api/v1/runs/{id}/artifacts/{kind}`

**When:** Called when the operator wants to download a specific output artifact from a run (e.g., a captured HTTP trace, a screenshot, or a generated report).  
**What it does:** Returns the artifact file for the specified kind. The `kind` path segment is a type identifier (e.g., `trace`, `report`, `snapshot`).

---

### `GET /api/v1/runs/{id}/execution-snapshot`

**When:** Called when the operator needs to see the exact state of the simulation at a specific point in time — useful for debugging a failed run.  
**What it does:** Returns a structured snapshot of all relevant state at the time the run stopped: current order status, actor states, active WebSocket connections, and last API responses.

---

### `POST /api/v1/runs/{id}/cancel`

**When:** Called when the operator wants to stop a simulation that is currently running.  
**What it does:** Sends a cancellation signal to the running simulation worker. The run status transitions to `cancelled` and cleanup happens gracefully.

---

### `POST /api/v1/runs/{id}/replay`

**When:** Called when the operator wants to re-run a simulation with the exact same parameters as a previous run — useful for reproducing a failure or re-testing after a fix.  
**What it does:** Creates a new run record that is a copy of the specified run's configuration and launches it immediately.

---

### `DELETE /api/v1/runs/{id}` / `POST /api/v1/runs/{id}/restore`

**When:** Delete is called when the operator removes a run from the active list. Restore is called when an archived run needs to be brought back for inspection.  
**What it does:** Soft-deletes or restores the run record. Deleted runs are accessible in the Archives section.

---

## Q. Run Profiles

A Run Profile is a saved configuration for a simulation run: which flow, which parameters, how many actors. Profiles let operators launch repeat simulations without re-entering settings.

---

### `GET /api/v1/run-profiles` / `POST /api/v1/run-profiles`

**When:** List is called when the operator opens the Profiles page. Create is called when saving a configuration for reuse.  
**What it does:** Returns all saved profiles, or creates a new one.

---

### `PUT /api/v1/run-profiles/{id}` / `DELETE /api/v1/run-profiles/{id}`

**When:** Called when the operator edits or deletes an existing profile.  
**What it does:** Updates or removes the profile record.

---

### `POST /api/v1/run-profiles/{id}/launch`

**When:** Called when the operator clicks "Launch" on a saved profile.  
**What it does:** Creates and immediately starts a new run using the profile's saved configuration. Equivalent to calling `POST /api/v1/runs` but without needing to fill in the form.

---

## R. Simulation Plans

A Simulation Plan defines the actors and scenario parameters for a complex multi-actor simulation (e.g., 5 users, 3 stores, 2 riders running concurrently).

---

### `GET /api/v1/simulation-plans/sim-actors`

**When:** Called when the operator is building a plan and needs to assign actors.  
**What it does:** Returns the pool of available simulation actors — pre-configured user accounts, store accounts, and robot (rider) accounts — that can be assigned to roles in the plan.

---

### `GET /api/v1/simulation-plans` / `POST /api/v1/simulation-plans` / `PUT /api/v1/simulation-plans/{id}` / `DELETE /api/v1/simulation-plans/{id}`

**When:** Called when the operator manages the library of simulation plans.  
**What it does:** Standard CRUD for plan records. Plans are reusable across multiple runs and profiles.

---

## S. Schedules

Schedules allow simulations to run automatically at defined intervals (e.g., every hour, every night at 2 AM) to run continuous regression testing against the live system.

---

### `POST /api/v1/schedules` / `GET /api/v1/schedules`

**When:** Create is called when an operator sets up a new automated schedule. List is called when viewing the Schedules management page.  
**What it does:** Creates a new cron-based schedule linked to a run profile, or returns all existing schedules with their next-run times and statuses.

---

### `POST /api/v1/schedules/{id}/trigger`

**When:** Called when an operator wants to manually fire a scheduled simulation outside its normal time window — e.g., to test immediately after a deployment.  
**What it does:** Immediately executes the schedule's linked profile as if the scheduled time had arrived.

---

### `POST /api/v1/schedules/{id}/pause` / `POST /api/v1/schedules/{id}/resume`

**When:** Called when maintenance is planned or completed and scheduled simulations need to be temporarily stopped and restarted.  
**What it does:** Halts or resumes the schedule without deleting it.

---

### `POST /api/v1/schedules/{id}/disable` / `POST /api/v1/schedules/{id}/delete` / `POST /api/v1/schedules/{id}/restore`

**When:** Called when a schedule is permanently ended, removed, or recovered from archives.  
**What it does:** Transitions the schedule through its archival lifecycle.

---

## T. Orders Proxy (Simulator Dashboard)

The simulator dashboard includes a read/write proxy over the LastMile orders API, giving operators a direct window into the live order system for debugging and manual intervention during simulations.

---

### `GET /api/v1/orders/auto-login`

**When:** Called when the operator opens the Orders panel in the simulator dashboard for the first time in a session.  
**What it does:** Automatically authenticates the simulator against the LastMile API and caches the store token, so the operator does not need to manually log in to each store.

---

### `GET /api/v1/orders/stores` / `POST /api/v1/orders/store-login`

**When:** Called when the operator selects a specific store to inspect in the Orders panel.  
**What it does:** Lists available stores, then authenticates against the selected store's account to enable order management actions on its behalf.

---

### `GET /api/v1/orders/lookup` / `GET /api/v1/orders/list`

**When:** Called when an operator searches for a specific order or browses the full order queue.  
**What it does:** Fetches a single order by reference, or returns a paginated list of orders for the selected store.

---

### `GET /api/v1/orders/store-stats` / `GET /api/v1/orders/customer-stats`

**When:** Called when the operator opens the stats panels in the Orders section.  
**What it does:** Returns aggregate stats for the store (orders today, completion rate) or for individual customers (order frequency, lifetime value).

---

### `GET /api/v1/orders/customers/search`

**When:** Called when the operator types a name or phone number in the customer search box.  
**What it does:** Returns matching customer records from the LastMile system.

---

### `PATCH /api/v1/orders/status`

**When:** Called when an operator manually overrides an order's status during a simulation (e.g., force-completing a stuck order).  
**What it does:** Updates the order status directly via the LastMile API, bypassing the normal store-app flow.

---

## U. GitHub Integration

The simulator integrates with GitHub to trigger simulations automatically on deployment, enabling post-deploy smoke testing.

---

### `POST /api/v1/integrations/github/deployment-complete`

**When:** Called by a GitHub Actions workflow immediately after a successful deployment to staging or production.  
**What it does:** Receives the deployment event payload, matches it against configured integration mappings, and triggers the associated simulation run or schedule. This is the entry point for automated post-deploy testing.

---

### GitHub Mappings (`/api/v1/integrations/github/mappings`)

**When:** Created when an operator wants to link a GitHub repository + environment combination to a specific simulation profile.  
**What it does:** Defines the rule: "when repo X is deployed to environment Y, run simulation profile Z."

---

### GitHub Projects (`/api/v1/integrations/github/projects`)

**When:** Created when a new GitHub repo is onboarded to the simulator integration.  
**What it does:** Registers the GitHub project with the simulator, generates a webhook secret, and returns it for use in the GitHub Actions config.

---

## V. System Configuration & Admin

---

### Timezone settings (`GET/PUT /system/timezones`)

**When:** Called on system settings load and when an operator changes the simulator's timezone.  
**What it does:** Returns or updates the timezone used for schedule calculations and log timestamps.

---

### Email settings (`GET/PUT /system/email`, `POST /api/v1/system/email/test`)

**When:** Called when configuring where the simulator sends alert emails and test run reports.  
**What it does:** Returns or updates SMTP configuration. The test endpoint sends a validation email to confirm the settings work.

---

### Retention settings (`GET/PUT /system/retention`, `GET /api/v1/retention/summary`)

**When:** Called when configuring how long run logs, artifacts, and archived records are kept before automatic purging.  
**What it does:** Returns or updates retention policy (days to keep each type of record). The summary shows current storage usage under the active policy.

---

### Admin Users (`/api/v1/admin/users`)

**When:** Called by a super-admin managing who has access to the simulator dashboard.  
**What it does:** Full CRUD for operator accounts, including password reset.

---

### Alerts (`GET /api/v1/alerts`)

**When:** Called when the simulator dashboard loads the alerts panel, or when a background polling job checks for new issues.  
**What it does:** Returns any active system alerts: failed schedules, simulation error thresholds breached, integration failures, or infrastructure warnings.

---

### Subentities (`GET /api/v1/subentities`, `GET /api/v1/subentities/search`)

**When:** Called when the operator needs to select or look up a specific store within the simulator context — e.g., when building a simulation plan or filtering the Orders panel.  
**What it does:** Lists all subentities the simulator has access to, or searches by name/ID.

---

---

# Appendix A — Authentication Schemes

| Scheme | Header | Used For |
|--------|--------|---------|
| Token auth | `Authorization: Token {token}` | All LastMile Operations API calls |
| Fainzy token | `Fainzy-Token: {token}` | Some Fainzy Core endpoints (store-facing) |
| JWT Bearer | `Authorization: Bearer {jwt}` | Simulator internal API |
| API key (query param) | `key={apiKey}` | Google Maps |
| HTTP Basic | `Authorization: Basic {base64}` | Stripe direct API calls |

---

# Appendix B — Endpoint Count by Backend

| Backend | Approximate Endpoint Count |
|---------|---------------------------|
| Fainzy Core API | ~32 |
| LastMile Operations API | ~27 |
| Web / CMS API | 3 |
| WebSocket channels | 3 |
| Google Maps | 3 |
| Stripe | 1 |
| Simulator Internal API | ~65 |
| **Total** | **~134** |
