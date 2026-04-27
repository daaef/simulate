# Fainzy Last Mile User App - Complete User Journey Walkthrough

> **Layman's Version (Simplified)**
>
> This document is a detailed playbook showing exactly what happens when:
>
> 1. **A brand new customer** downloads the app and orders food for the first time
> 2. **A returning customer** logs back in and orders again
> 3. **Location validation** - when the app checks if we deliver to their location (both when we DO and when we DON'T)
>
> The third scenario is critical: The app checks "Do we deliver here?" by:
> - Getting the user's GPS location (or letting them type an address)
> - Sending that location to our server to check
> - **YES** → Show available stores, let them order
> - **NO** → Show a form: "We'll be there soon! Leave your details and we'll notify you when we expand to your area"
>
> For each step, this document shows:
> - What the user sees and clicks on screen
> - What the app sends to the server (exact data/payloads)
> - What the server sends back (responses)
> - What happens when things go wrong (no GPS, no service, wrong address, etc.)
>
> Includes real example data so developers can test every scenario.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Scenario 1: First-Time User Registration & Order Flow](#2-scenario-1-first-time-user-registration--order-flow)
3. [Scenario 2: Returning User Login & Quick Order](#3-scenario-2-returning-user-login--quick-order)
4. [Scenario 3: Location Validation Edge Cases](#4-scenario-3-location-validation-edge-cases)
5. [Data Models Reference](#5-data-models-reference)
6. [API Contract](#6-api-contract)
7. [State Machines & Events](#7-state-machines--events)
8. [Edge Cases & Error Handling](#8-edge-cases--error-handling)

---

## 1. Architecture Overview

### Tech Stack
- **Framework**: Flutter (Dart)
- **State Management**: Bloc/Cubit pattern
- **HTTP Client**: Dio
- **APIs**: RESTful APIs with Fainzy-Token authentication
- **Payment**: Stripe integration
- **Maps**: Google Maps Flutter
- **Local Storage**: SharedPreferences

### Key Repositories
| Repository | Responsibility |
|------------|--------------|
| `AuthenticationRepository` | OTP, login, registration, token management |
| `SubentityRepository` | Stores, menus, categories, search |
| `OrderRepository` | Order creation, status tracking, history |
| `LocationRepository` | Service area validation, location requests |
| `LocalStorageRepository` | Persist user data, tokens, settings |

### Core Data Flow
```
User Action → Bloc Event → Repository API Call → API Response → 
Bloc State Update → UI Rebuild → User Sees Result
```

---

## 2. Scenario 1: First-Time User Registration & Order Flow

### Phase 1: Phone Number Entry & OTP Request

#### User Action
User opens app and sees phone number input screen.

#### Screen
`EnterPhoneNumberPage`

#### Bloc
`EnterPhoneNumberBloc`

#### Events
```dart
// User types phone number
PhoneNumberChanged(phoneNumber: "+2348012345678")

// User taps submit button
Submitted()
```

#### API Request
```http
POST /v1/auth/request-otp/
Content-Type: application/json

{
  "phone_number": "+2348012345678"
}
```

#### API Response (Success)
```json
{
  "status": "success",
  "message": "OTP sent successfully",
  "data": null
}
```

#### State Transitions
```
Initial → Submitting → Succeeded → Navigate to VerifyPhoneNumberPage
```

#### Error Cases
| Error | Response | UI Behavior |
|-------|----------|-------------|
| Invalid phone format | `{"error": "Invalid phone number format"}` | Show error below input |
| Network failure | Timeout | "Please check your connection" |

---

### Phase 2: OTP Verification

#### User Action
User receives SMS OTP (auto-read or manual entry).

#### Screen
`VerifyPhoneNumberPage`

#### Bloc
`VerifyPhoneNumberCubit`

#### Events
```dart
// Auto-read from SMS
listenForSms() → emits autoReadOtp: "123456"

// User submits OTP (auto or manual)
submitOtp("123456")

// Resend OTP
requestOtp()
```

#### API Request - Verify OTP
```http
POST /v1/auth/verify-otp/
Content-Type: application/json

{
  "phone_number": "+2348012345678",
  "otp": "123456"
}
```

#### API Response - Existing User (Setup Complete)
```json
{
  "status": "success",
  "setup_complete": true,
  "is_active": true,
  "data": {
    "user": {
      "id": 42,
      "first_name": "John",
      "last_name": "Doe",
      "email": "john@example.com",
      "phone_number": "+2348012345678",
      "notification_id": "fcm_token_123"
    },
    "token": "jwt_api_token_xyz789"
  }
}
```

#### API Response - New User (Setup Incomplete)
```json
{
  "status": "success",
  "setup_complete": false,
  "is_active": true,
  "data": null
}
```

#### API Response - Deactivated Account
```json
{
  "status": "success",
  "setup_complete": true,
  "is_active": false,
  "data": null
}
```

#### State Transitions

**New User Flow:**
```
Initial → Submitting → Succeeded (setupComplete: false) → Navigate to SetupAccountPage
```

**Existing User Flow:**
```
Initial → Submitting → Succeeded (setupComplete: true, isActive: true) 
→ authenticateLastMileUser() → Save user & token → Navigate to HomePage
```

**Deactivated Account Flow:**
```
Initial → Submitting → Succeeded (isActive: false) → Show reactivation dialog
```

#### Branching Logic
```dart
if (result.setupComplete == true) {
  if (result.isActive == false) {
    // Show account deactivated, offer reactivation
    emit(state.copyWith(isDeactivated: true));
  } else {
    // Existing active user
    final data = await authenticationRespository.authenticateLastMileUser(phoneNumber: phoneNumber);
    await authenticationRespository.saveUser(data.user!);
    await localStorageRepository.saveLastMileApiToken(data.token!);
    emit(state.copyWith(status: succeeded, user: data.user));
  }
} else {
  // New user - go to account setup
  emit(state.copyWith(status: succeeded));
}
```

---

### Phase 3: Account Setup (New User Only)

#### User Action
User fills registration form with personal details.

#### Screen
`SetupAccountPage`

#### Bloc
`SetupAccountBloc`

#### Events
```dart
// Form field changes
FirstNameChanged(firstName: "John")
LastNameChanged(lastName: "Doe")
EmailChanged(email: "john.doe@example.com")
PasswordChanged(password: "SecurePass123!")

// Toggle password visibility
ToggleShowPassword()

// Submit form
Submitted()
```

#### Form Validation (Input Models)
```dart
// FirstNameInput
- Required
- Min 2 characters
- Only letters and spaces

// LastNameInput  
- Required
- Min 2 characters
- Only letters and spaces

// EmailInput
- Required
- Valid email format (regex)

// PasswordInput
- Required
- Min 8 characters
- At least 1 uppercase, 1 lowercase, 1 number
```

#### API Request
```http
POST /v1/auth/create-user/
Content-Type: application/json

{
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone_number": "+2348012345678",
  "password": "SecurePass123!"
}
```

#### API Response
```json
{
  "status": "success",
  "data": {
    "user": {
      "id": 42,
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone_number": "+2348012345678",
      "notification_id": null
    },
    "token": "jwt_api_token_xyz789"
  }
}
```

#### State Transitions
```
Initial → Form Validated → Submitting → Succeeded 
→ Save token → Navigate to Location Selection
```

#### Demo User Data
```json
{
  "first_name": "John",
  "last_name": "Doe", 
  "email": "john.doe@example.com",
  "phone_number": "+2348012345678",
  "password": "SecurePass123!"
}
```

---

### Phase 4: Location Detection & Service Area Validation (CRITICAL)

#### User Action
User grants GPS permission or manually enters address.

#### Screen
`UseCurrentAddressPage` or `SearchAddressPage`

#### Bloc
`UseCurrentAddressBloc` or `SearchAddressBloc`

---

#### **BRANCH A: GPS Auto-Detection (In Service Area)**

##### Events
```dart
// User taps "Use Current Location"
StartSearching()
```

##### System Actions
```dart
// 1. Get GPS coordinates
position = await LocationHelper.instance.getUserPosition()
// Result: LatLng(6.5244, 3.3792) - Lagos, Nigeria

// 2. Fetch nearby service locations
fetchLocationsByGeo(
  lat: "6.5244",
  lng: "3.3792", 
  radius: 1  // km
)
```

##### API Request
```http
GET /v1/entities/locations/3.3792/6.5244/?search_radius=1
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

##### API Response - Locations Found (In Service Area)
```json
{
  "status": "success",
  "data": [
    {
      "id": 15,
      "name": "Lagos Island Office Complex",
      "floor_number": "3rd Floor",
      "country": "Nigeria",
      "post_code": "101231",
      "state": "Lagos",
      "city": "Lagos",
      "ward": "Lagos Island",
      "village": "",
      "location_type": "office",
      "gps_coordinates": {
        "type": "Point",
        "coordinates": [3.3792, 6.5244]
      },
      "operation_mode": "active",
      "address_details": "123 Marina Road, Lagos Island",
      "is_default": false,
      "is_active": true,
      "service_area": 5
    },
    {
      "id": 16,
      "name": "Victoria Island Mall",
      "floor_number": "Ground Floor",
      "country": "Nigeria",
      "post_code": "101234",
      "state": "Lagos",
      "city": "Lagos", 
      "ward": "Victoria Island",
      "village": "",
      "location_type": "mall",
      "gps_coordinates": {
        "type": "Point",
        "coordinates": [3.4215, 6.4335]
      },
      "operation_mode": "active",
      "address_details": "456 Akin Adesola Street, Victoria Island",
      "is_default": false,
      "is_active": true,
      "service_area": 5
    }
  ]
}
```

##### State Transitions
```
Initial → Searching → ResultsFound
```

##### User Selection
User selects location → `LocationSelected(location)` event

##### Save Location
```dart
settingsBloc.add(LocationChanged(event.location))
localStorageRepository.saveCurrentLocation(location.toJson())
```

##### Navigate To
Home feed showing stores for `service_area: 5`

---

#### **BRANCH B: GPS Auto-Detection (NOT in Service Area)**

##### Events
```dart
StartSearching()
```

##### System Actions
```dart
position = await LocationHelper.instance.getUserPosition()
// Result: LatLng(7.3775, 3.9470) - Ibadan, Nigeria (no service)

fetchLocationsByGeo(
  lat: "7.3775",
  lng: "3.9470",
  radius: 1
)
```

##### API Request
```http
GET /v1/entities/locations/3.9470/7.3775/?search_radius=1
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

##### API Response - No Locations Found
```json
{
  "status": "success",
  "data": []
}
```

##### State Transitions
```
Initial → Searching → NoResultsFound
```

##### UI Behavior
Shows `UserRequestFormSheet` (modal bottom sheet) with message:
> "We Will Soon Be In Your City!"
> "Please fill out this form and you will be the first to know once we are in your area."

##### Location Request Form Fields
| Field | Validation | Demo Value |
|-------|------------|------------|
| Full Name | Required, min 2 chars | "Adebayo Johnson" |
| Email | Valid email format | "adebayo.j@example.com" |
| Nearest Landmark | Required | "University of Ibadan" |
| City | Required | "Ibadan" |
| Country | Required | "Nigeria" |

##### API Request - Submit Location Request
```http
POST /v1/entities/location-requests/
Content-Type: application/json

{
  "full_name": "Adebayo Johnson",
  "email": "adebayo.j@example.com",
  "landmark": "University of Ibadan",
  "city": "Ibadan",
  "country": "Nigeria"
}
```

##### API Response
```json
{
  "status": "success",
  "message": "Location request submitted successfully. We'll notify you when we expand to your area.",
  "data": null
}
```

##### User Flow Blocked
User **CANNOT** proceed to home feed or ordering. Must wait for service expansion.

---

#### **BRANCH C: Manual Address Search (In Service Area)**

##### Events
```dart
// User types in search box
SearchQueryChanged(query: "victoria island lagos")
```

##### System Actions
```dart
// Google Places Autocomplete API
predictionsResponse = await LocationHelper.instance.autoComplete("victoria island lagos")
```

##### Google Places Response
```json
{
  "predictions": [
    {
      "place_id": "ChIJGRlMhCZgThAR3K5SxX9f9tE",
      "description": "Victoria Island, Lagos, Nigeria",
      "structured_formatting": {
        "main_text": "Victoria Island",
        "secondary_text": "Lagos, Nigeria"
      }
    },
    {
      "place_id": "ChIJZ3f9ltxgThARzFqTnX9j9oQ",
      "description": "Eko Hotel, Victoria Island, Lagos",
      "structured_formatting": {
        "main_text": "Eko Hotel",
        "secondary_text": "Victoria Island, Lagos, Nigeria"
      }
    }
  ]
}
```

##### User Selection
User selects prediction → Get place details (lat/lng)

##### API Call
```http
GET /v1/entities/locations/3.4215/6.4335/?search_radius=1
```

##### Result
Same as Branch A - locations found in service area.

---

#### **BRANCH D: Manual Address Search (NOT in Service Area)**

Same flow as Branch B - shows request form when no service locations found.

---

### Phase 5: Home Feed & Store Discovery

#### Screen
`HomeFeedPage`

#### Bloc
`HomeFeedBloc`

#### Prerequisites
```dart
// Service area from selected location
serviceArea = settingsBloc.state.selectedLocation!.serviceArea!  // 5
```

#### Events
```dart
// Initial load
FetchData()

// Search stores
SearchStores(query: "chicken")

// Clear search
ClearSearch()

// Tab selection (All vs Discount)
SelectTab(tabIndex: 1)
```

#### API Request - Fetch Stores
```http
GET /v1/entities/subentities/service-area/5/
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

#### API Response
```json
{
  "status": "success",
  "data": [
    {
      "subentity": {
        "id": 23,
        "name": "Bukka Hut",
        "branch": "Victoria Island",
        "image": {
          "id": 45,
          "upload": "https://cdn.fainzy.com/media/bukka_hut_logo.jpg"
        },
        "mobile_number": "+23480111222333",
        "gps_coordinates": {
          "type": "Point",
          "coordinates": [3.4215, 6.4335]
        },
        "rating": 4.5,
        "total_reviews": 128,
        "status": 1,
        "address": {
          "street": "234 Adeola Odeku Street",
          "city": "Lagos",
          "state": "Lagos",
          "country": "Nigeria"
        },
        "description": "Authentic Nigerian cuisine delivered fast",
        "start_time": "08:00",
        "closing_time": "22:00",
        "opening_days": "Mon-Sun",
        "currency": "NGN"
      }
    },
    {
      "subentity": {
        "id": 24,
        "name": "Sweet Sensation",
        "branch": "Lekki Phase 1",
        "image": {
          "id": 46,
          "upload": "https://cdn.fainzy.com/media/sweet_sensation_logo.jpg"
        },
        "mobile_number": "+23480444555666",
        "gps_coordinates": {
          "type": "Point", 
          "coordinates": [3.4783, 6.4386]
        },
        "rating": 4.2,
        "total_reviews": 89,
        "status": 1,
        "address": {
          "street": "12 Fola Osibo Street",
          "city": "Lagos",
          "state": "Lagos", 
          "country": "Nigeria"
        },
        "description": "Delicious pastries and quick meals",
        "start_time": "07:00",
        "closing_time": "21:00",
        "opening_days": "Mon-Sat",
        "currency": "NGN"
      }
    }
  ]
}
```

#### State Transitions
```
Initial → Fetching → ResultsFound (stores: [FainzyRestaurant])
```

#### Store Display
Each store card shows:
- Logo image
- Name + Branch
- Rating stars + review count
- Opening hours
- Distance (calculated from GPS)

---

### Phase 6: Store Selection & Menu Browsing

#### Screen
`StorePage`

#### Bloc
`StoreBloc`, `StoreItemBloc`

#### User Action
User taps on "Bukka Hut" store.

#### Events - Store Loading
```dart
// Load store data
FetchItems()
```

#### API Request - Fetch Categories
```http
GET /v1/entities/subentities/23/categories/
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

#### API Response - Categories
```json
{
  "status": "success",
  "data": [
    {"id": 1, "name": "All"},
    {"id": 2, "name": "Rice Dishes"},
    {"id": 3, "name": "Soups & Swallows"},
    {"id": 4, "name": "Proteins"},
    {"id": 5, "name": "Drinks"}
  ]
}
```

#### API Request - Fetch Menu Items
```http
GET /v1/entities/subentities/23/menus/
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

#### API Response - Menu Items
```json
{
  "status": "success",
  "data": [
    {
      "id": 101,
      "category": 2,
      "subentity": 23,
      "name": "Jollof Rice & Chicken",
      "price": 3500.00,
      "description": "Smoky party jollof rice with grilled chicken leg",
      "currency_symbol": "₦",
      "ingredients": "Rice, tomatoes, peppers, chicken, spices",
      "discount": 10.0,
      "discount_price": 3150.00,
      "status": "available",
      "images": [
        {
          "id": 201,
          "upload": "https://cdn.fainzy.com/media/jollof_rice_1.jpg"
        }
      ],
      "created": "2024-01-15T10:30:00Z",
      "modified": "2024-03-20T14:22:00Z"
    },
    {
      "id": 102,
      "category": 3,
      "subentity": 23,
      "name": "Egusi Soup & Pounded Yam",
      "price": 4500.00,
      "description": "Rich melon seed soup with assorted meat and smooth pounded yam",
      "currency_symbol": "₦",
      "ingredients": "Egusi seeds, palm oil, spinach, beef, goat meat, pounded yam",
      "discount": null,
      "discount_price": null,
      "status": "available",
      "images": [
        {
          "id": 202,
          "upload": "https://cdn.fainzy.com/media/egusi_soup_1.jpg"
        }
      ],
      "created": "2024-01-15T11:00:00Z",
      "modified": "2024-03-19T09:15:00Z"
    }
  ]
}
```

#### UI Structure
- Collapsible header with store image carousel
- Store info card (rating, hours, phone)
- Google Map with store location marker
- Sticky category tabs
- Menu item grid/list

---

### Phase 7: Menu Item Selection & Cart Building

#### Screen
Menu item detail modal/bottom sheet

#### Bloc
`StoreItemBloc`

#### User Action
User taps on "Jollof Rice & Chicken" → Opens item details.

#### Events
```dart
// Initialize item
Initialise()

// Change quantity
IncrementQuantity()  // quantity: 1 → 2
DecrementQuantity()  // quantity: 2 → 1 (min: 1)

// Toggle side items
ToggleSideItem(id: 501)  // Add extra plantain (+₦500)
ToggleSideItem(id: 502)  // Add coleslaw (+₦300)

// Add to cart
AddToCart(context)
```

#### Side Items API Request
```http
GET /v1/entities/subentities/23/menus/101/sides/
Headers: {
  "Fainzy-Token": "jwt_api_token_xyz789"
}
```

#### Side Items API Response
```json
{
  "status": "success",
  "data": [
    {
      "id": 501,
      "name": "Extra Plantain",
      "price": 500.00,
      "is_default": false
    },
    {
      "id": 502,
      "name": "Coleslaw",
      "price": 300.00,
      "is_default": false
    },
    {
      "id": 503,
      "name": "Moi Moi",
      "price": 400.00,
      "is_default": true
    }
  ]
}
```

#### Price Calculation
```dart
// Base calculations
basePrice = menu.discountPrice ?? menu.price  // 3150 (with discount)
quantity = 2
selectedSides = [Extra Plantain (500), Coleslaw (300)]

// Total calculation
totalPrice = (basePrice + sidePrices) * quantity
totalPrice = (3150 + 500 + 300) * 2 = 3950 * 2 = ₦7,900
```

#### Add to Cart Event
```dart
cartBloc.add(AddItemToCart(
  item: FainzyCartItem.fromMenu(
    menu: jollofRiceMenu,
    price: 3950.00,  // Includes sides
    quantity: 2,
    sides: [
      FainzySides(id: 501, title: "Extra Plantain", price: 500, isDefault: false, isSelected: true),
      FainzySides(id: 502, title: "Coleslaw", price: 300, isDefault: false, isSelected: true)
    ]
  ),
  store: bukkaHutRestaurant,
  context: context
))
```

#### Cart State Update (`AllCartsBloc`)
```dart
// Cart structure
Map<int, CartModel> carts = {
  23: CartModel(
    id: 23,
    store: bukkaHutRestaurant,
    items: {
      101: FainzyCartItem(
        id: "uuid-v1-string",
        menuId: 101,
        menu: jollofRiceMenu,
        quantity: 2,
        price: 3950.00,
        sides: [extraPlantain, coleslaw]
      )
    },
    totalValueOfItems: 7900.00
  )
}
```

#### Toast Notification
> "Jollof Rice & Chicken added to cart"

---

### Phase 8: Cart Review & Checkout Initiation

#### Screen
`StoreCartPage`

#### Bloc
`AllCartsBloc`

#### User Action
User taps cart icon → Reviews items → Taps "Checkout".

#### Cart Page Components
- Store details header
- List of cart items with:
  - Item image
  - Name + sides
  - Quantity controls (+/-)
  - Price per item
  - Swipe to delete
- Total summary
- Checkout button

#### Events
```dart
// Increment item in cart
IncrementItemQuantity(item, store)

// Decrement item in cart
DecrementItemQuantity(item, store)

// Remove item from cart
RemoveItemFromCart(item, store)

// Clear entire store cart
ClearCart(storeId: 23)
```

#### Checkout Button Action
```dart
OrderFlowTraceRecorder.instance.record(
  stage: 'checkout_started',
  trigger: 'StoreCartPage.CheckoutButton.onPressed',
  summary: 'User tapped checkout from the store cart.',
  actor: 'user',
  appDecision: 'Navigate to CheckoutPage with cart.',
  requestPayload: {
    'store': store.toMap(),
    'cart_total': 7900.00,
    'item_count': 1,
    'items': [cartItem.toMap()]
  }
)

// Navigate to checkout
AppRouter.navigatorKey.currentState!.pushNamed(
  Routes.routeCheckout,
  arguments: cart,
)
```

---

### Phase 9: Checkout & Order Placement

#### Screen
`CheckoutPage`

#### Bloc
`CheckoutBloc`

#### Initialization Events
```dart
// Load order costs (fees)
LoadOrderCosts("NGN")

// Load saved payment cards
LoadSavedCards()
```

#### API Request - Load Order Costs
```http
GET /v1/core/pricing/?currency=NGN
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

#### API Response - Order Costs
```json
{
  "status": "success",
  "data": {
    "delivery_percentage": 500.00,
    "service_percentage": 5.0
  }
}
```

#### Fee Calculation
```dart
totalValueOfItems = 7900.00
deliveryFee = 500.00  // Fixed value (not percentage)
serviceFee = (5.0 / 100) * 7900.00 = 395.00
couponDiscount = 0.00

total = 7900.00 + 500.00 + 395.00 - 0.00 = ₦8,795.00
```

#### Checkout Page Sections
1. **Delivery Location Selector**
   - Current saved location
   - Option to change location

2. **Order Summary**
   - Itemized list
   - Subtotal
   - Service fee
   - Delivery fee
   - Discount (if coupon applied)
   - **Total**

3. **Coupon Section**
   - "Have a coupon code?" input
   - Apply button
   - Available coupons list

4. **Payment Method**
   - Saved cards (if any)
   - "Pay with new card" option

#### Apply Coupon Events
```dart
// Select coupon
SelectCoupon(couponData: CouponData)

// Remove coupon
RemoveCoupon()
```

#### API Request - Load Coupons
```http
GET /v1/core/coupons/
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

#### API Response - Coupons
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "code": "WELCOME20",
      "config_details": {
        "is_percentage": true,
        "discount": 20.0
      }
    },
    {
      "id": 2,
      "code": "FLAT500",
      "config_details": {
        "is_percentage": false,
        "discount": 500.0
      }
    }
  ]
}
```

#### Place Order Event
```dart
// User taps "Place Order"
Checkout(
  deliveryLocation: selectedLocation,
  userId: 42
)
```

#### Order Generation
```dart
FainzyOrderModel generateOrder(int userId, FainzyLocation location) {
  return FainzyOrderModel(
    orderId: '#123456',  // Random 6 digits
    restaurant: cart.store,
    user: userId,
    deliveryLocation: location,
    menu: cart.items.values.toList(),
    status: 'pending',
    totalPrice: cart.totalValueOfItems,
  );
}
```

#### Generated Order Payload
```json
{
  "order_id": "#123456",
  "restaurant": {
    "id": 23,
    "name": "Bukka Hut",
    "branch": "Victoria Island",
    "address": {
      "street": "234 Adeola Odeku Street",
      "city": "Lagos",
      "state": "Lagos",
      "country": "Nigeria"
    },
    "gps_coordinates": {
      "type": "Point",
      "coordinates": [3.4215, 6.4335]
    },
    "currency": "NGN"
  },
  "location": {
    "id": 15,
    "name": "Lagos Island Office Complex",
    "address_details": "123 Marina Road, Lagos Island",
    "gps_coordinates": {
      "type": "Point",
      "coordinates": [3.3792, 6.5244]
    },
    "service_area": 5
  },
  "menu": [
    {
      "id": "uuid-v1-string",
      "menuId": 101,
      "menu": {
        "id": 101,
        "name": "Jollof Rice & Chicken",
        "price": 3500.00,
        "discount_price": 3150.00
      },
      "quantity": 2,
      "price": 3950.00,
      "sides": [
        {"id": 501, "name": "Extra Plantain", "price": 500.00},
        {"id": 502, "name": "Coleslaw", "price": 300.00}
      ]
    }
  ],
  "total_price": 7900.00,
  "status": "pending",
  "user": 42
}
```

#### API Request - Place Order
```http
POST /v1/core/orders/
Content-Type: application/json
Authorization: Bearer jwt_api_token_xyz789

{
  "order_id": "#123456",
  "restaurant": {...},
  "location": {...},
  "menu": [...],
  "total_price": 7900.00,
  "status": "pending",
  "user": 42
}
```

#### API Response - Order Created
```json
{
  "status": "success",
  "data": {
    "id": 789,
    "order_id": "#123456",
    "code": null,
    "restaurant": {
      "id": 23,
      "name": "Bukka Hut",
      "branch": "Victoria Island",
      "address": {...},
      "gps_coordinates": {...},
      "currency": "NGN"
    },
    "location": {
      "id": 15,
      "name": "Lagos Island Office Complex",
      "address_details": "123 Marina Road, Lagos Island",
      "gps_coordinates": {...}
    },
    "menu": [
      {
        "id": "uuid-string",
        "quantity": 2,
        "price": 3950.00,
        "menu": {
          "id": 101,
          "name": "Jollof Rice & Chicken",
          "price": 3500.00
        },
        "sides": [...]
      }
    ],
    "total_price": 7900.00,
    "coupon_discount": 0.00,
    "delivery_fee": 500.00,
    "service_fee": 395.00,
    "status": "pending",
    "user": {
      "id": 42,
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone_number": "+2348012345678"
    },
    "created": "2024-04-27T14:30:00Z",
    "modified": "2024-04-27T14:30:00Z",
    "estimated_eta": 45.0
  }
}
```

#### State Transitions
```
Idle → Submitting → SentToStore → Navigate to WaitingForStoreToAcceptPage
```

---

### Phase 10: Store Acceptance & Payment

#### Screen
`WaitingForStoreToAcceptOrderPage`

#### Bloc
`CheckoutBloc` (continues)

#### Events
```dart
// Poll for store acceptance
WaitForStoreToAccept()

// Check acceptance status (internal polling)
RunCheckStoreAcceptedOrder(orderId: 789)
```

#### Polling Logic
```dart
// Every 5 seconds, check order status
Timer.periodic(Duration(seconds: 5), (timer) async {
  final order = await orderRepository.fetchOrder(orderId: 789);
  
  if (order.status == 'accepted') {
    timer.cancel();
    add(StoreAccepted(order));
  } else if (order.status == 'rejected') {
    timer.cancel();
    add(StoreRejected());
  }
  // Continue polling if still 'pending'
});
```

#### **BRANCH A: Store Accepts Order**

##### API Request - Check Order Status
```http
GET /v1/core/orders/789/
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

##### API Response - Order Accepted
```json
{
  "status": "success",
  "data": {
    "id": 789,
    "order_id": "#123456",
    "status": "accepted",
    "restaurant": {...},
    "total_price": 7900.00,
    "delivery_fee": 500.00,
    "service_fee": 395.00,
    "estimated_eta": 45.0
  }
}
```

##### State Transition
```
SentToStore → OrderAccepted
```

##### Payment Flow
```dart
// If total > 0
MakePayment() → Stripe payment sheet

// If total == 0 (free order)
PlaceFreeOrder() → completeFreeOrder()
```

##### API Request - Complete Free Order
```http
POST /v1/core/orders/789/complete-free/
Content-Type: application/json
Authorization: Bearer jwt_api_token_xyz789

{
  "amount": 0.00,
  "currency": "NGN",
  "store_id": 23
}
```

##### API Response
```json
{
  "status": "success",
  "message": "Free order completed successfully"
}
```

##### State Transition
```
OrderAccepted → PaymentDone → Navigate to PaymentSuccessPage
```

#### **BRANCH B: Store Rejects Order**

##### API Response - Order Rejected
```json
{
  "status": "success",
  "data": {
    "id": 789,
    "order_id": "#123456",
    "status": "rejected",
    "restaurant": {...}
  }
}
```

##### State Transition
```
SentToStore → OrderRejected
```

##### UI Behavior
- Show "Store rejected your order" message
- Offer options:
  - Try again (resubmit order)
  - Choose different store
  - Cancel and go home

---

### Phase 11: Order Tracking

#### Screen
`OrderDetailsPage`

#### Bloc
`OrderDetailsBloc`

#### Events
```dart
// Initial load
FetchOrder()

// Refresh
FetchOrder()  // Pull to refresh

// User actions
CancelOrder()
TrackOrder()
```

#### API Request - Fetch Order Details
```http
GET /v1/core/orders/789/
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

#### Order Status Lifecycle
```
pending → accepted → payment_processing → preparing → ready → completed
    ↓
rejected (terminal)
    ↓
cancelled (terminal)
```

#### Status Descriptions
| Status | Meaning | UI Indicator |
|--------|---------|--------------|
| `pending` | Waiting for store to accept | Yellow spinner + "Waiting for store..." |
| `accepted` | Store accepted, payment pending | Green check + "Proceed to payment" |
| `payment_processing` | Payment in progress | Spinner + "Processing payment..." |
| `preparing` | Store preparing order | Chef icon + "Preparing your food" |
| `ready` | Order ready for delivery/pickup | Package icon + "Ready!" |
| `completed` | Order delivered/completed | Green check + "Enjoy your meal!" |
| `rejected` | Store rejected order | Red X + "Store unavailable" |
| `cancelled` | User or system cancelled | Grey icon + "Order cancelled" |

#### Order Details Display
- Order ID with copy button
- Store name + branch
- Delivery address
- Order creation time
- Itemized menu list
- Price breakdown:
  - Subtotal
  - Service fee
  - Delivery fee
  - Discount
  - **Total paid**

---

## 3. Scenario 2: Returning User Login & Quick Order

### Phase 1: Quick Authentication

#### Differences from New User
- Skip account setup form
- Use `authenticateLastMileUser()` instead of `createLastMileUser()`

#### API Request
```http
POST /v1/auth/authenticate/
Content-Type: application/json

{
  "phone_number": "+2348012345678"
}
```

#### API Response
```json
{
  "status": "success",
  "data": {
    "user": {
      "id": 42,
      "first_name": "John",
      "last_name": "Doe",
      "email": "john.doe@example.com",
      "phone_number": "+2348012345678",
      "notification_id": "fcm_token_123"
    },
    "token": "jwt_api_token_xyz789"
  }
}
```

### Phase 2: Pre-filled Data Loading

#### Auto-Load Saved Location
```dart
// App startup
final savedLocation = await localStorageRepository.fetchCurrentLocation();
if (savedLocation != null) {
  final location = FainzyLocation.fromJson(savedLocation);
  settingsBloc.add(LocationChanged(location));
}
```

#### Auto-Navigate
```dart
// Skip location selection if valid saved location exists
if (settingsBloc.state.selectedLocation != null) {
  appBloc.add(AppCanStart());
  // Navigate to HomePage
}
```

### Phase 3: Quick Reorder

#### Screen
`OrdersPage` (Order History)

#### Events
```dart
// Load order history
LoadOrders()
```

#### API Request
```http
GET /v1/core/orders/?user_id=42
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

#### Reorder Event
```dart
// User taps "Reorder" on past order
ReOrder(orderId: 789)
```

#### API Request - Reorder
```http
GET /v1/core/orders/789/reorder/
Headers: {
  "Authorization": "Bearer jwt_api_token_xyz789"
}
```

#### API Response - Previous Menu Items
```json
{
  "status": "success",
  "data": [
    {
      "id": 101,
      "name": "Jollof Rice & Chicken",
      "price": 3500.00,
      "description": "Smoky party jollof rice with grilled chicken leg"
    }
  ]
}
```

#### System Action
```dart
// Add all items to cart with default sides
for (final menu in previousItems) {
  cartBloc.add(AddItemToCart(
    item: FainzyCartItem.fromMenu(
      menu: menu,
      price: menu.price,
      quantity: 1,
      sides: []  // Default sides only
    ),
    store: previousStore,
    context: context
  ));
}
```

---

## 4. Scenario 3: Location Validation Edge Cases

### Case A: GPS Permission Denied

#### User Action
User denies location permission when prompted.

#### System Response
```dart
// Permission denied
try {
  position = await LocationHelper.instance.getUserPosition();
} catch (e) {
  // Show manual search option
  emit(state.copyWith(
    status: UseCurrentAddressStatus.permissionDenied
  ));
}
```

#### UI Behavior
- Show "Location permission denied" message
- Provide "Search address manually" button
- Navigate to `SearchAddressPage`

### Case B: Radius Expansion Search

#### User Action
User increases search radius to find nearby service areas.

#### Events
```dart
ApplyRadius(radius: 5)  // 5km
```

#### API Request
```http
GET /v1/entities/locations/3.3792/6.5244/?search_radius=5
```

#### State Transition
```
NoResultsFound(radius: 1) → Searching(radius: 5) → ResultsFound
```

### Case C: Saved Location Service Area Expired

#### Scenario
User had saved location, but service area is temporarily unavailable.

#### API Response - Empty Store List
```json
{
  "status": "success",
  "data": []
}
```

#### UI Behavior
- Home feed shows "No stores available in your area"
- Offer to:
  - Check different location
  - View service area status
  - Contact support

### Case D: Location Request Form Validation

#### Validation Rules
| Field | Rule | Error Message |
|-------|------|---------------|
| Full Name | Required, min 2 chars | "Please enter your full name" |
| Email | Valid email format | "Please enter a valid email" |
| Landmark | Required | "Please enter a landmark" |
| City | Required | "Please enter your city" |
| Country | Required | "Please enter your country" |

#### Submit State
```dart
UserRequestFormState(
  status: submitting | succeeded | failed,
  fullname: TextInput(value: "Adebayo Johnson"),
  email: EmailInput(value: "adebayo.j@example.com"),
  landmark: TextInput(value: "University of Ibadan"),
  city: TextInput(value: "Ibadan"),
  country: TextInput(value: "Nigeria"),
  canSubmit: true  // All fields valid
)
```

---

## 5. Data Models Reference

### 5.1 User Models

#### `FainzyUser`
```dart
class FainzyUser {
  final int? id;                    // 42
  final String? firstName;          // "John"
  final String? lastName;           // "Doe"
  final String? email;              // "john.doe@example.com"
  final String? password;           // "SecurePass123!" (registration only)
  final String? phoneNumber;        // "+2348012345678"
  final String? notificationId;     // "fcm_token_123"
}
```

#### `CreateUserResult`
```dart
class CreateUserResult {
  final String? token;              // "jwt_api_token_xyz789"
  final FainzyUser? user;           // User object
}
```

### 5.2 Location Models

#### `FainzyLocation`
```dart
class FainzyLocation {
  int? id;                          // 15
  DateTime? created;                // 2024-01-15T10:30:00Z
  DateTime? modified;               // 2024-03-20T14:22:00Z
  String? name;                     // "Lagos Island Office Complex"
  String? floorNumber;              // "3rd Floor"
  String? country;                  // "Nigeria"
  String? postCode;                 // "101231"
  String? state;                    // "Lagos"
  String? city;                     // "Lagos"
  String? ward;                     // "Lagos Island"
  String? village;                  // ""
  String? locationType;             // "office"
  GpsCordinates? gpsCoordinates;    // {type: "Point", coordinates: [3.3792, 6.5244]}
  String? operationMode;            // "active"
  String? addressDetails;           // "123 Marina Road, Lagos Island"
  bool? isDefault;                // false
  bool? isActive;                   // true
  int? serviceArea;                 // 5 (CRITICAL for store fetching)
}
```

#### `GpsCordinates`
```dart
class GpsCordinates {
  String? type;                     // "Point"
  List<double>? coordinates;          // [longitude, latitude] = [3.3792, 6.5244]
}
```

### 5.3 Store Models

#### `FainzyRestaurant`
```dart
class FainzyRestaurant {
  final int? id;                    // 23
  final String? name;               // "Bukka Hut"
  final String? branch;             // "Victoria Island"
  final FainzyImage? image;         // Logo image
  final List<FainzyImage>? carouselUploads;  // Store photos
  final String? mobileNumber;       // "+23480111222333"
  final GpsCordinates? gpsCordinates; // Location
  final double? rating;             // 4.5
  final double? totalReviews;       // 128
  final bool isOpen;                // true (status == 1)
  final Address? address;           // Full address object
  final String? description;        // "Authentic Nigerian cuisine"
  final String? startTime;          // "08:00"
  final String? closingTime;        // "22:00"
  final String? openingDays;        // "Mon-Sun"
  final int? status;                // 1 (open), 0 (closed)
  final String? currency;           // "NGN"
}
```

#### `Address`
```dart
class Address {
  final String? street;             // "234 Adeola Odeku Street"
  final String? city;               // "Lagos"
  final String? state;                // "Lagos"
  final String? country;            // "Nigeria"
}
```

### 5.4 Menu Models

#### `FainzyMenu`
```dart
class FainzyMenu {
  final int? id;                    // 101
  final int? category;              // 2 (Rice Dishes)
  final int? subentity;             // 23 (Bukka Hut)
  final List<FainzySides>? sides;   // Available extras
  final String? name;               // "Jollof Rice & Chicken"
  final double? price;              // 3500.00
  final String? description;        // "Smoky party jollof rice..."
  final dynamic currencySymbol;     // "₦"
  final String? ingredients;        // "Rice, tomatoes, peppers..."
  final double? discount;           // 10.0 (percentage)
  final String? status;             // "available" | "sold_out"
  final double? discountPrice;      // 3150.00 (calculated)
  final List<FainzyImage>? images;   // Food photos
  final String? created;            // "2024-01-15T10:30:00Z"
  final String? modified;           // "2024-03-20T14:22:00Z"
}
```

#### `FainzySides`
```dart
class FainzySides {
  final int? id;                    // 501
  final String? title;              // "Extra Plantain"
  final double? price;              // 500.00
  final bool? isDefault;            // false (user must select)
  final bool isSelected;            // true (user selected)
}
```

#### `FainzyCategory`
```dart
class FainzyCategory {
  final int? id;                    // 2
  final String? name;               // "Rice Dishes"
}
```

### 5.5 Cart Models

#### `CartModel`
```dart
class CartModel {
  final int id;                     // 23 (store ID)
  final FainzyRestaurant store;     // Store object
  final Map<int, FainzyCartItem> items;  // {menuId: cartItem}
  final double totalValueOfItems;   // 7900.00
}
```

#### `FainzyCartItem`
```dart
class FainzyCartItem {
  final String? id;                 // "uuid-v1-string"
  final int? menuId;                // 101
  final FainzyMenu? menu;           // Full menu object
  final int? quantity;              // 2
  final double? price;              // 3950.00 (includes sides)
  final List<FainzySides>? sides;   // Selected sides
  
  double get cost => (price ?? 0) * (quantity ?? 0);  // 7900.00
}
```

### 5.6 Order Models

#### `FainzyOrderModel` (Request)
```dart
class FainzyOrderModel {
  final String? orderId;            // "#123456"
  final FainzyRestaurant? restaurant;
  final FainzyLocation? deliveryLocation;
  final List<FainzyCartItem>? menu;
  final double? totalPrice;         // 7900.00
  final String? status;             // "pending"
  final int? user;                  // 42
  final DateTime? updated;
  final DateTime? cancellationTime;
  final DateTime? created;
}
```

#### `FainzyUserOrder` (Response)
```dart
class FainzyUserOrder {
  final int? id;                    // 789 (database ID)
  final String? orderId;            // "#123456"
  final String? code;               // null
  final FainzyRestaurant? restaurant;
  final FainzyLocation? deliveryLocation;
  final List<FainzyCartItem>? menu;
  final double? totalPrice;         // 7900.00
  final double? couponDiscount;     // 0.00
  final double? deliveryFee;        // 500.00
  final num? serviceFee;            // 395.00
  final String? status;             // "pending" | "accepted" | "payment_processing" | "preparing" | "ready" | "completed" | "rejected" | "cancelled"
  final FainzyUser? user;
  final DateTime? updated;
  final DateTime? cancellationTime;
  final DateTime? created;
  final double? estimatedEta;       // 45.0 (minutes)
}
```

### 5.7 Payment Models

#### `SavedCard`
```dart
class SavedCard {
  final String? id;                 // "card_xyz123"
  final CardDetails? card;          // Card info
}

class CardDetails {
  final String? brand;              // "visa" | "mastercard"
  final String? last4;              // "4242"
  final int? expMonth;              // 12
  final int? expYear;               // 2027
}
```

#### `CouponData`
```dart
class CouponData {
  final int? id;                    // 1
  final String? code;               // "WELCOME20"
  final CouponConfig? configDetails;
}

class CouponConfig {
  final bool? isPercentage;         // true
  final double? discount;           // 20.0
}
```

---

## 6. API Contract

### 6.1 Authentication Endpoints

#### Request OTP
```
POST /v1/auth/request-otp/
Body: {"phone_number": "+2348012345678"}
Success: 200 OK
Error: 400 Bad Request (invalid format)
```

#### Verify OTP
```
POST /v1/auth/verify-otp/
Body: {"phone_number": "+2348012345678", "otp": "123456"}
Success: 200 OK + user data if setup_complete
Error: 400 Bad Request (invalid OTP)
```

#### Create User
```
POST /v1/auth/create-user/
Body: {
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "phone_number": "+2348012345678",
  "password": "SecurePass123!"
}
Success: 201 Created + user + token
Error: 400 Bad Request (validation errors)
```

#### Authenticate User
```
POST /v1/auth/authenticate/
Body: {"phone_number": "+2348012345678"}
Success: 200 OK + user + token
Error: 404 Not Found (user doesn't exist)
```

### 6.2 Location Endpoints

#### Fetch Locations by Geo
```
GET /v1/entities/locations/{lng}/{lat}/?search_radius={km}
Headers: Fainzy-Token: {token}
Success: 200 OK + array of locations
Empty: 200 OK + [] (not in service area)
```

#### Submit Location Request
```
POST /v1/entities/location-requests/
Body: {
  "full_name": "Adebayo Johnson",
  "email": "adebayo.j@example.com",
  "landmark": "University of Ibadan",
  "city": "Ibadan",
  "country": "Nigeria"
}
Success: 201 Created
```

### 6.3 Store/Menu Endpoints

#### Fetch Subentities (Stores)
```
GET /v1/entities/subentities/service-area/{service_area_id}/
Headers: Fainzy-Token: {token}
Success: 200 OK + array of stores
```

#### Search Items
```
GET /v1/entities/search/?query={search_term}&service_area={service_area_id}
Headers: Fainzy-Token: {token}
Success: 200 OK + search results
```

#### Fetch Categories
```
GET /v1/entities/subentities/{subentity_id}/categories/
Headers: Fainzy-Token: {token}
Success: 200 OK + categories
```

#### Fetch Menus
```
GET /v1/entities/subentities/{subentity_id}/menus/
Headers: Fainzy-Token: {token}
Success: 200 OK + menu items
```

#### Fetch Sides
```
GET /v1/entities/subentities/{subentity_id}/menus/{menu_id}/sides/
Headers: Fainzy-Token: {token}
Success: 200 OK + side items
```

### 6.4 Order Endpoints

#### Place Order
```
POST /v1/core/orders/
Headers: Authorization: Bearer {token}
Body: FainzyOrderModel JSON
Success: 201 Created + order object
Error: 400 Bad Request (validation)
Error: 402 Payment Required (payment failed)
```

#### Fetch Order
```
GET /v1/core/orders/{order_id}/
Headers: Authorization: Bearer {token}
Success: 200 OK + order object
```

#### Fetch User Orders
```
GET /v1/core/orders/?user_id={user_id}
Headers: Authorization: Bearer {token}
Success: 200 OK + array of orders
```

#### Reorder
```
GET /v1/core/orders/{order_id}/reorder/
Headers: Authorization: Bearer {token}
Success: 200 OK + array of menu items
```

#### Complete Free Order
```
POST /v1/core/orders/{order_id}/complete-free/
Headers: Authorization: Bearer {token}
Body: {"amount": 0, "currency": "NGN", "store_id": 23}
Success: 200 OK
```

#### Update Order Status
```
PATCH /v1/core/orders/{order_id}/
Headers: Authorization: Bearer {token}
Body: {"status": "cancelled"}
Success: 200 OK
```

### 6.5 Pricing Endpoints

#### Load Order Costs
```
GET /v1/core/pricing/?currency={currency}
Headers: Authorization: Bearer {token}
Success: 200 OK + {delivery_percentage, service_percentage}
```

#### Load Coupons
```
GET /v1/core/coupons/
Headers: Authorization: Bearer {token}
Success: 200 OK + array of coupons
```

### 6.6 Payment Endpoints (Stripe Integration)

#### Create Payment Intent
```
POST /v1/core/payments/create-intent/
Headers: Authorization: Bearer {token}
Body: {"amount": 879500, "currency": "NGN", "order_id": 789}
Success: 200 OK + {client_secret, payment_intent_id}
```

#### Confirm Payment
```
POST /v1/core/payments/confirm/
Headers: Authorization: Bearer {token}
Body: {"payment_intent_id": "pi_xyz123"}
Success: 200 OK
```

#### Load Saved Cards
```
GET /v1/core/payments/saved-cards/
Headers: Authorization: Bearer {token}
Success: 200 OK + array of cards
```

---

## 7. State Machines & Events

### 7.1 EnterPhoneNumberBloc

#### States
```dart
enum EnterPhoneNumberStatus { initial, submitting, succeeded, failed }

class EnterPhoneNumberState {
  final PhoneNumberInput phoneNumber;
  final EnterPhoneNumberStatus status;
  final String? error;
}
```

#### Events
```dart
PhoneNumberChanged({required String phoneNumber})
Submitted()
```

#### State Transitions
```
Initial(phoneNumber: "") 
  → PhoneNumberChanged("+2348012345678") 
  → Initial(phoneNumber: "+2348012345678", valid: true)
  → Submitted()
  → Submitting()
  → Succeeded() / Failed(error: "Invalid phone")
```

### 7.2 VerifyPhoneNumberCubit

#### States
```dart
enum VerifyPhoneNumberStatus { initial, submitting, succeeded, failed, editing }
enum RequestOtpStatus { initial, submitting, succeeded, failed }

class VerifyPhoneNumberState {
  final VerifyPhoneNumberStatus status;
  final RequestOtpStatus requestOtpStatus;
  final String? autoReadOtp;
  final String? error;
  final bool isDeactivated;
  final FainzyUser? user;
}
```

#### Events
```dart
listenForSms()           // Auto-read SMS
submitOtp(String otp)    // Verify OTP
requestOtp()             // Resend OTP
```

### 7.3 SetupAccountBloc

#### States
```dart
enum SetupAccountStatus { initial, submitting, succeeded, failed }

class SetupAccountState {
  final FirstNameInput firstName;
  final LastNameInput lastName;
  final EmailInput email;
  final PasswordInput password;
  final bool showPassword;
  final SetupAccountStatus status;
  final String? error;
  final FainzyUser? user;
}
```

#### Events
```dart
FirstNameChanged({required String firstName})
LastNameChanged({required String lastName})
EmailChanged({required String email})
PasswordChanged({required String password})
ToggleShowPassword()
Submitted()
```

### 7.4 UseCurrentAddressBloc

#### States
```dart
enum UseCurrentAddressStatus { initial, searching, resultsFound, noResultsFound, errorOcurred }

class UseCurrentAddressState {
  final UseCurrentAddressStatus status;
  final List<FainzyLocation> searchResults;
  final int radius;  // Search radius in km
  final String? error;
}
```

#### Events
```dart
StartSearching()                    // Use GPS
SearchWithCoordinates({required LatLng latLng})  // Manual coordinates
LocationSelected({required FainzyLocation location})
ApplyRadius({required int radius})   // Change search radius
```

#### State Transitions - In Service Area
```
Initial(radius: 1)
  → StartSearching()
  → Searching()
  → ResultsFound(locations: [Location1, Location2])
  → LocationSelected(Location1)
  → Saved to SettingsBloc
```

#### State Transitions - Not In Service Area
```
Initial(radius: 1)
  → StartSearching()
  → Searching()
  → NoResultsFound()
  → Show UserRequestFormSheet
  → User fills form
  → Submit LocationRequest
  → Form dismissed
  → User blocked from proceeding
```

### 7.5 UserRequestFormBloc

#### States
```dart
enum UserRequestFormStatus { initial, submitting, succeeded, failed }

class UserRequestFormState {
  final TextInput fullname;
  final EmailInput email;
  final TextInput landmark;
  final TextInput city;
  final TextInput country;
  final UserRequestFormStatus status;
  final String? error;
  final bool isSuccessful;
  
  bool get isBusy => status == UserRequestFormStatus.submitting;
  bool get canSubmit => fullname.isValid && email.isValid && 
                        landmark.isValid && city.isValid && country.isValid;
}
```

#### Events
```dart
FullNameChanged({required String fullName})
EmailChanged({required String email})
LandmarkChanged({required String landmark})
CityChanged({required String city})
CountryChanged({required String country})
UserRequestSubmitted()
```

### 7.6 HomeFeedBloc

#### States
```dart
enum HomeFeedStatus { initial, fetching, resultsFound, noResultsFound, errorOcurred }

class HomeFeedState {
  final HomeFeedStatus status;
  final List<FainzyRestaurant> stores;
  final List<FainzyRestaurant> allStores;
  final List<SearchResult> searchResults;
  final String searchQuery;
  final bool isSearching;
  final int selectedTabIndex;
  final String? error;
}
```

#### Events
```dart
FetchData()                    // Load stores for service area
SearchStores({required String query})
ClearSearch()
SelectTab({required int tabIndex})
FetchDiscountStores()
```

### 7.7 StoreBloc

#### States
```dart
enum StoreStatus { initial, fetching, resultsFound, noResultsFound, errorOcurred }

class StoreState {
  final StoreStatus status;
  final List<FainzyMenu> menus;
  final List<FainzyCategory> categories;
  final String? error;
}
```

#### Events
```dart
FetchItems()                   // Load categories and menus
```

### 7.8 StoreItemBloc

#### States
```dart
enum StoreItemStatus { initial, fetching, resultsFound, noResultsFound, errorOcurred }

class StoreItemState {
  final StoreItemStatus status;
  final int quantity;
  final double totalPrice;
  final double basePrice;
  final Map<int, FainzySides> sides;
  final String? error;
}
```

#### Events
```dart
Initialise()
IncrementQuantity()
DecrementQuantity()
ToggleSideItem({required int id})
AddToCart({required BuildContext context})
FetchSides()
```

#### Price Calculation Flow
```
Initialise() 
  → basePrice = menu.discountPrice ?? menu.price
  → totalPrice = basePrice * quantity

IncrementQuantity()
  → quantity = 2
  → totalPrice = basePrice * 2

ToggleSideItem(501)  // Extra Plantain +500
  → basePrice += 500
  → totalPrice = (basePrice + 500) * 2
```

### 7.9 AllCartsBloc

#### States
```dart
class AllCartsState {
  final Map<int, CartModel> carts;  // {storeId: cart}
}
```

#### Events
```dart
AddItemToCart({required FainzyCartItem item, required FainzyRestaurant store, required BuildContext context})
RemoveItemFromCart({required FainzyCartItem item, required FainzyRestaurant store})
IncrementItemQuantity({required FainzyCartItem item, required FainzyRestaurant store})
DecrementItemQuantity({required FainzyCartItem item, required FainzyRestaurant store})
ClearCart({required int storeId})
ClearEntireCart()
```

### 7.10 CheckoutBloc

#### States
```dart
enum CheckoutStatus {
  idle,
  sentToStore,
  loadingOrderCosts,
  loadingCoupons,
  loadingSavedCards,
  orderAccepted,
  orderRejected,
  paymentDone,
  submitting,
  succeeded,
  errorOccurred
}

enum PaymentMethod { newCard, savedCard }

class CheckoutState {
  final CheckoutStatus status;
  final String? error;
  final int? orderId;
  final bool saveCard;
  final double deliveryPercentage;
  final double servicePercentage;
  final double totalValueOfItems;
  final ValueGetter<CouponData?> selectedCoupon;
  final ValueGetter<Map<String, dynamic>> paymentIntent;
  final List<FainzyCartItem> items;
  final List<CouponData> coupons;
  final ValueGetter<FainzyUserOrder?> orderPlaced;
  final List<SavedCard> savedCards;
  final ValueGetter<SavedCard?> selectedCard;
  final PaymentMethod paymentMethod;
  
  double get deliveryFee => deliveryPercentage > 0 ? deliveryPercentage : 0;
  double get serviceFee => servicePercentage > 0 ? (servicePercentage / 100) * totalValueOfItems : 0;
  double get discount => // calculated from selectedCoupon
  double get total => (totalValueOfItems + serviceFee + deliveryFee) - discount;
  bool get isFreeOrder => total <= 0;
}
```

#### Events
```dart
Checkout({required FainzyLocation deliveryLocation, required int userId})
MakePayment()
PlaceFreeOrder()
RunCheckStoreAcceptedOrder({required int orderId})
LoadOrderCosts(String currency)
LoadCoupons()
LoadSavedCards()
SelectPaymentMethod({required PaymentMethod paymentMethod})
ToggleSaveCard({required bool saveCard})
SelectCoupon({required CouponData couponData})
SelectCard({required SavedCard card})
WaitForStoreToAccept()
RemoveCoupon()
RemoveCard()
```

#### Order Status Flow
```
Idle
  → LoadOrderCosts()
  → loadingOrderCosts → idle
  → LoadSavedCards()
  → loadingSavedCards → idle
  → Checkout()
  → submitting
  → sentToStore
  → WaitForStoreToAccept()
  
  BRANCH A (Accepted):
    → RunCheckStoreAcceptedOrder()
    → orderAccepted
    → MakePayment() / PlaceFreeOrder()
    → submitting
    → paymentDone
    → Navigate to success
    
  BRANCH B (Rejected):
    → RunCheckStoreAcceptedOrder()
    → orderRejected
    → Show error, offer retry
```

### 7.11 OrderDetailsBloc

#### States
```dart
enum OrderDetailsStatus { initial, fetching, loaded, errorOcurred }

class OrderDetailsState {
  final OrderDetailsStatus status;
  final FainzyUserOrder? order;
  final List<SavedCard> savedCards;
  final PaymentMethod paymentMethod;
  final ValueGetter<SavedCard?> selectedCard;
  final bool busy;
}
```

#### Events
```dart
FetchOrder()
CancelOrder()
SelectPaymentMethod({required PaymentMethod paymentMethod})
SelectCard({required SavedCard card})
MakePayment()
```

---

## 8. Edge Cases & Error Handling

### 8.1 Authentication Errors

| Scenario | Error | Handling |
|----------|-------|----------|
| Invalid phone format | `"Invalid phone number format"` | Show inline error, don't submit |
| OTP expired | `"OTP has expired"` | Show error, offer resend |
| OTP incorrect | `"Invalid OTP"` | Show error, allow retry |
| Network timeout | TimeoutException | "Check connection", retry button |
| Email already exists | `"Email already registered"` | Suggest login instead |
| Weak password | `"Password must be at least 8 characters"` | Inline validation error |

### 8.2 Location Errors

| Scenario | Error | Handling |
|----------|-------|----------|
| GPS permission denied | PermissionDeniedException | Show manual search option |
| GPS disabled | LocationServiceDisabledException | Prompt to enable GPS |
| No service area found | Empty response `[]` | Show location request form |
| Location request submit fails | ApiResponseError | Show error, allow retry |
| Invalid coordinates | Out of bounds | Show "Invalid location" error |

### 8.3 Store/Menu Errors

| Scenario | Error | Handling |
|----------|-------|----------|
| Store closed | `status: 0` | Grey out store, show "Closed" |
| Menu item sold out | `status: "sold_out"` | Grey out item, show "Sold Out" badge |
| No stores in area | Empty array | Show "No stores available" state |
| Search no results | Empty array | Show "No results found" |
| Category load fails | ApiResponseError | Show error, retry button |

### 8.4 Cart Errors

| Scenario | Error | Handling |
|----------|-------|----------|
| Item already in cart | Duplicate key | Increment quantity instead |
| Store mismatch | Different store | Create new cart for store |
| Quantity below 1 | Min validation | Disable decrement button |
| Item becomes sold out | Status check | Remove from cart, notify user |

### 8.5 Order Errors

| Scenario | Error | Handling |
|----------|-------|----------|
| Store rejects order | `status: "rejected"` | Show rejection, offer retry/different store |
| Payment fails | Stripe error | Show payment error, allow retry |
| Order timeout | Polling timeout | Show "Store not responding", auto-cancel |
| Coupon invalid | `"Invalid coupon code"` | Show error, don't apply |
| Coupon expired | `"Coupon expired"` | Show error, don't apply |
| Network during payment | Connection lost | Save order state, allow resume |

### 8.6 Critical Flow: New User Out of Service Area

```dart
// Complete flow for user outside service area

1. User registers (SetupAccountBloc)
   → Account created successfully
   → Token saved

2. App navigates to location selection (UseCurrentAddressPage)
   → User grants GPS permission
   → GPS returns: LatLng(7.3775, 3.9470) [Ibadan - no service]

3. fetchLocationsByGeo(lat: 7.3775, lng: 3.9470, radius: 1)
   → API returns: []
   
4. State: NoResultsFound
   → UI shows: "We Will Soon Be In Your City!"
   → Shows form: Full Name, Email, Landmark, City, Country

5. User fills form:
   → Full Name: "Adebayo Johnson"
   → Email: "adebayo.j@example.com"
   → Landmark: "University of Ibadan"
   → City: "Ibadan"
   → Country: "Nigeria"

6. Submit Location Request
   → API: POST /v1/entities/location-requests/
   → Response: 201 Created
   → Form shows success, dismisses

7. User is BLOCKED from proceeding
   → No "Continue" button
   → No store access
   → No ordering capability
   → Can only: Change location, Log out, Wait for notification

8. Backend processes request
   → Business team notified
   → When service expands, email sent to user
```

### 8.7 Order Cancellation Flows

#### User Cancels (Pending Status)
```dart
if (order.status == 'pending') {
  await orderRepository.updateOrder(
    orderId: order.id,
    status: 'cancelled'
  );
  // Order cancelled, refund if paid
}
```

#### Store Cancels (After Acceptance)
```dart
if (order.status == 'accepted') {
  // Store calls API to cancel
  await orderRepository.updateOrder(
    orderId: order.id,
    status: 'cancelled'
  );
  // User notified, full refund processed
}
```

#### System Timeout (No Response)
```dart
Timer(Duration(minutes: 10), () async {
  final order = await fetchOrder(orderId);
  if (order.status == 'pending') {
    await orderRepository.updateOrder(
      orderId: order.id,
      status: 'cancelled'
    );
    // Auto-cancelled, user notified
  }
});
```

---

## Appendix: Complete Demo Data Set

### Demo User (New Registration)
```json
{
  "phone_number": "+2348012345678",
  "otp": "123456",
  "first_name": "John",
  "last_name": "Doe",
  "email": "john.doe@example.com",
  "password": "SecurePass123!"
}
```

### Demo User (Existing)
```json
{
  "id": 42,
  "first_name": "Jane",
  "last_name": "Smith",
  "email": "jane.smith@example.com",
  "phone_number": "+2348098765432",
  "token": "jwt_api_token_abc123"
}
```

### Demo Location (In Service Area)
```json
{
  "id": 15,
  "name": "Lagos Island Office Complex",
  "address_details": "123 Marina Road, Lagos Island",
  "city": "Lagos",
  "state": "Lagos",
  "country": "Nigeria",
  "gps_coordinates": {
    "coordinates": [3.3792, 6.5244]
  },
  "service_area": 5
}
```

### Demo Location (Out of Service Area)
```json
{
  "name": "Ibadan Home",
  "city": "Ibadan",
  "state": "Oyo",
  "country": "Nigeria",
  "gps_coordinates": {
    "coordinates": [3.9470, 7.3775]
  },
  "service_area": null
}
```

### Demo Store
```json
{
  "id": 23,
  "name": "Bukka Hut",
  "branch": "Victoria Island",
  "address": {
    "street": "234 Adeola Odeku Street",
    "city": "Lagos",
    "state": "Lagos",
    "country": "Nigeria"
  },
  "gps_coordinates": {
    "coordinates": [3.4215, 6.4335]
  },
  "rating": 4.5,
  "total_reviews": 128,
  "status": 1,
  "currency": "NGN"
}
```

### Demo Menu Item with Sides
```json
{
  "menu": {
    "id": 101,
    "name": "Jollof Rice & Chicken",
    "price": 3500.00,
    "discount_price": 3150.00,
    "description": "Smoky party jollof rice with grilled chicken leg"
  },
  "quantity": 2,
  "sides": [
    {"id": 501, "name": "Extra Plantain", "price": 500.00},
    {"id": 502, "name": "Coleslaw", "price": 300.00}
  ],
  "unit_price": 3950.00,
  "total": 7900.00
}
```

### Demo Order
```json
{
  "order_id": "#123456",
  "store_id": 23,
  "user_id": 42,
  "location_id": 15,
  "items": [
    {
      "menu_id": 101,
      "quantity": 2,
      "price": 3950.00,
      "sides": [501, 502]
    }
  ],
  "subtotal": 7900.00,
  "delivery_fee": 500.00,
  "service_fee": 395.00,
  "discount": 0.00,
  "total": 8795.00,
  "status": "completed"
}
```

---

## Document Version

**Version**: 1.0  
**Last Updated**: April 27, 2024  
**App**: Fainzy Last Mile User  
**Purpose**: Complete technical walkthrough for development, testing, and onboarding

---

*End of Document*
