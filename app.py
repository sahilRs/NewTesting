import os
import json
import base64
import time
import logging
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

DB_FILE = "keys_db.json"

# ---------------- DEFAULT DB ----------------
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


# ---------------- DB HELPERS ----------------
def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_db():
    # If file missing -> create from defaults
    if not os.path.exists(DB_FILE):
        save_db(DEFAULT_DB)
        return dict(DEFAULT_DB)  # return a copy

    try:
        with open(DB_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        # If corrupted -> overwrite with defaults
        save_db(DEFAULT_DB)
        return dict(DEFAULT_DB)

    # Self-heal missing top-level sections and missing default keys/packages
    for section in DEFAULT_DB:
        if section not in data or not isinstance(data[section], dict):
            data[section] = dict(DEFAULT_DB[section])
        else:
            # restore missing package entries
            for pkg_or_key in DEFAULT_DB[section]:
                if pkg_or_key not in data[section]:
                    data[section][pkg_or_key] = dict(DEFAULT_DB[section][pkg_or_key])

    # Persist any repairs
    save_db(data)
    return data


# Load DB into memory
db = load_db()


# ----------------- FORCE DOWNLOAD -----------------
def force_download(filepath, filename="keys_db.json"):
    with open(filepath, "rb") as f:
        data = f.read()
    resp = make_response(data)
    resp.headers.set("Content-Type", "application/octet-stream")
    resp.headers.set("Content-Disposition", f"attachment; filename={filename}")
    resp.headers.set("Content-Length", len(data))
    return resp


# ---------------- CRYPTO / SIGNATURE ----------------
def custom_decrypt(encoded_text: str) -> str:
    if not encoded_text:
        return ""
    key = XOR_KEY_STRING.encode("utf-8")
    # fix padding
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


# ----------------- API: add_keys (bulk) -----------------
@app.route("/add_keys", methods=["POST"])
def add_keys():
    """
    Request JSON:
    {
        "package": "com.example.pkg"   # optional -> if absent or empty, keys go to SIMPLE_KEYS
        "keys": ["k1", "k2", ...]      # list of keys to add
    }
    Response: auto-download of DB file (attachment)
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")

    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    global db
    db = load_db()  # reload to get fresh

    if not package:
        # Add into SIMPLE_KEYS
        for k in keys:
            db["SIMPLE_KEYS"][k] = {"is_used": False, "device_id": None, "last_verified": None}
    else:
        # Add into SECURE_KEYS[package]
        if package not in db["SECURE_KEYS"]:
            db["SECURE_KEYS"][package] = {}
        for k in keys:
            db["SECURE_KEYS"][package][k] = {"is_used": False, "device_id": None, "last_verified": None}

    save_db(db)
    return force_download(DB_FILE, "keys_db.json")


# ----------------- API: delete_keys (bulk) -----------------
@app.route("/delete_keys", methods=["POST"])
def delete_keys():
    """
    Request JSON:
    {
        "package": "com.example.pkg"   # optional -> if absent or empty, delete from SIMPLE_KEYS
        "keys": ["k1","k2", ...]       # list of keys to delete
    }
    Response: auto-download of DB file (attachment)
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")

    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    global db
    db = load_db()

    deleted = []
    not_found = []

    if not package:
        # delete from SIMPLE_KEYS
        for k in keys:
            if k in db["SIMPLE_KEYS"]:
                del db["SIMPLE_KEYS"][k]
                deleted.append(k)
            else:
                not_found.append(k)
    else:
        if package not in db["SECURE_KEYS"]:
            return jsonify({"error": "Package not found in SECURE_KEYS"}), 404
        for k in keys:
            if k in db["SECURE_KEYS"][package]:
                del db["SECURE_KEYS"][package][k]
                deleted.append(k)
            else:
                not_found.append(k)
        # if package becomes empty, remove package entry
        if package in db["SECURE_KEYS"] and not db["SECURE_KEYS"][package]:
            del db["SECURE_KEYS"][package]

    save_db(db)
    return force_download(DB_FILE, "keys_db.json")


# ----------------- API: add single key (compat) -----------------
@app.route("/add_key", methods=["POST"])
def add_key():
    """
    Request JSON:
    { "package": "...", "key": "k1" }   # package optional -> SIMPLE_KEYS if missing
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

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
    """
    Request JSON:
    { "package": "...", "key": "k1" }   # package optional -> SIMPLE_KEYS if missing
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

    global db
    db = load_db()

    if not package:
        if key in db["SIMPLE_KEYS"]:
            del db["SIMPLE_KEYS"][key]
            save_db(db)
            return force_download(DB_FILE, "keys_db.json")
        else:
            return jsonify({"error": "Key not found in SIMPLE_KEYS"}), 404
    else:
        if package in db["SECURE_KEYS"] and key in db["SECURE_KEYS"][package]:
            del db["SECURE_KEYS"][package][key]
            # remove empty package
            if not db["SECURE_KEYS"][package]:
                del db["SECURE_KEYS"][package]
            save_db(db)
            return force_download(DB_FILE, "keys_db.json")
        else:
            return jsonify({"error": "Key not found in SECURE_KEYS for this package"}), 404


# ----------------- API: keys verification (GET) -----------------
@app.route("/keys", methods=["GET"])
def handle_keys():
    """
    Example:
    GET /keys?key=k1&device_id=dev123            -> simple mode
    GET /keys?key=k1&device_id=dev123&package=com.pkg&sig=ENC_SIG  -> secure mode (requires sig)
    """
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
    """
    POST /ids?key=k1&package=com.pkg&sig=ENC_SIG
    Body: raw device_id (plain text)
    """
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
    if not os.path.exists(DB_FILE):
        save_db(DEFAULT_DB)
    return force_download(DB_FILE, "keys_db.json")


# ----------------- API: upload DB (restore after redeploy) -----------------
@app.route("/upload_db", methods=["POST"])
def upload_db():
    if "file" not in request.files:
        return jsonify({"error": "File missing"}), 400
    file = request.files["file"]
    file.save(DB_FILE)
    # reload in-memory db
    global db
    db = load_db()
    return jsonify({"success": True, "message": "Database restored successfully"}), 200


# ----------------- API: list all (debug) -----------------
@app.route("/list_all", methods=["GET"])
def list_all():
    global db
    db = load_db()
    return jsonify(db), 200


# ----------------- API: reset DB to defaults -----------------
@app.route("/reset_db", methods=["POST"])
def reset_db():
    save_db(DEFAULT_DB)
    global db
    db = load_db()
    return jsonify({"success": True, "message": "DB reset to default"}), 200


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
