<p align="center">
  <img src="IMG-20261009-WA7559.jpg" width="140" alt="IN.TECH Logo" />
</p>

# IN.TECH - Demo Store [BETA V1.0]

<p>
  <a href="https://inet.pythonanywhere.com"><img src="https://img.shields.io/badge/Live%20Demo-inet.pythonanywhere.com-00C853?style=flat-square"></a>
  <img src="https://img.shields.io/badge/Stack-Python%20%2F%20Flask%20%2F%20SQLite-blue?style=flat-square">
  <img src="https://img.shields.io/badge/Version-BETA%20V1.0-orange?style=flat-square">
</p>

> Single-file Flask e-commerce implementation (1169 LOC) — Sanitized educational build derived from a private production codebase.

**Live Demo:** https://inet.pythonanywhere.com  
**Main File:** `flask_demo.py`

### Overview
A minimal yet complete e-commerce system built entirely in a single file. This public repository is a sanitized version intended for educational and portfolio reference. It contains no real customer data, credentials, or private assets.

The production version is maintained separately in a private repository.

### Features
- Flask full-stack, single-file architecture
- SQLite with auto-migration helper `add_column_if_missing()`
- Admin dashboard: product CRUD, stock & order management
- Secure image upload: jpg, jpeg, png, webp, gif (5MB limit)
- Customer auth, cart, checkout, order tracking
- Password hashing with Werkzeug
- REST API: `/api/products`, `/api/product`, `/api/categories`

### Tech Stack
Python 3, Flask, SQLite3, Werkzeug, Jinja2

### Local Setup
```bash
git clone https://github.com/isafiih68-coder/In-Tech-Demo.git
cd In-Tech-Demo
pip install flask
export DEMO_STORE_SECRET_KEY="your-secret"
export DEMO_STORE_ADMIN_PASSWORD="your-password"
python flask_demo.py
