# IN.TECH - Demo Store [BETA V19] - Sanitized Public Version

> ⚠️ **SAFE DEMO VERSION** - This is a sanitized public version derived from a private e-commerce project. It contains no real customer data, passwords, addresses, secrets, or `.env` files.

**🚀 Live Demo:** https://inet.pythonanywhere.com
**Repository:** `isafiih68-coder/In-Tech-Demo`  
**Main File:** `flask_demo.py` (1169 lines)

### 🌐 Try The Live App
You can directly try the running version of this project here:
**👉 https://inet.pythonanywhere.com**

- Homepage / Shop
- Admin: `/admin` (use your ENV password for login)

### 🔒 What Was Sanitized?
To make this repository safe for public use, all sensitive data was removed:

- `STORE_NAME` -> "Demo Store" (original brand removed)
- `ADMIN_EMAIL` -> `admin@example.com` via ENV `DEMO_STORE_ADMIN_EMAIL`
- `ADMIN_PASSWORD` -> Empty by default, via ENV `DEMO_STORE_ADMIN_PASSWORD` (no hardcoded password)
- `STORE_ADDRESS` -> Generic placeholder text
- `COURIER_TRACKING_URLS` -> Replaced with generic "Kurir A / B / C" with empty URLs
- `SECRET_KEY` -> Loaded from ENV `DEMO_STORE_SECRET_KEY` or auto-generated via `secrets.token_hex(32)`
- `DB` -> Renamed to `demo_store.db` inside `/data` directory (original DB not included)
- Removed: All product images, customer upload photos, real database, and personal URLs

The original private code is securely stored in a separate private repository `In-Tech`.

### 🚀 Features (V19)
- Fullstack Flask E-commerce
- SQLite with auto-migration helper `add_column_if_missing()`
- Admin Dashboard: product CRUD, stock management, order management
- Image Upload: `jpg, jpeg, png, webp, gif` with 5MB limit + `secure_filename`
- Customer Features: Registration, login, cart, checkout, order tracking
- Security: Password hashing with Werkzeug `generate_password_hash` / `check_password_hash`
- REST API Endpoints:
    - `GET /api/products`
    - `GET /api/product`
    - `GET /api/categories`
    - `POST /api/register`
    - `POST /api/login`

### 🛠️ Tech Stack
Python 3, Flask, SQLite3, Werkzeug, Jinja2, HTML/CSS/JS

### ⚙️ Local Setup

1. Clone the repo
```bash
git clone https://github.com/isafiih68-coder/In-Tech-Demo.git
cd In-Tech-Demo
