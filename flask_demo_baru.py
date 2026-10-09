from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, send_from_directory
import sqlite3, datetime, hashlib, os, json, secrets
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = os.environ.get("DEMO_STORE_SECRET_KEY") or secrets.token_hex(32)  
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.environ.get("DEMO_STORE_DB_PATH", os.path.join(DATA_DIR, "demo_store.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "product_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD = 5 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024  # allow several photos in one request
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif"}

ADMIN_EMAIL = os.environ.get("DEMO_STORE_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("DEMO_STORE_ADMIN_PASSWORD", "")


STORE_MAP_URL = ""
STORE_NAME = "Demo Store"
STORE_ADDRESS = "Alamat contoh — ganti dengan alamat toko Anda"

COURIER_TRACKING_URLS = {
    "Kurir A": "",
    "Kurir B": "",
    "Kurir C": "",
}


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def add_column_if_missing(conn, table, column, definition):
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            user_id INTEGER,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            courier_type TEXT,
            courier_fee INTEGER DEFAULT 0,
            subtotal INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            items TEXT,
            payment TEXT,
            status TEXT DEFAULT 'PENDING',
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            user_id INTEGER,
            sender_name TEXT,
            message TEXT,
            is_admin INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL DEFAULT 0,
            weight TEXT DEFAULT '',
            description TEXT DEFAULT '',
            stock INTEGER DEFAULT 0,
            category_id INTEGER,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            is_main INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            location TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS promos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            discount_type TEXT DEFAULT 'percent',
            discount_value INTEGER DEFAULT 0,
            min_purchase INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    
    add_column_if_missing(conn, "users", "address", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "orders", "courier_fee", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "orders", "subtotal", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "orders", "payment", "TEXT DEFAULT 'COD'")
    add_column_if_missing(conn, "orders", "status", "TEXT DEFAULT 'PENDING'")
    add_column_if_missing(conn, "orders", "courier_name", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "orders", "tracking_number", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "orders", "tracking_status", "TEXT DEFAULT 'Menunggu diproses'")
    add_column_if_missing(conn, "orders", "tracking_location", "TEXT DEFAULT ''")
    add_column_if_missing(conn, "orders", "tracking_updated_at", "TEXT DEFAULT ''")

    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.executemany("INSERT INTO categories(name,active) VALUES(?,1)",
                         [("Semua",), ("Produk",), ("Paket",)])

    
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        product_cat = conn.execute("SELECT id FROM categories WHERE name='Produk'").fetchone()
        cid = product_cat["id"] if product_cat else None
        seed = [
            ("Produk Contoh A", 15000, "250gr", "Deskripsi produk dummy untuk demonstrasi.", 25, cid,
             "demo-product-a.jpg"),
            ("Produk Contoh B", 18000, "250gr", "Deskripsi produk dummy untuk demonstrasi.", 25, cid,
             "demo-product-b.jpg"),
            ("Produk Contoh C", 20000, "200gr", "Deskripsi produk dummy untuk demonstrasi.", 20, cid,
             "demo-product-c.jpg"),
            ("Paket Contoh", 35000, "500gr", "Paket contoh untuk demonstrasi aplikasi.", 15, cid,
             "demo-product-a.jpg"),
        ]
        for name, price, weight, desc, stock, cat, old_img in seed:
            cur = conn.execute("""
                INSERT INTO products(name,price,weight,description,stock,category_id,active,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (name, price, weight, desc, stock, cat, 1, now(), now()))
            pid = cur.lastrowid
            
            old_path = os.path.join(BASE_DIR, "static", old_img)
            if os.path.exists(old_path):
                conn.execute("""
                    INSERT INTO product_images(product_id,filename,is_main,sort_order,created_at)
                    VALUES(?,?,?,?,?)
                """, (pid, old_img, 1, 0, now()))

    conn.commit()
    conn.close()


init_db()


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored, password):
    if not stored:
        return False
    try:
        if stored.startswith(("pbkdf2:", "scrypt:", "argon2:")):
            return check_password_hash(stored, password)
    except Exception:
        pass
    
    return hashlib.sha256(password.encode()).hexdigest() == stored


def upgrade_old_password_if_needed(user_id, stored, password):
    if not stored.startswith(("pbkdf2:", "scrypt:", "argon2:")) and verify_password(stored, password):
        conn = get_db()
        conn.execute("UPDATE users SET password=? WHERE id=?", (hash_password(password), user_id))
        conn.commit()
        conn.close()


def admin_logged():
    return bool(session.get("admin_logged"))


def customer_id():
    return session.get("user_id")


def money(n):
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def product_image_url(filename):
    if not filename:
        return ""
    if filename.startswith("/"):
        return filename
    return "/product-images/" + filename


def product_dict(conn, row):
    pid = row["id"]
    imgs = conn.execute("""
        SELECT id,filename,is_main,sort_order
        FROM product_images WHERE product_id=? ORDER BY is_main DESC, sort_order ASC, id ASC
    """, (pid,)).fetchall()
    image_list = [product_image_url(x["filename"]) for x in imgs]
    main = image_list[0] if image_list else ""
    return {
        "id": pid, "name": row["name"], "price": row["price"], "weight": row["weight"] or "",
        "description": row["description"] or "", "stock": row["stock"], "category_id": row["category_id"],
        "active": row["active"], "main_image": main, "images": image_list,
        "category_name": row["category_name"] if "category_name" in row.keys() else ""
    }




@app.get("/api/products")
def api_products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    conn = get_db()
    sql = """
        SELECT p.*, c.name AS category_name
        FROM products p LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.active=1
    """
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if category and category != "Semua":
        sql += " AND c.name=?"
        params.append(category)
    sql += " ORDER BY p.id DESC"
    rows = conn.execute(sql, params).fetchall()
    data = [product_dict(conn, r) for r in rows]
    conn.close()
    return jsonify(data)


@app.get("/api/products/<int:pid>")
def api_product(pid):
    conn = get_db()
    row = conn.execute("""
        SELECT p.*, c.name AS category_name FROM products p
        LEFT JOIN categories c ON c.id=p.category_id
        WHERE p.id=? AND p.active=1
    """, (pid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Produk tidak ditemukan"}), 404
    data = product_dict(conn, row)
    conn.close()
    return jsonify(data)


@app.get("/api/categories")
def api_categories():
    conn = get_db()
    rows = conn.execute("SELECT id,name FROM categories WHERE active=1 ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/register")
def api_register():
    d = request.get_json(silent=True) or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    name = d.get("name", "").strip()
    phone = d.get("phone", "").strip()
    if not email or not password or not name:
        return jsonify({"ok": False, "error": "Nama, email dan password wajib diisi."}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "error": "Password minimal 6 karakter."}), 400
    conn = get_db()
    try:
        cur = conn.execute("""
            INSERT INTO users(email,password,name,phone,address,created_at)
            VALUES(?,?,?,?,?,?)
        """, (email, hash_password(password), name, phone, "", now()))
        conn.commit()
        uid = cur.lastrowid
        user = conn.execute("SELECT id,email,name,phone,address FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        session["user_id"] = uid
        return jsonify({"ok": True, "user": dict(user)})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"ok": False, "error": "Email sudah terdaftar."}), 409


@app.post("/api/login")
def api_login():
    d = request.get_json(silent=True) or {}
    email = d.get("email", "").strip().lower()
    password = d.get("password", "")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not user or not verify_password(user["password"], password):
        conn.close()
        return jsonify({"ok": False, "error": "Email atau password salah."}), 401
    upgrade_old_password_if_needed(user["id"], user["password"], password)
    conn.close()
    session["user_id"] = user["id"]
    session.pop("admin_logged", None)
    return jsonify({"ok": True, "user": {
        "id": user["id"], "email": user["email"], "name": user["name"],
        "phone": user["phone"], "address": user["address"]
    }})


@app.post("/api/logout")
def api_logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@app.get("/api/me")
def api_me():
    uid = customer_id()
    if not uid:
        return jsonify({"logged_in": False})
    conn = get_db()
    u = conn.execute("SELECT id,email,name,phone,address FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not u:
        session.pop("user_id", None)
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user": dict(u)})


@app.post("/api/profile")
def api_profile():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login pelanggan diperlukan."}), 401
    d = request.get_json(silent=True) or {}
    conn = get_db()
    conn.execute("UPDATE users SET name=?,phone=?,address=? WHERE id=?",
                 (d.get("name","").strip(), d.get("phone","").strip(), d.get("address","").strip(), uid))
    conn.commit()
    u = conn.execute("SELECT id,email,name,phone,address FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return jsonify({"ok": True, "user": dict(u)})


@app.post("/api/orders")
def api_orders():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Silakan login pelanggan terlebih dahulu."}), 401
    d = request.get_json(silent=True) or {}
    raw_items = d.get("items", [])
    if not raw_items:
        return jsonify({"ok": False, "error": "Keranjang kosong."}), 400

    
    conn = get_db()
    clean_items = []
    subtotal = 0
    # Merge repeated product IDs so duplicate cart rows cannot bypass stock checks.
    quantities = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("id"))
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            continue
        if pid <= 0 or qty <= 0:
            continue
        quantities[pid] = quantities.get(pid, 0) + min(qty, 99)

    for pid, qty in quantities.items():
        p = conn.execute("SELECT id,name,price,weight,stock,active FROM products WHERE id=?", (pid,)).fetchone()
        if not p or not p["active"]:
            continue
        if qty > 99:
            conn.close()
            return jsonify({"ok": False, "error": "Jumlah per produk maksimal 99."}), 400
        if p["stock"] < qty:
            conn.close()
            return jsonify({"ok": False, "error": f"Stok {p['name']} tidak cukup. Sisa {p['stock']}."}), 400
        line = p["price"] * qty
        subtotal += line
        clean_items.append({"id": p["id"], "name": p["name"], "price": p["price"], "qty": qty, "weight": p["weight"]})

    if not clean_items:
        conn.close()
        return jsonify({"ok": False, "error": "Produk tidak valid."}), 400

    fee = max(0, int(d.get("courier_fee", 0) or 0))
    courier = str(d.get("courier_type", "Ambil di Toko"))[:100]
    total = subtotal + fee
    u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    address = str(d.get("address", "")).strip() or (u["address"] if u else "")
    payment = str(d.get("payment", "COD"))[:50]

    cur = conn.execute("""
        INSERT INTO orders(created_at,user_id,customer_name,phone,address,courier_type,courier_fee,
                            subtotal,total,items,payment,status,courier_name,tracking_number,tracking_status,tracking_location,tracking_updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (now(), uid, u["name"], u["phone"], address, courier, fee, subtotal, total,
          json.dumps(clean_items, ensure_ascii=False), payment, "PENDING", "", "", "Menunggu diproses", "Demo Store", now()))
    oid = cur.lastrowid

    conn.execute("""INSERT INTO tracking_events(order_id,status,location,description,created_at)
                   VALUES(?,?,?,?,?)""",
                 (oid, "Pesanan dibuat", "Demo Store", "Pesanan demo diterima dan menunggu diproses.", now()))

    for item in clean_items:
        conn.execute("UPDATE products SET stock=stock-? WHERE id=?", (item["qty"], item["id"]))

    conn.execute("""
        INSERT INTO notifications(user_id,title,message,is_read,created_at)
        VALUES(?,?,?,?,?)
    """, (uid, "Pesanan dibuat", f"Pesanan #{oid} berhasil dibuat.", 0, now()))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": oid, "subtotal": subtotal, "fee": fee, "total": total})


@app.get("/api/my-orders")
def api_my_orders():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login diperlukan."}), 401
    conn = get_db()
    rows = conn.execute("""
        SELECT id,created_at,customer_name,address,courier_type,courier_fee,subtotal,total,items,payment,status,
               courier_name,tracking_number,tracking_status,tracking_location,tracking_updated_at
        FROM orders WHERE user_id=? ORDER BY id DESC
    """, (uid,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        x = dict(r)
        try:
            x["items"] = json.loads(x["items"])
        except Exception:
            x["items"] = []
        out.append(x)
    return jsonify(out)


@app.get("/api/orders/<int:oid>/tracking")
def api_order_tracking(oid):
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login diperlukan."}), 401
    conn = get_db()
    order = conn.execute("SELECT id,user_id,courier_name,tracking_number,tracking_status,tracking_location,tracking_updated_at,status FROM orders WHERE id=? AND user_id=?", (oid, uid)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Pesanan tidak ditemukan."}), 404
    events = conn.execute("SELECT id,status,location,description,created_at FROM tracking_events WHERE order_id=? ORDER BY id DESC", (oid,)).fetchall()
    conn.close()
    d = dict(order)
    courier = d.get("courier_name") or ""
    d["tracking_url"] = COURIER_TRACKING_URLS.get(courier, "")
    d["events"] = [dict(x) for x in events]
    return jsonify(d)


@app.get("/api/workshop")
def api_workshop():
    return jsonify({"name": STORE_NAME, "address": STORE_ADDRESS, "map_url": STORE_MAP_URL})


@app.get("/api/chats")
def api_chats():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login diperlukan."}), 401
    conn = get_db()
    rows = conn.execute("""
        SELECT id,created_at,sender_name,message,is_admin
        FROM chats WHERE user_id=? ORDER BY id ASC
    """, (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/chats")
def api_chat_send():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login diperlukan."}), 401
    d = request.get_json(silent=True) or {}
    msg = d.get("message", "").strip()
    if not msg:
        return jsonify({"ok": False, "error": "Pesan kosong."}), 400
    conn = get_db()
    u = conn.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
    conn.execute("""
        INSERT INTO chats(created_at,user_id,sender_name,message,is_admin)
        VALUES(?,?,?,?,0)
    """, (now(), uid, u["name"] if u else "Customer", msg[:2000]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/notifications")
def api_notifications():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False, "error": "Login diperlukan."}), 401
    conn = get_db()
    rows = conn.execute("""
        SELECT id,title,message,is_read,created_at FROM notifications
        WHERE user_id=? ORDER BY id DESC LIMIT 50
    """, (uid,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.post("/api/notifications/read")
def api_notifications_read():
    uid = customer_id()
    if not uid:
        return jsonify({"ok": False}), 401
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})




ADMIN_CSS = """
:root{--orange:#ff6a00;--dark:#17202a;--bg:#f4f6f8}
*{box-sizing:border-box;font-family:Inter,system-ui,sans-serif}
body{margin:0;background:var(--bg);color:#222}
a{text-decoration:none;color:inherit}
.admin-top{background:var(--dark);color:white;padding:15px 18px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:20}
.admin-wrap{max-width:1150px;margin:auto;padding:16px}
.admin-nav{display:flex;gap:8px;overflow:auto;background:white;padding:10px;border-radius:12px;margin-bottom:14px;position:sticky;top:65px;z-index:10}
.admin-nav a{padding:9px 12px;border-radius:9px;white-space:nowrap;font-size:13px}
.admin-nav a:hover{background:#fff0e6;color:var(--orange)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.stat{background:white;border-radius:14px;padding:16px;box-shadow:0 2px 7px #0000000d}
.card{background:white;border-radius:14px;padding:15px;margin-bottom:12px;box-shadow:0 2px 7px #0000000d}
.btn{border:0;border-radius:9px;padding:10px 14px;font-weight:700;cursor:pointer}
.primary{background:var(--orange);color:white}.danger{background:#e53935;color:white}.gray{background:#eee}
.input,select,textarea{width:100%;padding:10px;border:1px solid #ddd;border-radius:9px;margin:5px 0}
table{width:100%;border-collapse:collapse;background:white}th,td{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:13px}
.thumb{width:70px;height:70px;object-fit:cover;border-radius:9px}.product-row{display:grid;grid-template-columns:80px 1fr auto;gap:12px;align-items:center}
@media(max-width:700px){.grid{grid-template-columns:repeat(2,1fr)}.admin-nav{top:60px}.product-row{grid-template-columns:60px 1fr}.product-row .actions{grid-column:1/-1}}
"""


ADMIN_LOGIN = f"""<!doctype html><html lang='id'><head><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Admin Demo Store</title><style>{ADMIN_CSS}
.login{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}}
.box{{background:white;padding:25px;border-radius:18px;width:100%;max-width:410px;box-shadow:0 8px 35px #0002}}
h1{color:var(--orange)}
</style></head><body><div class='login'><div class='box'>
<h1>DEMO STORE</h1><h2>Login Admin</h2><p>Panel ini khusus pemilik/admin toko.</p>
<form method='post'><input class='input' name='email' type='email' placeholder='Email admin' required>
<input class='input' name='password' type='password' placeholder='Password' required>
<button class='btn primary' style='width:100%;margin-top:8px'>Masuk ke Dashboard</button></form>
{('<p style="color:#d00">'+error+'</p>') if error else ''}
<p style='font-size:12px;color:#777'>Customer login tetap berada di halaman toko.</p>
<a href='/' style='color:var(--orange)'>← Kembali ke Toko</a>
</div></div></body></html>"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if admin_logged():
        return redirect("/admin")
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if ADMIN_PASSWORD and email == ADMIN_EMAIL.lower() and secrets.compare_digest(password, ADMIN_PASSWORD):
            session["admin_logged"] = True
            session.pop("user_id", None)
            return redirect("/admin")
        error = "Email atau password admin salah."
    return render_template_string(ADMIN_LOGIN, error=error)


@app.get("/admin/logout")
def admin_logout():
    session.pop("admin_logged", None)
    return redirect("/admin/login")


def admin_required():
    if not admin_logged():
        return redirect("/admin/login")
    return None


@app.get("/admin")
def admin_home():
    gate = admin_required()
    if gate: return gate
    conn = get_db()
    stats = {
        "products": conn.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "customers": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "pending": conn.execute("SELECT COUNT(*) FROM orders WHERE status='PENDING'").fetchone()[0],
        "sales": conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status NOT IN ('CANCELLED','BATAL')").fetchone()[0],
        "unread": conn.execute("SELECT COUNT(*) FROM chats WHERE is_admin=0").fetchone()[0],
    }
    latest = conn.execute("SELECT id,customer_name,total,status,created_at FROM orders ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return render_admin("Dashboard", ADMIN_DASH, stats=stats, latest=latest)


ADMIN_BASE = f"""<!doctype html><html lang='id'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{{{{title}}}} - Admin Demo Store</title><style>{ADMIN_CSS}</style></head><body>
<div class='admin-top'><b>🛍️ DEMO STORE · ADMIN V19</b><a href='/admin/logout' style='color:white'>Logout</a></div>
<div class='admin-wrap'>
<div class='admin-nav'>
<a href='/admin'>📊 Dashboard</a><a href='/admin/products'>📦 Produk</a><a href='/admin/orders'>🛒 Pesanan</a>
<a href='/admin/customers'>👥 Pelanggan</a><a href='/admin/chats'>💬 Chat</a><a href='/admin/promos'>🏷️ Promo</a><a href='/'>🏠 Toko</a>
</div>{{{{body|safe}}}}</div></body></html>"""


def render_admin(title, template, **context):
    """Render the page body first, then insert the resulting HTML into the admin shell."""
    body_html = render_template_string(template, **context)
    return render_template_string(ADMIN_BASE, title=title, body=body_html)


ADMIN_DASH = """
<h2>Dashboard</h2>
<div class="grid">
<div class="stat"><small>Produk Aktif</small><h2>{{stats.products}}</h2></div>
<div class="stat"><small>Pesanan</small><h2>{{stats.orders}}</h2></div>
<div class="stat"><small>Pesanan Baru</small><h2>{{stats.pending}}</h2></div>
<div class="stat"><small>Pelanggan</small><h2>{{stats.customers}}</h2></div>
</div>
<div class="card"><b>Total Penjualan</b><h2 style="color:#ff6a00">{{"Rp {:,.0f}".format(stats.sales).replace(",",".")}}</h2></div>
<div class="card"><h3>Pesanan Terbaru</h3><table><tr><th>ID</th><th>Pelanggan</th><th>Total</th><th>Status</th><th>Waktu</th></tr>
{% for o in latest %}<tr><td>#{{o.id}}</td><td>{{o.customer_name}}</td><td>Rp {{ "{:,.0f}".format(o.total).replace(",",".") }}</td><td>{{o.status}}</td><td>{{o.created_at}}</td></tr>{% endfor %}
</table></div>
"""


@app.route("/admin/products", methods=["GET", "POST"])
def admin_products():
    gate = admin_required()
    if gate: return gate
    conn = get_db()
    message = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            pid = request.form.get("id")
            name = request.form.get("name","").strip()
            price = int(request.form.get("price","0") or 0)
            weight = request.form.get("weight","").strip()
            stock = int(request.form.get("stock","0") or 0)
            desc = request.form.get("description","").strip()
            cat = request.form.get("category_id") or None
            active = 1 if request.form.get("active") == "1" else 0
            if not name or price < 0 or stock < 0:
                message = "Nama, harga dan stok harus valid."
            elif pid:
                conn.execute("""UPDATE products SET name=?,price=?,weight=?,description=?,stock=?,category_id=?,active=?,updated_at=? WHERE id=?""",
                             (name,price,weight,desc,stock,cat,active,now(),pid))
                message = "Produk diperbarui."
            else:
                conn.execute("""INSERT INTO products(name,price,weight,description,stock,category_id,active,created_at,updated_at)
                                VALUES(?,?,?,?,?,?,?,?,?)""",
                             (name,price,weight,desc,stock,cat,active,now(),now()))
                message = "Produk ditambahkan."
            conn.commit()
        elif action == "delete":
            pid = int(request.form.get("id"))
            conn.execute("DELETE FROM products WHERE id=?", (pid,))
            conn.commit()
            message = "Produk dihapus."
    cats = conn.execute("SELECT id,name FROM categories WHERE name!='Semua' ORDER BY name").fetchall()
    products = conn.execute("""SELECT p.*,c.name category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.id DESC""").fetchall()
    data = [product_dict(conn,p) for p in products]
    conn.close()
    return render_admin("Produk", ADMIN_PRODUCTS, cats=cats, products=data, message=message)


ADMIN_PRODUCTS = """
<h2>📦 Kelola Produk</h2>
{% if message %}<div class="card" style="border-left:4px solid #ff6a00">{{message}}</div>{% endif %}
<div class="card">
<h3>Tambah Produk</h3>
<form method="post">
<input type="hidden" name="action" value="save">
<input class="input" name="name" placeholder="Nama produk" required>
<div class="grid" style="grid-template-columns:1fr 1fr 1fr">
<input class="input" name="price" type="number" min="0" placeholder="Harga" required>
<input class="input" name="weight" placeholder="Berat, contoh 250gr">
<input class="input" name="stock" type="number" min="0" placeholder="Stok" required>
</div>
<select name="category_id" class="input">{% for c in cats %}<option value="{{c.id}}">{{c.name}}</option>{% endfor %}</select>
<textarea class="input" name="description" rows="4" placeholder="Deskripsi produk"></textarea>
<input type="hidden" name="active" value="1">
<button class="btn primary">+ Simpan Produk</button>
</form></div>
<div class="card"><h3>Daftar Produk</h3>
{% for p in products %}
<div class="product-row" style="padding:12px 0;border-bottom:1px solid #eee">
<div>{% if p.main_image %}<img class="thumb" src="{{p.main_image}}">{% else %}<div class="thumb" style="background:#eee;display:flex;align-items:center;justify-content:center">No Foto</div>{% endif %}</div>
<div><b>{{p.name}}</b><br><span style="color:#ff6a00;font-weight:700">Rp {{ "{:,.0f}".format(p.price).replace(",",".") }}</span><br><small>{{p.weight}} · stok {{p.stock}} · {{p.category_name or "Tanpa kategori"}}</small></div>
<div class="actions">
<a class="btn primary" href="/admin/products/{{p.id}}">Edit / Foto</a>
<form method="post" style="display:inline" onsubmit="return confirm('Hapus produk?')"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{p.id}}"><button class="btn danger">Hapus</button></form>
</div></div>
{% endfor %}</div>
"""


@app.route("/admin/products/<int:pid>", methods=["GET", "POST"])
def admin_product_detail(pid):
    gate = admin_required()
    if gate: return gate
    conn = get_db()
    message = ""
    p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p:
        conn.close()
        return "Produk tidak ditemukan", 404

    if request.method == "POST":
        action = request.form.get("action")
        if action == "save":
            conn.execute("""UPDATE products SET name=?,price=?,weight=?,description=?,stock=?,category_id=?,active=?,updated_at=? WHERE id=?""",
                         (request.form.get("name","").strip(), int(request.form.get("price","0") or 0),
                          request.form.get("weight","").strip(), request.form.get("description","").strip(),
                          int(request.form.get("stock","0") or 0), request.form.get("category_id") or None,
                          1 if request.form.get("active")=="1" else 0, now(), pid))
            conn.commit(); message="Perubahan produk disimpan."
        elif action == "upload":
            files = request.files.getlist("photos")
            current_count = conn.execute("SELECT COUNT(*) FROM product_images WHERE product_id=?", (pid,)).fetchone()[0]
            added = 0
            for f in files:
                if not f or not f.filename or not allowed_file(f.filename): continue
                f.stream.seek(0, os.SEEK_END); size=f.stream.tell(); f.stream.seek(0)
                if size > MAX_UPLOAD: continue
                ext=f.filename.rsplit(".",1)[1].lower()
                fname=f"{pid}_{secrets.token_hex(8)}.{ext}"
                f.save(os.path.join(UPLOAD_DIR, secure_filename(fname)))
                main = 1 if current_count == 0 and added == 0 else 0
                conn.execute("""INSERT INTO product_images(product_id,filename,is_main,sort_order,created_at)
                                VALUES(?,?,?,?,?)""", (pid,fname,main,current_count+added,now()))
                added += 1
            conn.commit(); message=f"{added} foto berhasil diupload."
        elif action == "main":
            iid = int(request.form.get("image_id"))
            conn.execute("UPDATE product_images SET is_main=0 WHERE product_id=?", (pid,))
            conn.execute("UPDATE product_images SET is_main=1 WHERE id=? AND product_id=?", (iid,pid))
            conn.commit(); message="Foto utama diperbarui."
        elif action == "delete_photo":
            iid = int(request.form.get("image_id"))
            img=conn.execute("SELECT filename FROM product_images WHERE id=? AND product_id=?", (iid,pid)).fetchone()
            if img:
                conn.execute("DELETE FROM product_images WHERE id=? AND product_id=?", (iid,pid))
                if img["filename"] and not img["filename"].startswith("/"):
                    try: os.remove(os.path.join(UPLOAD_DIR,img["filename"]))
                    except OSError: pass
                # Ensure one main photo remains if any photo exists.
                first=conn.execute("SELECT id FROM product_images WHERE product_id=? ORDER BY sort_order,id LIMIT 1",(pid,)).fetchone()
                if first:
                    conn.execute("UPDATE product_images SET is_main=0 WHERE product_id=?",(pid,))
                    conn.execute("UPDATE product_images SET is_main=1 WHERE id=?",(first["id"],))
                conn.commit()
            message="Foto dihapus."
    p = conn.execute("SELECT p.*,c.name category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=?", (pid,)).fetchone()
    cats = conn.execute("SELECT id,name FROM categories WHERE name!='Semua' ORDER BY name").fetchall()
    images = conn.execute("SELECT * FROM product_images WHERE product_id=? ORDER BY is_main DESC,sort_order,id",(pid,)).fetchall()
    conn.close()
    return render_admin("Edit Produk", ADMIN_PRODUCT_DETAIL, p=p, cats=cats, images=images, message=message)


ADMIN_PRODUCT_DETAIL = """
<h2>📦 Edit Produk & Foto</h2>
{% if message %}<div class="card">{{message}}</div>{% endif %}
<div class="card"><form method="post">
<input type="hidden" name="action" value="save">
<input class="input" name="name" value="{{p.name}}" placeholder="Nama" required>
<div class="grid" style="grid-template-columns:1fr 1fr 1fr">
<input class="input" name="price" type="number" value="{{p.price}}">
<input class="input" name="weight" value="{{p.weight}}">
<input class="input" name="stock" type="number" value="{{p.stock}}">
</div>
<select name="category_id" class="input">{% for c in cats %}<option value="{{c.id}}" {% if p.category_id==c.id %}selected{% endif %}>{{c.name}}</option>{% endfor %}</select>
<textarea class="input" name="description" rows="5">{{p.description}}</textarea>
<label><input type="checkbox" name="active" value="1" {% if p.active %}checked{% endif %}> Produk aktif</label><br><br>
<button class="btn primary">Simpan Perubahan</button></form></div>

<div class="card"><h3>🖼️ Galeri Foto</h3>
<form method="post" enctype="multipart/form-data">
<input type="hidden" name="action" value="upload">
<input class="input" type="file" name="photos" accept="image/*" multiple required>
<small>Maksimal 5 MB per foto. Bisa pilih beberapa foto sekaligus dari HP.</small><br><br>
<button class="btn primary">Upload Foto</button></form>
<hr>
<div class="grid" style="grid-template-columns:repeat(2,1fr)">
{% for im in images %}
<div style="border:1px solid #eee;padding:8px;border-radius:12px">
<img src="{{('/product-images/'+im.filename) if not im.filename.startswith('/') else im.filename}}" style="width:100%;height:150px;object-fit:cover;border-radius:9px">
{% if im.is_main %}<b style="color:#ff6a00">★ Foto Utama</b>{% else %}
<form method="post" style="margin-top:7px"><input type="hidden" name="action" value="main"><input type="hidden" name="image_id" value="{{im.id}}"><button class="btn gray">Jadikan Utama</button></form>{% endif %}
<form method="post" style="margin-top:7px" onsubmit="return confirm('Hapus foto?')"><input type="hidden" name="action" value="delete_photo"><input type="hidden" name="image_id" value="{{im.id}}"><button class="btn danger">Hapus Foto</button></form>
</div>
{% endfor %}
</div></div>
<a class="btn gray" href="/admin/products">← Kembali ke Produk</a>
"""


@app.route("/admin/orders", methods=["GET", "POST"])
def admin_orders():
    gate = admin_required()
    if gate: return gate
    conn = get_db()
    message = ""
    if request.method == "POST":
        action = request.form.get("action", "status")
        oid = int(request.form.get("id") or 0)
        if action == "tracking":
            courier = request.form.get("courier_name", "").strip()[:50]
            resi = request.form.get("tracking_number", "").strip()[:100]
            tstatus = request.form.get("tracking_status", "").strip()[:100]
            location = request.form.get("tracking_location", "").strip()[:200]
            desc = request.form.get("tracking_description", "").strip()[:500]
            row = conn.execute("SELECT user_id FROM orders WHERE id=?", (oid,)).fetchone()
            conn.execute("""UPDATE orders SET courier_name=?,tracking_number=?,tracking_status=?,tracking_location=?,tracking_updated_at=? WHERE id=?""",
                         (courier,resi,tstatus or "Dalam proses",location,now(),oid))
            conn.execute("INSERT INTO tracking_events(order_id,status,location,description,created_at) VALUES(?,?,?,?,?)",
                         (oid,tstatus or "Dalam proses",location,desc or (tstatus or "Status diperbarui"),now()))
            if row and row["user_id"]:
                conn.execute("INSERT INTO notifications(user_id,title,message,is_read,created_at) VALUES(?,?,?,?,?)",
                             (row["user_id"],"📦 Update pengiriman",f"Pesanan #{oid}: {tstatus or 'Dalam proses'}" + (f" — {location}" if location else ""),0,now()))
            conn.commit()
            message = f"Tracking pesanan #{oid} diperbarui."
        else:
            status=request.form.get("status","PENDING")
            allowed={"PENDING","CONFIRMED","PROCESSING","SHIPPED","COMPLETED","CANCELLED"}
            if status in allowed:
                old=conn.execute("SELECT user_id,status FROM orders WHERE id=?",(oid,)).fetchone()
                conn.execute("UPDATE orders SET status=? WHERE id=?",(status,oid))
                if old and old["user_id"]:
                    conn.execute("INSERT INTO notifications(user_id,title,message,is_read,created_at) VALUES(?,?,?,?,?)",
                                 (old["user_id"],"Status pesanan berubah",f"Pesanan #{oid}: {status}",0,now()))
                conn.execute("INSERT INTO tracking_events(order_id,status,location,description,created_at) VALUES(?,?,?,?,?)",
                             (oid,status,"",f"Status pesanan berubah menjadi {status}.",now()))
                conn.commit()
                message = f"Status pesanan #{oid} disimpan."
    rows=conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    conn.close()
    return render_admin("Pesanan", ADMIN_ORDERS, orders=rows, message=message)


ADMIN_ORDERS = """
<h2>🛒 Pesanan & Tracking Kurir</h2>
{% if message %}<div class="card" style="border-left:4px solid #ff6a00">{{message}}</div>{% endif %}
<div class="card"><p style="margin-top:0"><b>Alur:</b> admin memasukkan ekspedisi + nomor resi + lokasi/status terakhir. Pembeli langsung melihat riwayat tracking di aplikasi.</p></div>
{% for o in orders %}
<div class="card">
<div class="row"><div><h3 style="margin:0">#{{o.id}} · {{o.customer_name}}</h3><small>{{o.created_at}} · {{o.phone}}</small></div><b style="color:#ff6a00">Rp {{ "{:,.0f}".format(o.total).replace(",",".") }}</b></div>
<p><b>Alamat:</b> {{o.address}}</p>
<form method="post" style="border-top:1px solid #eee;padding-top:10px">
<input type="hidden" name="action" value="status"><input type="hidden" name="id" value="{{o.id}}">
<div class="grid" style="grid-template-columns:1fr 1fr"><div><label>Status Pesanan</label><select name="status" class="input">
{% for s in ['PENDING','CONFIRMED','PROCESSING','SHIPPED','COMPLETED','CANCELLED'] %}<option {% if o.status==s %}selected{% endif %}>{{s}}</option>{% endfor %}
</select></div><div style="padding-top:28px"><button class="btn primary">Simpan Status</button></div></div></form>
<div style="border-top:1px solid #eee;padding-top:10px;margin-top:10px"><b>🚚 Tracking Kurir</b>
<form method="post"><input type="hidden" name="action" value="tracking"><input type="hidden" name="id" value="{{o.id}}">
<div class="grid" style="grid-template-columns:1fr 1fr 1fr"><select class="input" name="courier_name"><option value="">Pilih ekspedisi</option>{% for c in ['Kurir A','Kurir B','Kurir C'] %}<option {% if o.courier_name==c %}selected{% endif %}>{{c}}</option>{% endfor %}</select><input class="input" name="tracking_number" value="{{o.tracking_number}}" placeholder="Nomor resi"><input class="input" name="tracking_status" value="{{o.tracking_status}}" placeholder="Status terakhir, contoh: Paket berada di pusat sortir"></div>
<div class="grid" style="grid-template-columns:1fr 1fr"><input class="input" name="tracking_location" value="{{o.tracking_location}}" placeholder="Lokasi terakhir"><input class="input" name="tracking_description" placeholder="Keterangan, contoh: Paket sudah keluar dari gudang"></div>
<button class="btn primary">📍 Update Tracking</button></form>
{% if o.tracking_number %}<p class="muted">{{o.courier_name}} · Resi <b>{{o.tracking_number}}</b> · {{o.tracking_status}} · {{o.tracking_location}} · update {{o.tracking_updated_at}}</p>{% endif %}
</div></div>
{% endfor %}
"""



@app.get("/admin/customers")
def admin_customers():
    gate=admin_required()
    if gate: return gate
    conn=get_db()
    rows=conn.execute("""SELECT u.*,COUNT(o.id) order_count,COALESCE(SUM(o.total),0) spent
                         FROM users u LEFT JOIN orders o ON o.user_id=u.id GROUP BY u.id ORDER BY u.id DESC""").fetchall()
    conn.close()
    return render_admin("Pelanggan", ADMIN_CUSTOMERS, customers=rows)


ADMIN_CUSTOMERS = """
<h2>👥 Pelanggan</h2><div class="card"><table><tr><th>Nama</th><th>Email</th><th>HP</th><th>Pesanan</th><th>Total Belanja</th><th>Alamat</th></tr>
{% for u in customers %}<tr><td>{{u.name}}</td><td>{{u.email}}</td><td>{{u.phone}}</td><td>{{u.order_count}}</td>
<td>Rp {{ "{:,.0f}".format(u.spent).replace(",",".") }}</td><td>{{u.address}}</td></tr>{% endfor %}</table></div>
"""


@app.route("/admin/chats", methods=["GET", "POST"])
def admin_chats():
    gate=admin_required()
    if gate: return gate
    conn=get_db()
    if request.method=="POST":
        uid=int(request.form.get("user_id") or 0)
        msg=request.form.get("message","").strip()
        if uid and msg:
            conn.execute("""INSERT INTO chats(created_at,user_id,sender_name,message,is_admin) VALUES(?,?,?,?,1)""",
                         (now(),uid,"Demo Admin",msg[:2000]))
            conn.commit()
    rows=conn.execute("""SELECT c.*,u.name AS customer_name,u.email FROM chats c LEFT JOIN users u ON u.id=c.user_id ORDER BY c.id DESC LIMIT 200""").fetchall()
    users=conn.execute("SELECT id,name,email FROM users ORDER BY name").fetchall()
    conn.close()
    return render_admin("Chat", ADMIN_CHATS, chats=rows, users=users)


ADMIN_CHATS = """
<h2>💬 Chat Pelanggan</h2>
<div class="card"><form method="post"><select class="input" name="user_id" required><option value="">Pilih pelanggan</option>
{% for u in users %}<option value="{{u.id}}">{{u.name}} — {{u.email}}</option>{% endfor %}</select>
<textarea class="input" name="message" placeholder="Balas pelanggan..." required></textarea><button class="btn primary">Kirim Balasan</button></form></div>
<div class="card"><table><tr><th>Waktu</th><th>Pelanggan</th><th>Pengirim</th><th>Pesan</th></tr>
{% for c in chats %}<tr><td>{{c.created_at}}</td><td>{{c.customer_name}}</td><td>{{'Demo Admin' if c.is_admin else c.sender_name}}</td><td>{{c.message}}</td></tr>{% endfor %}</table></div>
"""


@app.route("/admin/promos", methods=["GET", "POST"])
def admin_promos():
    gate=admin_required()
    if gate: return gate
    conn=get_db()
    if request.method=="POST":
        action=request.form.get("action")
        if action=="add":
            conn.execute("""INSERT INTO promos(title,description,discount_type,discount_value,min_purchase,active,created_at)
                            VALUES(?,?,?,?,?,?,?)""",
                         (request.form.get("title","").strip(),request.form.get("description","").strip(),
                          request.form.get("discount_type","percent"),int(request.form.get("discount_value","0") or 0),
                          int(request.form.get("min_purchase","0") or 0),1,now()))
            conn.commit()
        elif action=="toggle":
            pid=int(request.form.get("id")); conn.execute("UPDATE promos SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(pid,)); conn.commit()
        elif action=="delete":
            pid=int(request.form.get("id")); conn.execute("DELETE FROM promos WHERE id=?",(pid,)); conn.commit()
    promos=conn.execute("SELECT * FROM promos ORDER BY id DESC").fetchall()
    conn.close()
    return render_admin("Promo", ADMIN_PROMOS, promos=promos)


ADMIN_PROMOS = """
<h2>🏷️ Promo</h2><div class="card"><form method="post">
<input type="hidden" name="action" value="add"><input class="input" name="title" placeholder="Nama promo" required>
<input class="input" name="description" placeholder="Deskripsi">
<div class="grid" style="grid-template-columns:1fr 1fr 1fr"><select class="input" name="discount_type"><option value="percent">Persen</option><option value="fixed">Potongan Rupiah</option></select>
<input class="input" name="discount_value" type="number" placeholder="Nilai diskon"><input class="input" name="min_purchase" type="number" placeholder="Minimal belanja"></div>
<button class="btn primary">Tambah Promo</button></form></div>
<div class="card"><table><tr><th>Promo</th><th>Diskon</th><th>Min. Belanja</th><th>Status</th><th>Aksi</th></tr>
{% for p in promos %}<tr><td><b>{{p.title}}</b><br>{{p.description}}</td><td>{{p.discount_value}}{{'%' if p.discount_type=='percent' else ' rupiah'}}</td>
<td>Rp {{ "{:,.0f}".format(p.min_purchase).replace(",",".") }}</td><td>{{'AKTIF' if p.active else 'NONAKTIF'}}</td>
<td><form method="post" style="display:inline"><input type="hidden" name="action" value="toggle"><input type="hidden" name="id" value="{{p.id}}"><button class="btn gray">Toggle</button></form>
<form method="post" style="display:inline"><input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="{{p.id}}"><button class="btn danger">Hapus</button></form></td></tr>{% endfor %}</table></div>
"""




CUSTOMER_HTML = r"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Demo Store - Marketplace V19</title>
<style>
:root{--primary:#ff6a00;--bg:#f5f5f5;--text:#222}
*{box-sizing:border-box;font-family:Inter,system-ui,-apple-system,sans-serif}
body{margin:0;background:var(--bg);color:var(--text);padding-bottom:76px}
.header{background:linear-gradient(135deg,#ff6a00,#ff8500);color:#fff;padding:16px 14px 13px;position:sticky;top:0;z-index:30}
.headrow{display:flex;justify-content:space-between;align-items:center;gap:10px}
.brand{font-size:20px;font-weight:900;line-height:1.05}.addr{font-size:11px;opacity:.95;margin-top:4px}
.iconbtn{border:0;background:#ffffff28;color:white;border-radius:12px;width:42px;height:42px;font-size:20px;position:relative}
.badge{position:absolute;top:-5px;right:-5px;background:#e4002b;color:white;border-radius:20px;font-size:10px;padding:3px 6px;font-weight:900}
.search{margin-top:13px;background:#fff;border-radius:10px;padding:10px 12px;display:flex;gap:8px}
.search input{border:0;outline:0;width:100%;font-size:14px}.search button{border:0;background:transparent}
.page{display:none}.page.active{display:block}
.banner{margin:10px 12px;background:linear-gradient(135deg,#ff7b20,#ffb15c);color:#fff;border-radius:15px;padding:17px;font-weight:800}
.cats{display:flex;gap:8px;overflow:auto;padding:2px 12px 10px}.cat{background:white;border:0;border-radius:18px;padding:8px 13px;white-space:nowrap}.cat.active{background:var(--primary);color:white}
.products{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 10px}
.card{background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 2px 7px #0000000d}
.card img{width:100%;height:160px;object-fit:cover;background:#eee}.cardbody{padding:10px}
.name{font-weight:800;font-size:15px;min-height:38px}.muted{color:#777;font-size:12px}.price{color:var(--primary);font-weight:900;font-size:17px;margin:4px 0}
.btn{border:0;border-radius:10px;padding:10px;font-weight:800;cursor:pointer}.primary{background:var(--primary);color:white}.dark{background:#111;color:#fff}.gray{background:#eee}.danger{background:#e53935;color:white}
.card .btn{width:100%}
.bottom{position:fixed;bottom:0;left:0;right:0;height:66px;background:#fff;border-top:1px solid #ddd;display:flex;justify-content:space-around;z-index:40}
.bottom button{border:0;background:transparent;color:#777;font-size:10px;min-width:58px}.bottom button.active{color:var(--primary);font-weight:800}
.modal{display:none;position:fixed;inset:0;background:#0008;z-index:100;align-items:flex-end;justify-content:center}
.sheet{background:white;width:100%;max-width:520px;max-height:94vh;border-radius:20px 20px 0 0;padding:16px;overflow:auto}
.close{float:right;border:0;background:#eee;border-radius:50%;width:34px;height:34px}
.input{width:100%;padding:12px;border:1px solid #ddd;border-radius:10px;margin:6px 0}
.detail-img{width:100%;height:330px;object-fit:cover;border-radius:14px;background:#eee}.thumbs{display:flex;gap:7px;overflow:auto;margin:8px 0}.thumbs img{width:65px;height:65px;object-fit:cover;border-radius:8px;border:2px solid transparent}.thumbs img.sel{border-color:var(--primary)}
.qty{display:flex;align-items:center;gap:12px}.qty button{width:36px;height:36px;border:0;border-radius:9px;background:#eee;font-size:20px}
.fixed-actions{position:sticky;bottom:0;background:#fff;padding-top:10px;display:flex;gap:8px}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px}.panel{background:white;border-radius:14px;padding:14px;margin:10px 12px}
.order{border:1px solid #eee;border-radius:12px;padding:11px;margin:8px 0}
.chat{height:58vh;background:#f3f3f3;border-radius:12px;padding:10px;overflow:auto}.bubble{padding:9px 12px;border-radius:14px;background:white;max-width:82%;margin:5px 0;font-size:13px}.me{margin-left:auto;background:#dcf8c6}
.empty{text-align:center;padding:40px 10px;color:#777}.workshop-card{border:1px solid #ffd5bb}.trackbox{background:#fff7ef;border:1px solid #ffd7b8;border-radius:12px;padding:10px;margin-top:10px}.trackline{border-left:3px solid #ff6a00;padding-left:12px;margin:10px 0}.trackdot{width:9px;height:9px;background:#ff6a00;border-radius:50%;display:inline-block;margin-right:5px}
@media(min-width:700px){.products{grid-template-columns:repeat(4,1fr);max-width:1100px;margin:auto}.header,.banner,.cats{padding-left:max(14px,calc((100% - 1100px)/2));padding-right:max(14px,calc((100% - 1100px)/2))}.sheet{border-radius:18px;margin:auto;margin-bottom:20px}.modal{align-items:center}}
</style></head><body>

<header class="header"><div class="headrow">
<div><div class="brand">DEMO APP<br>DEMO STORE</div><div class="addr">Alamat contoh</div></div>
<div style="display:flex;gap:7px"><button class="iconbtn" onclick="App.openCart()">🛒<span id="cartBadge" class="badge">0</span></button><button class="iconbtn" onclick="App.openChat()">💬</button></div>
</div><div class="search"><input id="search" placeholder="Cari Demo Store..." oninput="App.loadProducts()"><button onclick="App.loadProducts()">🔎</button></div>
</header>

<main>
<section id="home" class="page active"><div class="banner">🛍️ Contoh produk untuk demo<br><small>Pesan mudah, belanja aman.</small></div>
<div class="panel workshop-card"><div class="row"><div><b>📍 Demo Store Workshop</b><br><small>Alamat contoh</small></div><a class="btn primary" href="#" target="_blank" rel="noopener">Buka Maps</a></div><small class="muted">Datang langsung, ambil pesanan, atau lihat lokasi workshop.</small></div>
<div class="cats" id="cats"></div><div class="products" id="products"></div></section>

<section id="orders" class="page"><div class="panel"><h2>📦 Pesanan Saya</h2><div id="ordersList"></div></div></section>
<section id="notif" class="page"><div class="panel"><h2>🔔 Notifikasi</h2><div id="notifList"></div></div></section>
<section id="profile" class="page"><div class="panel"><h2>👤 Saya</h2><div id="profileBox"></div></div></section>
<section id="deals" class="page"><div class="panel"><h2>🏷️ Deals</h2><p>Promo toko akan muncul di sini.</p><div id="promoBox"></div></div></section>
<section id="live" class="page"><div class="panel"><h2>▶️ Live</h2><p>Fitur live bisa dikembangkan pada tahap berikutnya.</p></div></section>
</main>

<nav class="bottom">
<button data-tab="home" class="active" onclick="App.tab('home')">🏠<br>Beranda</button>
<button data-tab="chat" onclick="App.openChat()">💬<br>Chat</button>
<button data-tab="deals" onclick="App.tab('deals')">🏷️<br>Deals</button>
<button data-tab="live" onclick="App.tab('live')">▶️<br>Live</button>
<button data-tab="notif" onclick="App.tab('notif')">🔔<br>Notifikasi</button>
<button data-tab="profile" onclick="App.tab('profile')">👤<br>Saya</button>
</nav>

<div class="modal" id="authModal"><div class="sheet"><button class="close" onclick="App.closeModal('authModal')">✕</button>
<h2>Masuk ke Demo Store</h2><p class="muted">Login pelanggan terpisah dari panel admin.</p>
<div id="loginBox"><input id="loginEmail" class="input" placeholder="Email"><input id="loginPass" type="password" class="input" placeholder="Password">
<button class="btn dark" style="width:100%" onclick="App.login()">Login</button><p style="text-align:center">Belum punya akun? <a href="#" onclick="App.showRegister();return false" style="color:#ff6a00">Daftar</a></p></div>
<div id="registerBox" style="display:none"><input id="regName" class="input" placeholder="Nama lengkap"><input id="regEmail" class="input" placeholder="Email"><input id="regPhone" class="input" placeholder="No HP"><input id="regPass" type="password" class="input" placeholder="Password minimal 6 karakter"><button class="btn primary" style="width:100%" onclick="App.register()">Buat Akun</button><p style="text-align:center">Sudah punya akun? <a href="#" onclick="App.showLogin();return false" style="color:#ff6a00">Login</a></p></div>
</div></div>

<div class="modal" id="detailModal"><div class="sheet"><button class="close" onclick="App.closeModal('detailModal')">✕</button><div id="detailContent"></div></div></div>
<div class="modal" id="cartModal"><div class="sheet"><button class="close" onclick="App.closeModal('cartModal')">✕</button><h2>🛒 Keranjang</h2><div id="cartContent"></div></div></div>
<div class="modal" id="checkoutModal"><div class="sheet"><button class="close" onclick="App.closeModal('checkoutModal')">✕</button><h2>Checkout</h2><div id="checkoutContent"></div></div></div>
<div class="modal" id="chatModal"><div class="sheet"><button class="close" onclick="App.closeModal('chatModal')">✕</button><h2>💬 Chat Demo Admin</h2><div id="chatArea" class="chat"></div><div style="display:flex;gap:6px;margin-top:8px"><input id="chatInput" class="input" placeholder="Tulis pesan..." style="margin:0"><button class="btn primary" onclick="App.sendChat()">Kirim</button></div></div></div>

<script>
const App={
  cart:JSON.parse(localStorage.getItem("demo_store_cart_v1")||"[]"),
  category:"Semua", me:null, detailQty:1, detailProduct:null,
  money(n){return "Rp "+Number(n||0).toLocaleString("id-ID")},
  save(){localStorage.setItem("demo_store_cart_v1",JSON.stringify(this.cart));this.updateBadge()},
  updateBadge(){document.getElementById("cartBadge").textContent=this.cart.reduce((a,x)=>a+x.qty,0)},
  async api(url,opt={}){const r=await fetch(url,opt);let d={};try{d=await r.json()}catch(e){}if(!r.ok)throw new Error(d.error||"Terjadi kesalahan");return d},
  async init(){await this.meCheck();await this.loadCategories();await this.loadProducts();this.updateBadge()},
  async meCheck(){const d=await this.api("/api/me");this.me=d.logged_in?d.user:null},
  async loadCategories(){const cs=await this.api("/api/categories");document.getElementById("cats").innerHTML=cs.map(c=>`<button class="cat ${this.category==c.name?"active":""}" onclick="App.category='${c.name.replaceAll("'","&#39;")}';App.loadCategories();App.loadProducts()">${c.name}</button>`).join("")},
  async loadProducts(){const q=encodeURIComponent(document.getElementById("search").value||"");const d=await this.api("/api/products?q="+q+"&category="+encodeURIComponent(this.category));const g=document.getElementById("products");g.innerHTML=d.length?d.map(p=>`<div class="card" onclick="App.openDetail(${p.id})"><img src="${p.main_image||'https://picsum.photos/500/400?random='+p.id}" onerror="this.src='https://picsum.photos/500/400?random=${p.id}'"><div class="cardbody"><div class="name">${p.name}</div><div class="muted">${p.weight} · stok ${p.stock}</div><div class="price">${this.money(p.price)}</div><button class="btn primary" onclick="event.stopPropagation();App.add(${p.id})">+ Keranjang</button></div></div>`).join(""):`<div class="empty" style="grid-column:1/-1">Produk tidak ditemukan.</div>`},
  async openDetail(id){const p=await this.api("/api/products/"+id);this.detailProduct=p;this.detailQty=1;document.getElementById("detailContent").innerHTML=this.detailHtml(p);document.getElementById("detailModal").style.display="flex"},
  detailHtml(p){const imgs=p.images.length?p.images:[`https://picsum.photos/700/600?random=${p.id}`];return `<img id="detailMain" class="detail-img" src="${imgs[0]}"><div class="thumbs">${imgs.map((im,i)=>`<img class="${i==0?'sel':''}" src="${im}" onclick="App.selectImg(this,'${im}')">`).join("")}</div><h2>${p.name}</h2><div class="price">${this.money(p.price)}</div><div class="muted">${p.weight} · Stok ${p.stock}</div><p>${p.description||"Deskripsi contoh produk."}</p><div class="qty"><button onclick="App.changeDetailQty(-1)">−</button><b id="detailQty">1</b><button onclick="App.changeDetailQty(1)">+</button></div><div class="fixed-actions"><button class="btn gray" style="flex:1" onclick="App.add(${p.id},App.detailQty)">🛒 Keranjang</button><button class="btn primary" style="flex:1" onclick="App.buyNow(${p.id})">Beli Sekarang</button></div>`},
  selectImg(el,src){document.getElementById("detailMain").src=src;document.querySelectorAll(".thumbs img").forEach(x=>x.classList.remove("sel"));el.classList.add("sel")},
  changeDetailQty(n){this.detailQty=Math.max(1,Math.min(this.detailProduct.stock,this.detailQty+n));document.getElementById("detailQty").textContent=this.detailQty},
  async add(id,qty=1){if(!this.me){this.openAuth();return}const p=await this.api("/api/products/"+id);const e=this.cart.find(x=>x.id==id);const newQty=(e?e.qty:0)+qty;if(newQty>p.stock){alert("Stok tidak cukup.");return}if(e)e.qty=newQty;else this.cart.push({id:p.id,name:p.name,price:p.price,qty:qty,weight:p.weight,image:p.main_image});this.save();alert("Produk masuk keranjang.")},
  async buyNow(id){await this.add(id,this.detailQty);if(this.me){this.closeModal("detailModal");this.openCart()}},
  openCart(){if(!this.cart.length){alert("Keranjang masih kosong.");return}this.renderCart();document.getElementById("cartModal").style.display="flex"},
  renderCart(){let sub=0;document.getElementById("cartContent").innerHTML=this.cart.map((x,i)=>{sub+=x.price*x.qty;return `<div class="order"><div class="row"><div><b>${x.name}</b><br><span class="muted">${this.money(x.price)} · ${x.weight||""}</span></div><button class="btn danger" onclick="App.remove(${i})">Hapus</button></div><div class="row" style="margin-top:8px"><div class="qty"><button onclick="App.qty(${i},-1)">−</button><b>${x.qty}</b><button onclick="App.qty(${i},1)">+</button></div><b>${this.money(x.price*x.qty)}</b></div></div>`}).join("")+`<div class="panel" style="margin:10px 0"><div class="row"><span>Subtotal</span><b>${this.money(sub)}</b></div><button class="btn primary" style="width:100%;margin-top:10px" onclick="App.openCheckout()">Checkout</button></div>`},
  qty(i,n){this.cart[i].qty=Math.max(1,this.cart[i].qty+n);this.save();this.renderCart()},
  remove(i){this.cart.splice(i,1);this.save();if(!this.cart.length)this.closeModal("cartModal");else this.renderCart()},
  async openCheckout(){if(!this.me){this.openAuth();return}const u=this.me;let sub=this.cart.reduce((a,x)=>a+x.price*x.qty,0);document.getElementById("checkoutContent").innerHTML=`<div class="panel" style="margin:0 0 10px"><b>📍 Alamat Pengiriman</b><textarea id="shipAddress" class="input" rows="3">${u.address||""}</textarea><small>Pastikan alamat lengkap jika diantar.</small></div><div class="panel" style="margin:0 0 10px"><b>🚚 Pengiriman</b><select id="courier" class="input" onchange="App.calcCheckout()"><option value="0|Ambil di Toko - Gratis">Ambil di Toko - Gratis</option><option value="5000|Area A">Area A - Rp5.000</option><option value="10000|Area B">Area B - Rp10.000</option><option value="15000|Area C">Area C - Rp15.000</option></select><b>💳 Pembayaran</b><select id="payment" class="input"><option>COD</option><option>Transfer</option><option>QRIS</option></select></div><div class="panel" style="margin:0"><div class="row"><span>Subtotal</span><b id="coSub">${this.money(sub)}</b></div><div class="row"><span>Ongkir</span><b id="coFee">Rp 0</b></div><hr><div class="row"><b>Total</b><b id="coTotal" style="color:#ff6a00;font-size:20px">${this.money(sub)}</b></div><button class="btn primary" style="width:100%;margin-top:10px" onclick="App.placeOrder()">Buat Pesanan</button></div>`;this.closeModal("cartModal");document.getElementById("checkoutModal").style.display="flex"},
  calcCheckout(){const fee=parseInt(document.getElementById("courier").value.split("|")[0]||0);const sub=this.cart.reduce((a,x)=>a+x.price*x.qty,0);document.getElementById("coFee").textContent=this.money(fee);document.getElementById("coTotal").textContent=this.money(sub+fee)},
  async placeOrder(){const [fee,courier]=document.getElementById("courier").value.split("|");try{const d=await this.api("/api/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:this.cart,address:document.getElementById("shipAddress").value,courier_fee:Number(fee),courier_type:courier,payment:document.getElementById("payment").value})});this.cart=[];this.save();this.closeModal("checkoutModal");alert("Pesanan #"+d.id+" berhasil dibuat.");this.tab("orders")}catch(e){alert(e.message)}},
  openAuth(){document.getElementById("authModal").style.display="flex";this.showLogin()},
  showLogin(){document.getElementById("loginBox").style.display="block";document.getElementById("registerBox").style.display="none"},
  showRegister(){document.getElementById("loginBox").style.display="none";document.getElementById("registerBox").style.display="block"},
  async login(){try{const d=await this.api("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:document.getElementById("loginEmail").value,password:document.getElementById("loginPass").value})});this.me=d.user;this.closeModal("authModal");alert("Login berhasil. Selamat datang "+this.me.name)}catch(e){alert(e.message)}},
  async register(){try{const d=await this.api("/api/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:document.getElementById("regName").value,email:document.getElementById("regEmail").value,phone:document.getElementById("regPhone").value,password:document.getElementById("regPass").value})});this.me=d.user;this.closeModal("authModal");alert("Akun berhasil dibuat.")}catch(e){alert(e.message)}},
  async logout(){await this.api("/api/logout",{method:"POST"});this.me=null;this.tab("home");alert("Logout berhasil.")},
  async openChat(){if(!this.me){this.openAuth();return}document.getElementById("chatModal").style.display="flex";await this.loadChat()},
  async loadChat(){const d=await this.api("/api/chats");document.getElementById("chatArea").innerHTML=d.length?d.map(x=>`<div class="bubble ${x.is_admin?'':'me'}"><b>${x.is_admin?'Demo Admin':x.sender_name}</b><br>${x.message}<br><small class="muted">${x.created_at}</small></div>`).join(""):`<div class="empty">Mulai percakapan dengan admin.</div>`;const a=document.getElementById("chatArea");a.scrollTop=a.scrollHeight},
  async sendChat(){const i=document.getElementById("chatInput"),msg=i.value.trim();if(!msg)return;await this.api("/api/chats",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg})});i.value="";await this.loadChat()},
  async loadOrders(){if(!this.me){document.getElementById("ordersList").innerHTML=`<div class="empty">Silakan login untuk melihat pesanan.</div>`;return}const d=await this.api("/api/my-orders");if(!d.length){document.getElementById("ordersList").innerHTML=`<div class="empty">Belum ada pesanan.</div>`;return}document.getElementById("ordersList").innerHTML=d.map(o=>`<div class="order"><div class="row"><b>#${o.id}</b><b style="color:#ff6a00">${o.status}</b></div><small>${o.created_at}</small><p>${(o.items||[]).map(x=>x.name+" x"+x.qty).join("<br>")}</p><b>${this.money(o.total)}</b><br><small>${o.courier_type} · ${o.payment}</small><div class="trackbox"><div class="row"><b>📦 Lacak Paket</b><button class="btn gray" onclick="App.loadTracking(${o.id})">Lihat Tracking</button></div><div id="track-${o.id}" style="display:none"></div></div></div>`).join("")},
  async loadTracking(id){const box=document.getElementById("track-"+id);if(!box)return;box.style.display="block";box.innerHTML="Memuat tracking...";try{const d=await this.api("/api/orders/"+id+"/tracking");const ev=d.events||[];box.innerHTML=`<div style="margin-top:10px"><b>${d.courier_name||"Kurir belum dipilih"}</b>${d.tracking_number?` · Resi <b>${d.tracking_number}</b>`:""}<br><span class="muted">${d.tracking_status||"Menunggu diproses"}${d.tracking_location?" · "+d.tracking_location:""}</span>${d.tracking_url&&d.tracking_number?`<br><a class="btn primary" style="display:inline-block;margin-top:8px;text-decoration:none" href="${d.tracking_url}" target="_blank" rel="noopener">🌐 Lacak di Website Kurir</a>`:""}</div><div style="margin-top:8px">${ev.length?ev.map(e=>`<div class="trackline"><span class="trackdot"></span><b>${e.status}</b><br><small>${e.location||""} · ${e.created_at}</small><br><small>${e.description||""}</small></div>`).join(""):"<small class='muted'>Belum ada update perjalanan paket.</small>"}</div>`}catch(e){box.innerHTML="Gagal memuat tracking."}},
  async loadNotif(){if(!this.me){document.getElementById("notifList").innerHTML=`<div class="empty">Login untuk melihat notifikasi.</div>`;return}const d=await this.api("/api/notifications");document.getElementById("notifList").innerHTML=d.length?d.map(x=>`<div class="order"><b>${x.title}</b><br>${x.message}<br><small>${x.created_at}</small></div>`).join(""):`<div class="empty">Belum ada notifikasi.</div>`;await this.api("/api/notifications/read",{method:"POST"})},
  async loadProfile(){const b=document.getElementById("profileBox");if(!this.me){b.innerHTML=`<button class="btn primary" style="width:100%" onclick="App.openAuth()">Login / Daftar</button>`;return}b.innerHTML=`<input id="profName" class="input" value="${this.me.name||""}"><input id="profPhone" class="input" value="${this.me.phone||""}"><textarea id="profAddress" class="input" rows="4" placeholder="Alamat">${this.me.address||""}</textarea><input class="input" value="${this.me.email}" disabled><button class="btn primary" style="width:100%" onclick="App.saveProfile()">Simpan Profil</button><button class="btn gray" style="width:100%;margin-top:8px" onclick="App.logout()">Logout</button>`},
  async saveProfile(){const d=await this.api("/api/profile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:document.getElementById("profName").value,phone:document.getElementById("profPhone").value,address:document.getElementById("profAddress").value})});this.me=d.user;alert("Profil disimpan.")},
  async loadPromos(){document.getElementById("promoBox").innerHTML="<p class='muted'>Promo dikelola dari dashboard admin.</p>"},
  tab(t){document.querySelectorAll(".page").forEach(x=>x.classList.remove("active"));const el=document.getElementById(t);if(el)el.classList.add("active");document.querySelectorAll(".bottom button").forEach(x=>x.classList.toggle("active",x.dataset.tab===t));if(t==="orders")this.loadOrders();if(t==="notif")this.loadNotif();if(t==="profile")this.loadProfile();if(t==="deals")this.loadPromos()},
  closeModal(id){document.getElementById(id).style.display="none"}
};
App.init();
</script></body></html>"""


@app.get("/")
def home():
    return CUSTOMER_HTML


@app.get("/product-images/<path:filename>")
def product_images(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/health")
def health():
    conn = get_db()
    products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return jsonify({"ok": True, "version": "V19", "products": products, "users": users, "workshop": STORE_MAP_URL})



application = app

if __name__ == "__main__":
    app.run(debug=False)
