import os
import json
import base64
import time
import logging
from flask import Flask, request, jsonify

# --- Logging setup ---
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

# Expected signature (server-side stored)
EXPECTED_SIGNATURE = "1D:03:E2:BD:74:A8:FB:B3:2D:B8:28:F1:16:7B:CC:56:3C:F1:AD:B4:CA:16:8B:6F:FD:D4:08:43:92:41:B3:0C"

# XOR KEY
XOR_KEY_STRING = "xA9fQ7Ls2"


# ------------------- JSON DB FUNCTIONS ------------------------

def load_db():
    """Load JSON database, create if not exists."""
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f:
            json.dump({"packages": {}, "simple_keys": {}}, f, indent=4)

    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(data):
    """Save JSON database."""
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)


# ------------------- CRYPTO FUNCTIONS ------------------------

def custom_decrypt(encoded_text: str) -> str:
    key = XOR_KEY_STRING.encode('utf-8')

    missing_padding = len(encoded_text) % 4
    if missing_padding:
        encoded_text += '=' * (4 - missing_padding)

    try:
        data = base64.b64decode(encoded_text)
    except Exception as e:
        logging.error(f"Base64 decoding failed: {e}")
        return ""

    decrypted_chars = [chr(data[i] ^ key[i % len(key)]) for i in range(len(data))]
    return "".join(decrypted_chars)


def verify_signature(sig_enc):
    try:
        decrypted_sig = custom_decrypt(sig_enc)
        normalized_decrypted_sig = decrypted_sig.strip().rstrip('=')
        normalized_expected_sig = EXPECTED_SIGNATURE.strip().rstrip('=')

        return normalized_decrypted_sig == normalized_expected_sig

    except Exception as e:
        logging.error(f"Signature verification failed: {e}")
        return False


# ------------------- ADD KEYS API ----------------------------
# ------------------- DELETE KEYS API ------------------------

@app.route('/delete_keys', methods=['POST'])
def delete_keys():
    data = request.json
    package = data.get("package")
    keys = data.get("keys")

    if not package or not keys:
        return jsonify({"error": "Missing 'package' or 'keys'"}), 400

    db = load_db()

    if package not in db["packages"]:
        return jsonify({"error": "Package not found"}), 404

    deleted = []
    not_found = []

    for key in keys:
        if key in db["packages"][package]:
            del db["packages"][package][key]
            deleted.append(key)
        else:
            not_found.append(key)

    # If package becomes empty -> delete package section
    if len(db["packages"][package]) == 0:
        del db["packages"][package]

    save_db(db)

    return jsonify({
        "success": True,
        "package": package,
        "deleted_keys": deleted,
        "not_found_keys": not_found
    }), 200

@app.route('/add_keys', methods=['POST'])
def add_keys():
    data = request.json
    package = data.get("package")
    keys = data.get("keys")

    if not package or not keys:
        return jsonify({"error": "Missing 'package' or 'keys'"}), 400

    db = load_db()

    # Create package section if missing
    if package not in db["packages"]:
        db["packages"][package] = {}

    added, skipped = [], []

    for key in keys:
        if key in db["packages"][package]:
            skipped.append(key)
        else:
            db["packages"][package][key] = {
                "is_used": False,
                "device_id": None,
                "last_verified": None
            }
            added.append(key)

    save_db(db)

    return jsonify({
        "success": True,
        "package": package,
        "added_keys": added,
        "already_exists": skipped
    }), 200


# ------------------- KEYS VERIFICATION ------------------------

@app.route('/keys', methods=['GET'])
def handle_keys():
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig = request.args.get('sig')

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    db = load_db()

    # Secure mode (package + signature required)
    is_secure = package and sig

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in db["packages"] or key not in db["packages"][package]:
            return jsonify({"error": "Invalid key or package"}), 401

        entry = db["packages"][package][key]

    else:  # Simple mode
        if key not in db["simple_keys"]:
            return jsonify({"error": "Invalid simple key"}), 401

        entry = db["simple_keys"][key]

    # Key already used by someone else
    if entry["is_used"] and entry["device_id"] != device_id:
        return jsonify({"error": "Key already in use"}), 403

    # First time use
    entry["is_used"] = True
    entry["device_id"] = device_id
    entry["last_verified"] = time.time()

    save_db(db)

    return jsonify({"success": True, "message": "Key Verified"}), 200


# ------------------- DEVICE REGISTRATION ------------------------

@app.route('/ids', methods=['POST'])
def handle_ids():
    key = request.args.get("key")
    package = request.args.get("package")
    sig = request.args.get("sig")

    try:
        device_id = request.data.decode('utf-8').strip()
    except:
        device_id = None

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    db = load_db()
    is_secure = package and sig

    if is_secure:
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in db["packages"] or key not in db["packages"][package]:
            return jsonify({"error": "Invalid key/package"}), 401

        entry = db["packages"][package][key]
    else:
        if key not in db["simple_keys"]:
            return jsonify({"error": "Invalid simple key"}), 401

        entry = db["simple_keys"][key]

    if entry["is_used"] and entry["device_id"] != device_id:
        return jsonify({"error": "Key already registered to another device"}), 403

    entry["is_used"] = True
    entry["device_id"] = device_id
    entry["last_verified"] = time.time()

    save_db(db)

    return jsonify({"success": True, "message": "Device Registered"}), 200


# ------------------- USED KEYS LIST ------------------------

@app.route('/used_keys', methods=['GET'])
def used_keys():
    db = load_db()

    used_secure = {}
    used_simple = {}

    for package, keys in db["packages"].items():
        for key, data in keys.items():
            if data["is_used"]:
                used_secure.setdefault(package, {})[key] = data

    for key, data in db["simple_keys"].items():
        if data["is_used"]:
            used_simple[key] = data

    return jsonify({
        "used_secure_keys": used_secure,
        "used_simple_keys": used_simple
    }), 200


# ------------------- DEBUG SIGNATURE ------------------------

@app.route('/debug_sig', methods=['GET'])
def debug_sig():
    sig = request.args.get('sig')

    if not sig:
        return jsonify({"error": "sig missing"}), 400

    decrypted = custom_decrypt(sig)

    return jsonify({
        "encrypted_input": sig,
        "xor_key": XOR_KEY_STRING,
        "decrypted": decrypted,
        "expected": EXPECTED_SIGNATURE
    }), 200


# ------------------- RUN SERVER ------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
