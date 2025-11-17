import os
import json
import base64
import time
import logging
import sqlite3
from flask import Flask, request, jsonify, make_response

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

# --- filenames (keep keys_db.json for compatibility with original clients) ---
DB_JSON_FILE = "keys_db.json"   # returned by endpoints exactly as before
DB_SQLITE_FILE = "keys.db"      # internal authoritative store to avoid corruption

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


# ---------------- PASSWORDS (as requested) ----------------
PASS_DELETE = "HJSPCH"
PASS_ADD = "JDJDODO"
PASS_DOWNLOAD = "JDKDXPCHE"
PASS_UPLOAD = "DJJDJSDPS"


# ---------------- SQLite helpers (authoritative store) ----------------
def init_sqlite():
    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS secure_keys (
            package TEXT NOT NULL,
            key_value TEXT NOT NULL,
            is_used INTEGER DEFAULT 0,
            device_id TEXT,
            last_verified REAL,
            PRIMARY KEY (package, key_value)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS simple_keys (
            key_value TEXT PRIMARY KEY,
            is_used INTEGER DEFAULT 0,
            device_id TEXT,
            last_verified REAL
        )
    """)
    con.commit()
    con.close()


def sql_load_from_json_if_needed():
    """
    If sqlite DB empty and keys_db.json exists, load it.
    If neither exists, create both from DEFAULT_DB.
    Always ensure JSON snapshot exists.
    """
    init_sqlite()
    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    # check whether DB has data
    cur.execute("SELECT COUNT(*) FROM simple_keys")
    simple_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM secure_keys")
    secure_count = cur.fetchone()[0]

    if (simple_count == 0 and secure_count == 0) and os.path.exists(DB_JSON_FILE):
        # try to load JSON into sqlite
        try:
            with open(DB_JSON_FILE, "r") as f:
                j = json.load(f)
            # load simple
            for k, v in j.get("SIMPLE_KEYS", {}).items():
                cur.execute("INSERT OR REPLACE INTO simple_keys(key_value,is_used,device_id,last_verified) VALUES(?,?,?,?)",
                            (k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
            # load secure
            for pkg, keys in j.get("SECURE_KEYS", {}).items():
                for k, v in keys.items():
                    cur.execute("INSERT OR REPLACE INTO secure_keys(package,key_value,is_used,device_id,last_verified) VALUES(?,?,?,?,?)",
                                (pkg, k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
            con.commit()
        except Exception:
            # fallback to defaults
            write_json_snapshot(DEFAULT_DB)
            load_defaults_into_sqlite(DEFAULT_DB)
    elif (simple_count == 0 and secure_count == 0) and not os.path.exists(DB_JSON_FILE):
        # create both from defaults
        write_json_snapshot(DEFAULT_DB)
        load_defaults_into_sqlite(DEFAULT_DB)

    con.close()
    # ensure json snapshot exists and in sync
    write_json_snapshot(sqlite_to_json())


def load_defaults_into_sqlite(dbobj):
    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()
    for k, v in dbobj.get("SIMPLE_KEYS", {}).items():
        cur.execute("INSERT OR REPLACE INTO simple_keys(key_value,is_used,device_id,last_verified) VALUES(?,?,?,?)",
                    (k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
    for pkg, keys in dbobj.get("SECURE_KEYS", {}).items():
        for k, v in keys.items():
            cur.execute("INSERT OR REPLACE INTO secure_keys(package,key_value,is_used,device_id,last_verified) VALUES(?,?,?,?,?)",
                        (pkg, k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
    con.commit()
    con.close()


def sqlite_to_json():
    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()
    out = {"SECURE_KEYS": {}, "SIMPLE_KEYS": {}}
    cur.execute("SELECT key_value,is_used,device_id,last_verified FROM simple_keys")
    for row in cur.fetchall():
        k, is_used, device_id, last_verified = row
        out["SIMPLE_KEYS"][k] = {"is_used": bool(is_used), "device_id": device_id, "last_verified": last_verified}
    cur.execute("SELECT package,key_value,is_used,device_id,last_verified FROM secure_keys")
    for row in cur.fetchall():
        pkg, k, is_used, device_id, last_verified = row
        if pkg not in out["SECURE_KEYS"]:
            out["SECURE_KEYS"][pkg] = {}
        out["SECURE_KEYS"][pkg][k] = {"is_used": bool(is_used), "device_id": device_id, "last_verified": last_verified}
    con.close()
    return out


def write_json_snapshot(data_obj):
    # write to JSON exactly as the original code expected
    try:
        with open(DB_JSON_FILE, "w") as f:
            json.dump(data_obj, f, indent=4)
        return True
    except Exception as e:
        logging.exception("Failed to write JSON snapshot: %s", e)
        return False


def update_snapshot_from_sqlite():
    j = sqlite_to_json()
    write_json_snapshot(j)


# Initialize on startup (preserve original JSON logic)
sql_load_from_json_if_needed()


# ----------------- FORCE DOWNLOAD (preserve original behavior) -----------------
def force_download(filepath, filename="keys_db.json"):
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
        # match original logic: strip and rstrip "="
        return dec.strip().rstrip("=") == EXPECTED_SIGNATURE.strip().rstrip("=")
    except Exception:
        return False


# ----------------- API: add_keys (bulk) -----------------
@app.route("/add_keys", methods=["POST"])
def add_keys():
    # password required (exact behavior requested)
    if request.headers.get("X-PASS") != PASS_ADD:
        return jsonify({"error": "Invalid password"}), 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")
    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    if not package:
        for k in keys:
            cur.execute("INSERT OR IGNORE INTO simple_keys(key_value,is_used,device_id,last_verified) VALUES(?,0,NULL,NULL)", (k,))
    else:
        for k in keys:
            cur.execute("INSERT OR IGNORE INTO secure_keys(package,key_value,is_used,device_id,last_verified) VALUES(?,?,?,?,?)",
                        (package, k, 0, None, None))

    con.commit()
    con.close()

    # update json snapshot to maintain original behaviour for downloads
    update_snapshot_from_sqlite()
    return force_download(DB_JSON_FILE, "keys_db.json")


# ----------------- API: delete_keys (bulk) -----------------
@app.route("/delete_keys", methods=["POST"])
def delete_keys():
    # password required
    if request.headers.get("X-PASS") != PASS_DELETE:
        return jsonify({"error": "Invalid password"}), 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    package = data.get("package")
    keys = data.get("keys")
    if not keys or not isinstance(keys, list):
        return jsonify({"error": "Provide 'keys' as a non-empty list"}), 400

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    deleted = []
    not_found = []

    if not package:
        for k in keys:
            cur.execute("SELECT 1 FROM simple_keys WHERE key_value=?", (k,))
            if cur.fetchone():
                cur.execute("DELETE FROM simple_keys WHERE key_value=?", (k,))
                deleted.append(k)
            else:
                not_found.append(k)
    else:
        cur.execute("SELECT 1 FROM secure_keys WHERE package=?", (package,))
        # if package not found -> 404 like original expectation
        cur.execute("SELECT COUNT(*) FROM secure_keys WHERE package=?", (package,))
        if cur.fetchone()[0] == 0:
            con.close()
            return jsonify({"error": "Package not found in SECURE_KEYS"}), 404

        for k in keys:
            cur.execute("SELECT 1 FROM secure_keys WHERE package=? AND key_value=?", (package, k))
            if cur.fetchone():
                cur.execute("DELETE FROM secure_keys WHERE package=? AND key_value=?", (package, k))
                deleted.append(k)
            else:
                not_found.append(k)

        # remove package entry if empty (in sqlite that's automatic)
        # but ensure any zero rows remain not present

    con.commit()
    con.close()

    update_snapshot_from_sqlite()
    return force_download(DB_JSON_FILE, "keys_db.json")


# ----------------- API: add single key (compat) -----------------
@app.route("/add_key", methods=["POST"])
def add_key():
    # keep compatibility; require same add password
    if request.headers.get("X-PASS") != PASS_ADD:
        return jsonify({"error": "Invalid password"}), 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    if not package:
        cur.execute("INSERT OR IGNORE INTO simple_keys(key_value,is_used,device_id,last_verified) VALUES(?,0,NULL,NULL)", (key,))
    else:
        cur.execute("INSERT OR IGNORE INTO secure_keys(package,key_value,is_used,device_id,last_verified) VALUES(?,?,?,?,?)",
                    (package, key, 0, None, None))

    con.commit()
    con.close()

    update_snapshot_from_sqlite()
    return force_download(DB_JSON_FILE, "keys_db.json")


# ----------------- API: delete single key (compat) -----------------
@app.route("/delete_key", methods=["POST"])
def delete_key():
    # require delete password
    if request.headers.get("X-PASS") != PASS_DELETE:
        return jsonify({"error": "Invalid password"}), 403

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    package = data.get("package")
    key = data.get("key")
    if not key:
        return jsonify({"error": "key is required"}), 400

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    if not package:
        cur.execute("SELECT 1 FROM simple_keys WHERE key_value=?", (key,))
        if cur.fetchone():
            cur.execute("DELETE FROM simple_keys WHERE key_value=?", (key,))
            con.commit()
            con.close()
            update_snapshot_from_sqlite()
            return force_download(DB_JSON_FILE, "keys_db.json")
        else:
            con.close()
            return jsonify({"error": "Key not found in SIMPLE_KEYS"}), 404
    else:
        cur.execute("SELECT 1 FROM secure_keys WHERE package=? AND key_value=?", (package, key))
        if cur.fetchone():
            cur.execute("DELETE FROM secure_keys WHERE package=? AND key_value=?", (package, key))
            # remove package if empty (no extra action needed)
            con.commit()
            con.close()
            update_snapshot_from_sqlite()
            return force_download(DB_JSON_FILE, "keys_db.json")
        else:
            con.close()
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

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()

    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            con.close()
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        cur.execute("SELECT is_used,device_id FROM secure_keys WHERE package=? AND key_value=?", (package, key))
    else:
        cur.execute("SELECT is_used,device_id FROM simple_keys WHERE key_value=?", (key,))

    row = cur.fetchone()
    if not row:
        con.close()
        return jsonify({"error": "Invalid key or package (secure mode)" if is_secure else "Invalid simple key"}), 401

    entry_is_used, entry_device = row

    if entry_is_used and entry_device != device_id:
        con.close()
        return jsonify({"error": "Key already in use by another device"}), 403

    # register/verify (preserve original behavior)
    now = time.time()
    if is_secure:
        cur.execute("UPDATE secure_keys SET is_used=1,device_id=?,last_verified=? WHERE package=? AND key_value=?",
                    (device_id, now, package, key))
    else:
        cur.execute("UPDATE simple_keys SET is_used=1,device_id=?,last_verified=? WHERE key_value=?",
                    (device_id, now, key))

    con.commit()
    con.close()

    update_snapshot_from_sqlite()
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

    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()
    is_secure = bool(package and sig)

    if is_secure:
        if not verify_signature(sig):
            con.close()
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403
        cur.execute("SELECT is_used,device_id FROM secure_keys WHERE package=? AND key_value=?", (package, key))
    else:
        cur.execute("SELECT is_used,device_id FROM simple_keys WHERE key_value=?", (key,))

    row = cur.fetchone()
    if not row:
        con.close()
        return jsonify({"error": "Invalid key/package (secure mode)" if is_secure else "Invalid simple key"}), 401

    entry_is_used, entry_device = row
    if entry_is_used and entry_device != device_id:
        con.close()
        return jsonify({"error": "Key already registered to another device"}), 403

    now = time.time()
    if is_secure:
        cur.execute("UPDATE secure_keys SET is_used=1,device_id=?,last_verified=? WHERE package=? AND key_value=?",
                    (device_id, now, package, key))
    else:
        cur.execute("UPDATE simple_keys SET is_used=1,device_id=?,last_verified=? WHERE key_value=?",
                    (device_id, now, key))

    con.commit()
    con.close()
    update_snapshot_from_sqlite()
    return jsonify({"success": True, "message": "Device registered/verified"}), 200


# ----------------- API: download DB manually (preserve original behavior) -----------------
@app.route("/download_db", methods=["GET"])
def download_db():
    if request.headers.get("X-PASS") != PASS_DOWNLOAD:
        return jsonify({"error": "Invalid password"}), 403
    # ensure snapshot up-to-date
    update_snapshot_from_sqlite()
    if not os.path.exists(DB_JSON_FILE):
        write_json_snapshot(DEFAULT_DB)
    return force_download(DB_JSON_FILE, "keys_db.json")


# ----------------- API: upload DB (restore after redeploy) -----------------
@app.route("/upload_db", methods=["POST"])
def upload_db():
    if request.headers.get("X-PASS") != PASS_UPLOAD:
        return jsonify({"error": "Invalid password"}), 403

    if "file" not in request.files:
        return jsonify({"error": "File missing"}), 400
    file = request.files["file"]
    # save JSON snapshot
    file.save(DB_JSON_FILE)

    # reload sqlite from JSON snapshot (preserve original JSON content)
    try:
        with open(DB_JSON_FILE, "r") as f:
            j = json.load(f)
    except Exception:
        return jsonify({"error": "Uploaded file is not valid JSON"}), 400

    # wipe sqlite and load new
    init_sqlite()
    con = sqlite3.connect(DB_SQLITE_FILE)
    cur = con.cursor()
    cur.execute("DELETE FROM simple_keys")
    cur.execute("DELETE FROM secure_keys")
    con.commit()

    # load contents
    for k, v in j.get("SIMPLE_KEYS", {}).items():
        cur.execute("INSERT OR REPLACE INTO simple_keys(key_value,is_used,device_id,last_verified) VALUES(?,?,?,?)",
                    (k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
    for pkg, keys in j.get("SECURE_KEYS", {}).items():
        for k, v in keys.items():
            cur.execute("INSERT OR REPLACE INTO secure_keys(package,key_value,is_used,device_id,last_verified) VALUES(?,?,?,?,?)",
                        (pkg, k, int(v.get("is_used", False)), v.get("device_id"), v.get("last_verified")))
    con.commit()
    con.close()

    return jsonify({"success": True, "message": "Database restored successfully"}), 200


# ----------------- API: list all (debug) -----------------
@app.route("/list_all", methods=["GET"])
def list_all():
    # Password check
    if request.headers.get("X-PASS") != "Xksps":
        return jsonify({"error": "Invalid password"}), 403

    j = sqlite_to_json()
    return jsonify(j), 200
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
    # ensure sqlite/json initialized
    sql_load_from_json_if_needed()
    app.run(host="0.0.0.0", port=5000, debug=False)
