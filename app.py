import os
import json
import base64
import time
import logging
import sqlite3
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

# ---------------- Files / constants ----------------
DB_FILE = "keys_db.json"   # kept for compatibility & downloads (will be regenerated from SQLite)
SQLITE_DB = "keys.sqlite"
_db_lock = Lock()

# ---------------- DEFAULT DB (used only if DB file missing/corrupt) ----------------
DEFAULT_DB = {
    "SECURE_KEYS": {
        "com.hul.shikhar.rssm": {
            "d1": {"is_used": False, "device_id": None, "last_verified": None},
            "d2": {"is_used": False, "device_id": None, "last_verified": None}
        },
        "com.sahil.work": {
            "s1": {"is_used": False, "device_id": None, "last_verified": None},
            "s2": {"is_used": False, "device_id": None, "last_verified": None}
        },
        "com.aebas.aebas_client": {
            "adhar1": {"is_used": False, "device_id": None, "last_verified": None},
            "adhar2": {"is_used": False, "device_id": None, "last_verified": None}
        }
    },
    "SIMPLE_KEYS": {
        "d-0924-3841": {"is_used": False, "device_id": None, "last_verified": None},
        "x-0924-3841": {"is_used": False, "device_id": None, "last_verified": None},
        "s-2227-7194": {"is_used": False, "device_id": None, "last_verified": None}
    }
}

# --- Signature settings (kept from earlier) ---
EXPECTED_SIGNATURE = "1D:03:E2:BD:74:A8:FB:B3:2D:B8:28:F1:16:7B:CC:56:3C:F1:AD:B4:CA:16:8B:6F:FD:D4:08:43:92:41:B3:0C"
XOR_KEY_STRING = "xA9fQ7Ls2"

# ---------------- SQLite initialization ----------------
def _get_conn():
    # check_same_thread False because we protect with _db_lock
    conn = sqlite3.connect(SQLITE_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite():
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            # secure_keys: package + key composite PK
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
            # simple_keys: key PK
            c.execute("""
                CREATE TABLE IF NOT EXISTS simple_keys (
                    key TEXT PRIMARY KEY,
                    is_used INTEGER DEFAULT 0,
                    device_id TEXT,
                    last_verified REAL
                )
            """)
            conn.commit()
        finally:
            conn.close()

# Seed DB from DEFAULT_DB only if database empty
def seed_defaults_if_empty():
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM secure_keys")
            if c.fetchone()["cnt"] == 0:
                for pkg, keys in DEFAULT_DB["SECURE_KEYS"].items():
                    for k, meta in keys.items():
                        c.execute(
                            "INSERT OR IGNORE INTO secure_keys (package, key, is_used, device_id, last_verified) VALUES (?, ?, ?, ?, ?)",
                            (pkg, k, 1 if meta.get("is_used") else 0, meta.get("device_id"), meta.get("last_verified"))
                        )
            c.execute("SELECT COUNT(*) as cnt FROM simple_keys")
            if c.fetchone()["cnt"] == 0:
                for k, meta in DEFAULT_DB["SIMPLE_KEYS"].items():
                    c.execute(
                        "INSERT OR IGNORE INTO simple_keys (key, is_used, device_id, last_verified) VALUES (?, ?, ?, ?)",
                        (k, 1 if meta.get("is_used") else 0, meta.get("device_id"), meta.get("last_verified"))
                    )
            conn.commit()
        finally:
            conn.close()

# call at startup
init_sqlite()
seed_defaults_if_empty()

# ---------------- DB HELPERS (shim to preserve original logic) ----------------
def save_db(data):
    """
    Save the provided data dict into SQLite (overwrite existing data).
    Also regenerate keys_db.json file for compatibility with original endpoints that return the JSON file.
    """
    # data expected to follow DEFAULT_DB structure
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            # wipe tables
            c.execute("DELETE FROM secure_keys")
            c.execute("DELETE FROM simple_keys")
            # insert secure keys
            for pkg, keys in data.get("SECURE_KEYS", {}).items():
                for k, meta in keys.items():
                    is_used = 1 if meta.get("is_used") else 0
                    device_id = meta.get("device_id")
                    last_verified = meta.get("last_verified")
                    c.execute(
                        "INSERT INTO secure_keys (package, key, is_used, device_id, last_verified) VALUES (?, ?, ?, ?, ?)",
                        (pkg, k, is_used, device_id, last_verified)
                    )
            # insert simple keys
            for k, meta in data.get("SIMPLE_KEYS", {}).items():
                is_used = 1 if meta.get("is_used") else 0
                device_id = meta.get("device_id")
                last_verified = meta.get("last_verified")
                c.execute(
                    "INSERT INTO simple_keys (key, is_used, device_id, last_verified) VALUES (?, ?, ?, ?)",
                    (k, is_used, device_id, last_verified)
                )
            conn.commit()
        finally:
            conn.close()

    # regenerate JSON file for compatibility (file contents reflect saved DB)
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        logging.exception("Failed to write JSON backup file after saving DB.")


def load_db():
    """
    Read the DB from SQLite and return a dict structured exactly like DEFAULT_DB.
    If SQLite missing or empty/corrupt, create JSON backup and seed defaults.
    """
    # If sqlite missing for some reason, create and seed
    if not os.path.exists(SQLITE_DB):
        init_sqlite()
        seed_defaults_if_empty()
        # write DEFAULT_DB to JSON as well
        try:
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_DB, f, indent=4)
        except Exception:
            pass
        return dict(DEFAULT_DB)

    out = {"SECURE_KEYS": {}, "SIMPLE_KEYS": {}}

    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            try:
                c.execute("SELECT package, key, is_used, device_id, last_verified FROM secure_keys")
                rows = c.fetchall()
                for r in rows:
                    pkg = r["package"]
                    k = r["key"]
                    out["SECURE_KEYS"].setdefault(pkg, {})
                    out["SECURE_KEYS"][pkg][k] = {
                        "is_used": bool(r["is_used"]),
                        "device_id": r["device_id"],
                        "last_verified": r["last_verified"]
                    }

                c.execute("SELECT key, is_used, device_id, last_verified FROM simple_keys")
                rows = c.fetchall()
                for r in rows:
                    k = r["key"]
                    out["SIMPLE_KEYS"][k] = {
                        "is_used": bool(r["is_used"]),
                        "device_id": r["device_id"],
                        "last_verified": r["last_verified"]
                    }
            except Exception:
                # If anything goes wrong reading sqlite, fallback to DEFAULT_DB and re-seed
                logging.exception("Error reading SQLite DB — re-seeding defaults.")
                save_db(dict(DEFAULT_DB))
                return dict(DEFAULT_DB)
        finally:
            conn.close()

    # ensure top-level sections exist
    if "SECURE_KEYS" not in out or not isinstance(out["SECURE_KEYS"], dict):
        out["SECURE_KEYS"] = {}
    if "SIMPLE_KEYS" not in out or not isinstance(out["SIMPLE_KEYS"], dict):
        out["SIMPLE_KEYS"] = {}

    # persist JSON copy (to keep parity with older behavior where a JSON file always exists)
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4)
    except Exception:
        logging.exception("Failed to write JSON backup file in load_db().")

    return out

# Load DB into memory at startup (keeps same variable as original)
db = load_db()

# ----------------- FORCE DOWNLOAD (keeps original behavior) -----------------
def force_download(filepath, filename="keys_db.json"):
    # ensure JSON file exists; if not, regenerate from sqlite
    if not os.path.exists(filepath):
        # regenerate from sqlite
        _ = load_db()
    with open(filepath, "rb") as f:
        data = f.read()
    resp = make_response(data)
    resp.headers.set("Content-Type", "application/octet-stream")
    resp.headers.set("Content-Disposition", f"attachment; filename={filename}")
    resp.headers.set("Content-Length", len(data))
    return resp

# ---------------- CRYPTO / SIGNATURE (unchanged) ----------------
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
        return dec.strip().rstrip("=") == EXPECTED_SIGNATURE.strip().rstrip("=")
    except Exception:
        return False


@app.route("/add_keys", methods=["POST"])
def add_keys():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "NAINAK82JS":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")
    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    global db
    db = load_db()

    if not package:
        for k in keys:
            db["SIMPLE_KEYS"][k] = {"is_used": False, "device_id": None, "last_verified": None}
    else:
        if package not in db["SECURE_KEYS"]:
            db["SECURE_KEYS"][package] = {}
        for k in keys:
            db["SECURE_KEYS"][package][k] = {"is_used": False, "device_id": None, "last_verified": None}

    save_db(db)
    return force_download(DB_FILE, "keys_db.json")
# ----------------- API: delete_keys (bulk) -----------------
@app.route("/delete_keys", methods=["POST"])
def delete_keys():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "NAINAK82JS":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")

    global db
    db = load_db()

    deleted = []
    not_found = []

    if not package:
        for k in keys:
            if k in db["SIMPLE_KEYS"]:
                del db["SIMPLE_KEYS"][k]
                deleted.append(k)
            else:
                not_found.append(k)
    else:
        if package not in db["SECURE_KEYS"]:
            return jsonify({"error": "Package not found"}), 404

        for k in keys:
            if k in db["SECURE_KEYS"][package]:
                del db["SECURE_KEYS"][package][k]
                deleted.append(k)
            else:
                not_found.append(k)

        if not db["SECURE_KEYS"][package]:
            del db["SECURE_KEYS"][package]

    save_db(db)
    return force_download(DB_FILE, "keys_db.json")

# ----------------- API: add single key (compat) -----------------
@app.route("/add_key", methods=["POST"])
def add_key():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "NAINAK82JS":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")

    global db
    db = load_db()

    if not package:
        db["SIMPLE_KEYS"][key] = {"is_used": False, "device_id": None, "last_verified": None}
    else:
        if package not in db["SECURE_KEYS"]:
            db["SECURE_KEYS"][package] = {}
        db["SECURE_KEYS"][package][key] = {"is_used": False, "device_id": None, "last_verified": None}

    save_db(db)
    return force_download(DB_FILE, "keys_db.json")

# ----------------- API: delete single key (compat) -----------------
@app.route("/delete_key", methods=["POST"])
def delete_key():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "NAINAK82JS":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")

    global db
    db = load_db()

    if not package:
        if key in db["SIMPLE_KEYS"]:
            del db["SIMPLE_KEYS"][key]
            save_db(db)
            return force_download(DB_FILE, "keys_db.json")
        else:
            return jsonify({"error": "Key not found"}), 404
    else:
        if package in db["SECURE_KEYS"] and key in db["SECURE_KEYS"][package]:
            del db["SECURE_KEYS"][package][key]

            if not db["SECURE_KEYS"][package]:
                del db["SECURE_KEYS"][package]

            save_db(db)
            return force_download(DB_FILE, "keys_db.json")
        else:
            return jsonify({"error": "Key not found in secure package"}), 404
# ----------------- API: keys verification (GET) -----------------
@app.route("/keys", methods=["GET"])
def handle_keys():
    key = request.args.get("key")
    device_id = request.args.get("device_id")
    package = request.args.get("package")
    sig = request.args.get("sig")

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    global db
    db = load_db()

    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        if package not in db["SECURE_KEYS"] or key not in db["SECURE_KEYS"][package]:
            return jsonify({"error": "Invalid key or package (secure mode)"}), 401
        entry = db["SECURE_KEYS"][package][key]
    else:
        if key not in db["SIMPLE_KEYS"]:
            return jsonify({"error": "Invalid simple key"}), 401
        entry = db["SIMPLE_KEYS"][key]

    # key already used by another device
    if entry.get("is_used") and entry.get("device_id") != device_id:
        return jsonify({"error": "Key already in use by another device"}), 403

    # register/verify
    entry["is_used"] = True
    entry["device_id"] = device_id
    entry["last_verified"] = time.time()

    save_db(db)
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

    global db
    db = load_db()
    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        if package not in db["SECURE_KEYS"] or key not in db["SECURE_KEYS"][package]:
            return jsonify({"error": "Invalid key/package (secure mode)"}), 401
        entry = db["SECURE_KEYS"][package][key]
    else:
        if key not in db["SIMPLE_KEYS"]:
            return jsonify({"error": "Invalid simple key"}), 401
        entry = db["SIMPLE_KEYS"][key]

    if entry.get("is_used") and entry.get("device_id") != device_id:
        return jsonify({"error": "Key already registered to another device"}), 403

    entry["is_used"] = True
    entry["device_id"] = device_id
    entry["last_verified"] = time.time()

    save_db(db)
    return jsonify({"success": True, "message": "Device registered/verified"}), 200

# ----------------- API: download DB manually -----------------
@app.route("/download_db", methods=["GET"])
def download_db():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "XNSLNSJ":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    # regenerate JSON if missing or stale
    if not os.path.exists(DB_FILE):
        save_db(load_db())

    return force_download(DB_FILE, "keys_db.json")

# ----------------- API: upload DB (restore after redeploy) -----------------
@app.route("/upload_db", methods=["POST"])
def upload_db():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "ADMINUPLOAD9027":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    if "file" not in request.files:
        return jsonify({"error": "File missing"}), 400

    file = request.files["file"]
    uploaded_path = DB_FILE + ".upload"
    file.save(uploaded_path)

    try:
        with open(uploaded_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("Invalid JSON")

        save_db(data)
    except Exception:
        logging.exception("Uploaded DB invalid")
        return jsonify({"error": "Uploaded file invalid"}), 400
    finally:
        try:
            os.remove(uploaded_path)
        except Exception:
            pass

    global db
    db = load_db()
    return jsonify({"success": True, "message": "Database restored successfully"}), 200
# ----------------- API: list all (debug) -----------------
@app.route("/list_all", methods=["GET"])
def list_all():
    # ---- PASSWORD CHECK ----
    pwd = request.args.get("password")
    if pwd != "NAINAK82JS":
        return jsonify({"error": "INVALID PASSWORD"}), 401
    # -------------------------

    global db
    db = load_db()
    return jsonify(db), 200

# ----------------- API: reset DB to defaults -----------------
# NOTE: you asked earlier to remove reset_db endpoint. Keeping it removed here (do not add).
# If you want it re-added, tell me.

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
