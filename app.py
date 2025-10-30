import base64
import time
import logging
from flask import Flask, request, jsonify

# --- Configuration and Initialization ---

# Logging setup (console + file)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding="utf-8")
    ]
)

app = Flask(__name__)

# Expected signature (your real app signing cert hash)
EXPECTED_SIGNATURE = "A4:0D:A8:0A:59:D1:70:CA:A9:50:CF:15:C1:8C:45:4D:47:A3:9B:26:98:9D:8B:64:0E:CD:74:5B:A7:1B:F5:DC"

# XOR key used for signature encryption/decryption
XOR_KEY_STRING = "xA9fQ7Ls2"

# Secure key pool
SECURE_KEYS = {
    "com.hul.shikhar.rssm": {
        "d1": {"is_used": False, "device_id": None, "last_verified": None},
        "d2": {"is_used": False, "device_id": None, "last_verified": None}
    },
    "com.sahil.work": {
        "s1": {"is_used": False, "device_id": None, "last_verified": None},
        "s2": {"is_used": False, "device_id": None, "last_verified": None}
    }
}

# Simple key pool
SIMPLE_KEYS = {
    "G-0924-3841-A": {"is_used": False, "device_id": None, "last_verified": None},
    "G-0924-3841-B": {"is_used": False, "device_id": None, "last_verified": None}
}

# --- Cryptography Functions ---

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

        if normalized_decrypted_sig == normalized_expected_sig:
            return True
        else:
            logging.error(f"❌ SIGNATURE MISMATCH! Expected: '{normalized_expected_sig}' | Got: '{normalized_decrypted_sig}'")
            return False
    except Exception as e:
        logging.error(f"Signature verification failed: {e}")
        return False


# --- API Endpoints ---

@app.route('/keys', methods=['GET'])
def handle_keys():
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig = request.args.get('sig')

    if not key or not device_id:
        return jsonify({"error": "Missing 'key' or 'device_id'"}), 400

    is_secure_mode = package and sig

    if is_secure_mode:
        logging.debug(f"Attempting key verification for key={key} in SECURE MODE.")
        
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in SECURE_KEYS or key not in SECURE_KEYS[package]:
            return jsonify({"error": "Invalid key or package"}), 401

        entry = SECURE_KEYS[package][key]

        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key is used by another device (Secure Mode)"}), 403

        if not entry["is_used"]:
            entry["is_used"] = True
            entry["device_id"] = device_id
            logging.info(f"Key {key} registered to device {device_id}")

        entry["last_verified"] = time.time()

        return jsonify({
            "success": True,
            "message": "Key verified successfully (Secure Mode)"
        }), 200

    else:
        logging.debug(f"Attempting key verification for key={key} in SIMPLE MODE.")

        if key not in SIMPLE_KEYS:
            return jsonify({"error": "Invalid key"}), 401

        entry = SIMPLE_KEYS[key]

        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key is used by another device (Simple Mode)"}), 403

        if not entry["is_used"]:
            entry["is_used"] = True
            entry["device_id"] = device_id
            logging.info(f"Simple key {key} registered to device {device_id}")

        entry["last_verified"] = time.time()

        return jsonify({
            "success": True,
            "message": "Key verified successfully (Simple Mode)"
        }), 200


@app.route('/debug_sig', methods=['GET'])
def debug_signature():
    sig = request.args.get('sig')
    if not sig:
        return jsonify({"error": "Missing 'sig' parameter"}), 400

    decrypted_sig = custom_decrypt(sig)
    normalized_sig = decrypted_sig.strip().rstrip('=')

    return jsonify({
        "encrypted_input": sig,
        "XOR_KEY_STRING": XOR_KEY_STRING,
        "decrypted_raw": decrypted_sig,
        "decrypted_normalized": normalized_sig,
        "expected_signature": EXPECTED_SIGNATURE
    }), 200


@app.route('/ids', methods=['POST'])
def handle_ids():
    key = request.args.get('key')
    package = request.args.get('package')
    sig = request.args.get('sig')

    try:
        device_id = request.data.decode('utf-8').strip()
    except Exception:
        device_id = None

    if not key or not device_id:
        return jsonify({"error": "Missing key or device_id"}), 400

    # --- Determine mode ---
    is_secure_mode = package and sig

    if is_secure_mode:
        logging.debug(f"Attempting device registration for key={key} in SECURE MODE.")

        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in SECURE_KEYS or key not in SECURE_KEYS[package]:
            return jsonify({"error": "Invalid key or package"}), 401

        entry = SECURE_KEYS[package][key]

        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key already registered to another device (Secure Mode)"}), 403

        # Register / verify
        entry["is_used"] = True
        entry["device_id"] = device_id
        entry["last_verified"] = time.time()
        logging.info(f"Secure key {key} registered to {device_id}")

        return jsonify({
            "success": True,
            "message": "Device registered/verified successfully (Secure Mode)"
        }), 200

    else:
        logging.debug(f"Attempting device registration for key={key} in SIMPLE MODE.")

        if key not in SIMPLE_KEYS:
            return jsonify({"error": "Invalid key"}), 401

        entry = SIMPLE_KEYS[key]

        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key already registered to another device (Simple Mode)"}), 403

        # Register / verify
        entry["is_used"] = True
        entry["device_id"] = device_id
        entry["last_verified"] = time.time()
        logging.info(f"Simple key {key} registered to {device_id}")

        return jsonify({
            "success": True,
            "message": "Device registered/verified successfully (Simple Mode)"
        }), 200


# ✅ NEW ENDPOINT: Show used keys (Secure + Simple)
@app.route('/used_keys', methods=['GET'])
def show_used_keys():
    """Show all used keys for both secure and simple pools."""
    used_secure = {}
    used_simple = {}

    # Secure keys
    for package, keys in SECURE_KEYS.items():
        for key_name, data in keys.items():
            if data["is_used"]:
                used_secure.setdefault(package, {})[key_name] = data

    # Simple keys
    for key_name, data in SIMPLE_KEYS.items():
        if data["is_used"]:
            used_simple[key_name] = data

    return jsonify({
        "used_secure_keys": used_secure,
        "used_simple_keys": used_simple
    }), 200


# --- Run Application ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
