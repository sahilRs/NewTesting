import os
import sqlite3
import time
import logging
from threading import Lock
from flask import Flask, request, jsonify, make_response, send_file

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding="utf-8")
    ]
)

app = Flask(__name__)

# ---------------- DB (SQLite) ----------------
DB_PATH = "keys.db"
db_lock = Lock()

# ---------------- DEFAULT DATA (only used to seed if DB empty) ----------------
DEFAULT_SECURE = {
    "com.hul.shikhar.rssm": ["d1", "d2"],
    "com.sahil.work": ["s1", "s2"],
    "com.aebas.aebas_client": ["adhar1", "adhar2"],
}
DEFAULT_SIMPLE = ["d-0924-3841", "x-0924-3841", "s-2227-7194"]


# --- Signature settings (kept from earlier) ---
EXPECTED_SIGNATURE = "1D:03:E2:BD:74:A8:FB:B3:2D:B8:28:F1:16:7B:CC:56:3C:F1:AD:B4:CA:16:8B:6F:FD:D4:08:43:92:41:B3:0C"
XOR_KEY_STRING = "xA9fQ7Ls2"


# ---------------- SQLite helpers ----------------
def init_db():
    """Create DB and tables if they don't exist and seed defaults if empty."""
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        try:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS secure_keys (
                    package TEXT NOT NULL,
                    key TEXT NOT NULL,
                    is_used INTEGER DEFAULT 0,
                    device_id TEXT,
                    last_verified REAL,
                    PRIMARY KEY (package, key)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS simple_keys (
                    key TEXT PRIMARY KEY,
                    is_used INTEGER DEFAULT 0,
                    device_id TEXT,
                    last_verified REAL
                )
            """)
            conn.commit()

            # seed defaults if tables empty
            c.execute("SELECT COUNT(*) FROM secure_keys")
            if c.fetchone()[0] == 0:
                for pkg, keys in DEFAULT_SECURE.items():
                    for k in keys:
                        c.execute("""
                            INSERT OR IGNORE INTO secure_keys (package, key)
                            VALUES (?, ?)
                        """, (pkg, k))
            c.execute("SELECT COUNT(*) FROM simple_keys")
            if c.fetchone()[0] == 0:
                for k in DEFAULT_SIMPLE:
                    c.execute("""
                        INSERT OR IGNORE INTO simple_keys (key)
                        VALUES (?)
                    """, (k,))
            conn.commit()
        finally:
            conn.close()


def _conn():
    """Return a sqlite3 connection configured for rows."""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql, params=(), commit=False, one=False):
    with db_lock:
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            if commit:
                conn.commit()
            if one:
                return cur.fetchone()
            return cur.fetchall()
        finally:
            conn.close()


# ---------------- CRYPTO / SIGNATURE ----------------
import base64


def custom_decrypt(encoded_text: str) -> str:
    if not encoded_text:
        return ""
    key = XOR_KEY_STRING.encode("utf-8")
    missing = len(encoded_text) % 4
    if missing:
        encoded_text += "=" * (4 - missing)
    try:
        raw = base64.b64decode(encoded_text)
    except Exception:
        return ""
    return "".join(chr(raw[i] ^ key[i % len(key)]) for i in range(len(raw)))


def verify_signature(sig_enc: str) -> bool:
    try:
        dec = custom_decrypt(sig_enc)
        # compare trimmed forms
        return dec.strip().rstrip("=") == EXPECTED_SIGNATURE.strip().rstrip("=")
    except Exception:
        return False


# ----------------- CRUD helpers for keys ----------------
def secure_key_exists(package, key):
    row = query(
        "SELECT is_used, device_id, last_verified FROM secure_keys WHERE package=? AND key=?",
        (package, key), one=True
    )
    return row


def simple_key_exists(key):
    row = query(
        "SELECT is_used, device_id, last_verified FROM simple_keys WHERE key=?",
        (key,), one=True
    )
    return row


def add_secure_key(package, key):
    query("""
        INSERT OR IGNORE INTO secure_keys (package, key, is_used, device_id, last_verified)
        VALUES (?, ?, 0, NULL, NULL)
    """, (package, key), commit=True)


def add_simple_key(key):
    query("""
        INSERT OR IGNORE INTO simple_keys (key, is_used, device_id, last_verified)
        VALUES (?, 0, NULL, NULL)
    """, (key,), commit=True)


def delete_secure_key(package, key):
    query("DELETE FROM secure_keys WHERE package=? AND key=?", (package, key), commit=True)


def delete_simple_key(key):
    query("DELETE FROM simple_keys WHERE key=?", (key,), commit=True)


def update_secure_key(package, key, device_id):
    now = time.time()
    query("""
        UPDATE secure_keys
        SET is_used=1, device_id=?, last_verified=?
        WHERE package=? AND key=?
    """, (device_id, now, package, key), commit=True)


def update_simple_key(key, device_id):
    now = time.time()
    query("""
        UPDATE simple_keys
        SET is_used=1, device_id=?, last_verified=?
        WHERE key=?
    """, (device_id, now, key), commit=True)


def list_all_keys_as_dict():
    out = {"SECURE_KEYS": {}, "SIMPLE_KEYS": {}}
    rows = query("SELECT package, key, is_used, device_id, last_verified FROM secure_keys")
    for r in rows:
        pkg = r["package"]
        k = r["key"]
        out["SECURE_KEYS"].setdefault(pkg, {})
        out["SECURE_KEYS"][pkg][k] = {
            "is_used": bool(r["is_used"]),
            "device_id": r["device_id"],
            "last_verified": r["last_verified"]
        }
    rows = query("SELECT key, is_used, device_id, last_verified FROM simple_keys")
    for r in rows:
        k = r["key"]
        out["SIMPLE_KEYS"][k] = {
            "is_used": bool(r["is_used"]),
            "device_id": r["device_id"],
            "last_verified": r["last_verified"]
        }
    return out


# initialize DB on startup
init_db()


# ----------------- API: add_keys (bulk) -----------------
@app.route("/add_keys", methods=["POST"])
def add_keys():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")
    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    if not package:
        # Add into SIMPLE_KEYS
        for k in keys:
            add_simple_key(k)
    else:
        # Add into SECURE_KEYS[package]
        for k in keys:
            add_secure_key(package, k)

    # return DB file for compatibility
    return send_file(DB_PATH, as_attachment=True, download_name="keys.db")


# ----------------- API: delete_keys (bulk) -----------------
@app.route("/delete_keys", methods=["POST"])
def delete_keys():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")
    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    deleted = []
    not_found = []

    if not package:
        # delete from SIMPLE_KEYS
        for k in keys:
            if simple_key_exists(k):
                delete_simple_key(k)
                deleted.append(k)
            else:
                not_found.append(k)
    else:
        for k in keys:
            if secure_key_exists(package, k):
                delete_secure_key(package, k)
                deleted.append(k)
            else:
                not_found.append(k)

    # return DB file for compatibility
    return send_file(DB_PATH, as_attachment=True, download_name="keys.db")


# ----------------- API: add single key (compat) -----------------
@app.route("/add_key", methods=["POST"])
def add_key():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

    if not package:
        add_simple_key(key)
    else:
        add_secure_key(package, key)

    return send_file(DB_PATH, as_attachment=True, download_name="keys.db")


# ----------------- API: delete single key (compat) -----------------
@app.route("/delete_key", methods=["POST"])
def delete_key():
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

    if not package:
        if simple_key_exists(key):
            delete_simple_key(key)
            return send_file(DB_PATH, as_attachment=True, download_name="keys.db")
        else:
            return jsonify({"error": "Key not found in SIMPLE_KEYS"}), 404
    else:
        if secure_key_exists(package, key):
            delete_secure_key(package, key)
            # remove package row cleanup is automatic --- no separate package table
            return send_file(DB_PATH, as_attachment=True, download_name="keys.db")
        else:
            return jsonify({"error": "Key not found in SECURE_KEYS for this package"}), 404


# ----------------- API: keys verification (GET) -----------------
@app.route("/keys", methods=["GET"])
def handle_keys():
    key = request.args.get("key")
    device_id = request.args.get("device_id")
    package = request.args.get("package")
    sig = request.args.get("sig")

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        row = secure_key_exists(package, key)
        if not row:
            return jsonify({"error": "Invalid key or package (secure mode)"}), 401
        is_used = bool(row["is_used"])
        old_device = row["device_id"]
        # key already used by another device
        if is_used and old_device and old_device != device_id:
            return jsonify({"error": "Key already in use by another device"}), 403

        # if already used by same device, just update last_verified to avoid unnecessary writes to other fields
        if is_used and old_device == device_id:
            update_secure_key(package, key, device_id)  # update last_verified timestamp
            return jsonify({"success": True, "message": "Key verified"}), 200

        # new registration or previously unused
        update_secure_key(package, key, device_id)
        return jsonify({"success": True, "message": "Key verified/registered"}), 200
    else:
        row = simple_key_exists(key)
        if not row:
            return jsonify({"error": "Invalid simple key"}), 401
        is_used = bool(row["is_used"])
        old_device = row["device_id"]
        if is_used and old_device and old_device != device_id:
            return jsonify({"error": "Key already in use by another device"}), 403

        if is_used and old_device == device_id:
            update_simple_key(key, device_id)  # bump last_verified
            return jsonify({"success": True, "message": "Key verified"}), 200

        update_simple_key(key, device_id)
        return jsonify({"success": True, "message": "Key verified/registered"}), 200


# ----------------- API: ids (POST) for device registration -----------------
@app.route("/ids", methods=["POST"])
def handle_ids():
    key = request.args.get("key")
    package = request.args.get("package")
    sig = request.args.get("sig")

    try:
        device_id = request.data.decode("utf-8").strip()
    except Exception:
        device_id = None

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        row = secure_key_exists(package, key)
        if not row:
            return jsonify({"error": "Invalid key/package (secure mode)"}), 401
        is_used = bool(row["is_used"])
        old_device = row["device_id"]
        if is_used and old_device and old_device != device_id:
            return jsonify({"error": "Key already registered to another device"}), 403

        update_secure_key(package, key, device_id)
        return jsonify({"success": True, "message": "Device registered/verified"}), 200
    else:
        row = simple_key_exists(key)
        if not row:
            return jsonify({"error": "Invalid simple key"}), 401
        is_used = bool(row["is_used"])
        old_device = row["device_id"]
        if is_used and old_device and old_device != device_id:
            return jsonify({"error": "Key already registered to another device"}), 403

        update_simple_key(key, device_id)
        return jsonify({"success": True, "message": "Device registered/verified"}), 200


# ----------------- API: download DB manually -----------------
@app.route("/download_db", methods=["GET"])
def download_db():
    if not os.path.exists(DB_PATH):
        init_db()
    return send_file(DB_PATH, as_attachment=True, download_name="keys.db")


# ----------------- API: upload DB (restore after redeploy) -----------------
@app.route("/upload_db", methods=["POST"])
def upload_db():
    if "file" not in request.files:
        return jsonify({"error": "File missing"}), 400
    file = request.files["file"]
    # save uploaded file as DB_PATH (overwrite)
    file.save(DB_PATH)
    # basic sanity: ensure tables exist (init_db is safe to call)
    init_db()
    return jsonify({"success": True, "message": "Database restored successfully"}), 200


# ----------------- API: list all (debug) -----------------
@app.route("/list_all", methods=["GET"])
def list_all():
    return jsonify(list_all_keys_as_dict()), 200


# ----------------- API: debug signature (optional) -----------------
@app.route("/debug_sig", methods=["GET"])
def debug_sig():
    sig = request.args.get("sig")
    if not sig:
        return jsonify({"error": "sig missing"}), 400
    decrypted = custom_decrypt(sig)
    return jsonify({
        "encrypted_input": sig,
        "xor_key": XOR_KEY_STRING,
        "decrypted": decrypted,
        "expected": EXPECTED_SIGNATURE
    }), 200


# ---------------- RUN APP ----------------
if __name__ == "__main__":
    # Production-ready line as requested
    app.run(host="0.0.0.0", port=5000, debug=False)
