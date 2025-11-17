import os
import json
import base64
import time
import logging
import sqlite3
from threading import Lock
from flask import Flask, request, jsonify, make_response

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding="utf-8")
    ]
)

app = Flask(__name__)

# ---------------- Files / constants ----------------
SQLITE_DB = "keys.sqlite"
JSON_BACKUP = "keys_db.json"
_db_lock = Lock()

# ---------------- DEFAULT KEYS ----------------
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

# ---------------- Signature (CHANGE THESE IF EVER EXPOSED!) ----------------
EXPECTED_SIGNATURE = "1D:03:E2:BD:74:A8:FB:B3:2D:B8:28:F1:16:7B:CC:56:3C:F1:AD:B4:CA:16:8B:6F:FD:D4:08:43:92:41:B3:0C"
XOR_KEY_STRING = "xA9fQ7Ls2"

# ---------------- Admin Tokens (no longer in URL!) ----------------
ADMIN_TOKEN_ADD_DELETE = "NAINAK82JS"          # for add/delete/list
ADMIN_TOKEN_DOWNLOAD    = "XNSLNSJ"            # for download
ADMIN_TOKEN_UPLOAD      = "ADMINUPLOAD9027"    # for upload/restore

# ---------------- SQLite Helpers ----------------
def _get_conn():
    conn = sqlite3.connect(SQLITE_DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite():
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS secure_keys (
                package TEXT NOT NULL, key TEXT NOT NULL,
                is_used INTEGER DEFAULT 0, device_id TEXT, last_verified REAL,
                PRIMARY KEY (package, key))""")
            c.execute("""CREATE TABLE IF NOT EXISTS simple_keys (
                key TEXT PRIMARY KEY, is_used INTEGER DEFAULT 0,
                device_id TEXT, last_verified REAL)""")
            conn.commit()
        finally:
            conn.close()

def seed_defaults_if_empty():
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM secure_keys")
            if c.fetchone()["cnt"] == 0:
                for pkg, keys in DEFAULT_DB["SECURE_KEYS"].items():
                    for k, v in keys.items():
                        c.execute("INSERT OR IGNORE INTO secure_keys VALUES (?, ?, ?, ?, ?)",
                                  (pkg, k, 0, None, None))
                for k, v in DEFAULT_DB["SIMPLE_KEYS"].items():
                    c.execute("INSERT OR IGNORE INTO simple_keys VALUES (?, ?, ?, ?)",
                              (k, 0, None, None))
                conn.commit()
        finally:
            conn.close()

init_sqlite()
seed_defaults_if_empty()

# ---------------- Core DB Functions (atomic) ----------------
def load_db():
    out = {"SECURE_KEYS": {}, "SIMPLE_KEYS": {}}
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT package, key, is_used, device_id, last_verified FROM secure_keys")
            for r in c.fetchall():
                pkg = r["package"]
                out["SECURE_KEYS"].setdefault(pkg, {})[r["key"]] = {
                    "is_used": bool(r["is_used"]),
                    "device_id": r["device_id"],
                    "last_verified": r["last_verified"]
                }
            c.execute("SELECT key, is_used, device_id, last_verified FROM simple_keys")
            for r in c.fetchall():
                out["SIMPLE_KEYS"][r["key"]] = {
                    "is_used": bool(r["is_used"]),
                    "device_id": r["device_id"],
                    "last_verified": r["last_verified"]
                }
        finally:
            conn.close()
    return out

def save_db(data):
    with _db_lock:
        conn = _get_conn()
        try:
            c = conn.cursor()
            c.execute("DELETE FROM secure_keys")
            c.execute("DELETE FROM simple_keys")
            for pkg, keys in data.get("SECURE_KEYS", {}).items():
                for k, meta in keys.items():
                    c.execute("INSERT INTO secure_keys VALUES (?, ?, ?, ?, ?)",
                              (pkg, k, int(meta["is_used"]), meta["device_id"], meta["last_verified"]))
            for k, meta in data.get("SIMPLE_KEYS", {}).items():
                c.execute("INSERT INTO simple_keys VALUES (?, ?, ?, ?)",
                          (k, int(meta["is_used"]), meta["device_id"], meta["last_verified"]))
            conn.commit()
        finally:
            conn.close()
        # Keep JSON backup for compatibility
        try:
            with open(JSON_BACKUP, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception:
            logging.exception("Failed to update JSON backup")

# ---------------- Crypto ----------------
def custom_decrypt(encoded_text: str) -> str:
    if not encoded_text: return ""
    key = XOR_KEY_STRING.encode("utf-8")
    missing = len(encoded_text) % 4
    if missing: encoded_text += "=" * (4 - missing)
    try:
        raw = base64.b64decode(encoded_text)
        return "".join(chr(raw[i] ^ key[i % len(key)]) for i in range(len(raw)))
    except Exception:
        return ""

def verify_signature(sig_enc: str) -> bool:
    try:
        return custom_decrypt(sig_enc).strip().rstrip("=") == EXPECTED_SIGNATURE.strip().rstrip("=")
    except Exception:
        return False

# ---------------- Helper: Bind key to device (core logic) ----------------
def bind_key_to_device(package, key, device_id, signature=None):
    with _db_lock:
        data = load_db()
        entry = None
        is_secure = package and signature is not None

        if is_secure:
            if not verify_signature(signature):
                return False, "SIGNATURE VERIFICATION FAILED"
            entry = data["SECURE_KEYS"].get(package, {}).get(key)
        else:
            entry = data["SIMPLE_KEYS"].get(key)

        if not entry:
            return False, "Invalid key"

        if entry["is_used"] and entry["device_id"] != device_id:
            return False, "Key already in use by another device"

        entry["is_used"] = True
        entry["device_id"] = device_id
        entry["last_verified"] = time.time()
        save_db(data)
        return True, "OK"

# ---------------- Routes ----------------
def require_admin_token(token_expected):
    token = request.headers.get("X-Admin-Token")
    if not token or token != token_expected:
        return jsonify({"error": "Unauthorized"}), 401
    return None

def force_download():
    if not os.path.exists(JSON_BACKUP):
        save_db(load_db())
    with open(JSON_BACKUP, "rb") as f:
        data = f.read()
    resp = make_response(data)
    resp.headers.set("Content-Type", "application/octet-stream")
    resp.headers.set("Content-Disposition", 'attachment; filename="keys_db.json"')
    return resp

@app.route("/keys", methods=["GET"])
def handle_keys():
    key = request.args.get("key")
    device_id = request.args.get("device_id")
    package = request.args.get("package")
    sig = request.args.get("sig")

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    success, msg = bind_key_to_device(package, key, device_id, sig)
    if not success:
        return jsonify({"error": msg}), 403 if "use" in msg or "SIGNATURE" in msg else 401
    return jsonify({"success": True, "message": "Key verified/registered"}), 200

@app.route("/ids", methods=["POST"])
def handle_ids():
    key = request.args.get("key")
    package = request.args.get("package")
    sig = request.args.get("sig")
    try:
        device_id = request.data.decode("utf-8").strip()
    except Exception:
        return jsonify({"error": "Invalid device_id"}), 400

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    success, msg = bind_key_to_device(package, key, device_id, sig)
    if not success:
        return jsonify({"error": msg}), 403 if "use" in msg or "SIGNATURE" in msg else 401
    return jsonify({"success": True, "message": "Device registered/verified"}), 200

@app.route("/add_keys", methods=["POST"])
def add_keys():
    auth = require_admin_token(ADMIN_TOKEN_ADD_DELETE)
    if auth: return auth

    data = request.get_json(force=True, silent=True)
    if not data or not isinstance(data.get("keys"), list):
        return jsonify({"error": "Provide 'keys' as list"}), 400

    package = data.get("package")
    keys = data.get("keys", [])

    with _db_lock:
        db = load_db()
        target = db["SECURE_KEYS"] if package else db["SIMPLE_KEYS"]
        if package and package not in db["SECURE_KEYS"]:
            db["SECURE_KEYS"][package] = {}

        for k in keys:
            if package:
                if k in db["SECURE_KEYS"][package]:
                    return jsonify({"error": f"Key '{k}' already exists in package"}), 400
                db["SECURE_KEYS"][package][k] = {"is_used": False, "device_id": None, "last_verified": None}
            else:
                if k in db["SIMPLE_KEYS"]:
                    return jsonify({"error": f"Simple key '{k}' already exists"}), 400
                db["SIMPLE_KEYS"][k] = {"is_used": False, "device_id": None, "last_verified": None}

        save_db(db)
    return force_download()

@app.route("/delete_keys", methods=["POST"])
def delete_keys():
    auth = require_admin_token(ADMIN_TOKEN_ADD_DELETE)
    if auth: return auth

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    keys = data.get("keys", [])

    with _db_lock:
        db = load_db()
        deleted = []
        if not package:
            for k in keys:
                if k in db["SIMPLE_KEYS"]:
                    del db["SIMPLE_KEYS"][k]
                    deleted.append(k)
        else:
            if package not in db["SECURE_KEYS"]:
                return jsonify({"error": "Package not found"}), 404
            for k in keys:
                if k in db["SECURE_KEYS"][package]:
                    del db["SECURE_KEYS"][package][k]
                    deleted.append(k)
            if not db["SECURE_KEYS"][package]:
                del db["SECURE_KEYS"][package]
        save_db(db)
    return force_download()

@app.route("/download_db", methods=["GET"])
def download_db():
    auth = require_admin_token(ADMIN_TOKEN_DOWNLOAD)
    if auth: return auth
    return force_download()

@app.route("/upload_db", methods=["POST"])
def upload_db():
    auth = require_admin_token(ADMIN_TOKEN_UPLOAD)
    if auth: return auth

    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files["file"]
    temp_path = JSON_BACKUP + ".tmp"
    file.save(temp_path)

    try:
        with open(temp_path, "r", encoding="utf-8") as f:
            new_data = json.load(f)
        if not isinstance(new_data, dict):
            raise ValueError("Not a dict")
        save_db(new_data)
        return jsonify({"success": True, "message": "DB restored"}), 200
    except Exception as e:
        logging.exception("Upload failed")
        return jsonify({"error": "Invalid file"}), 400
    finally:
        try: os.remove(temp_path)
        except: pass

@app.route("/list_all", methods=["GET"])
def list_all():
    auth = require_admin_token(ADMIN_TOKEN_ADD_DELETE)
    if auth: return auth
    return jsonify(load_db()), 200

# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
