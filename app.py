from flask import Flask, request, jsonify
from datetime import datetime
import base64
import logging

app = Flask(__name__)
# Set log level to easily see requests and startup messages
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION ---

# Expected signature for secure verification mode
EXPECTED_SIGNATURE = "A4:0D:A8:0A:59:D1:70:CA:A9:50:CF:15:C1:8C:45:4D:47:A3:9B:26:98:9D:8B:64:0E:CD:74:5B:A7:1B:F5:DC"

# Secure Key Pool: Nested by package name, requires signature check
SECURE_KEYS = {
    "com.sahil.work": {
        "dark": {"is_used": False, "device_id": None, "last_verified": None},
        "darkss": {"is_used": False, "device_id": None, "last_verified": None}
    },
    "com.hul.shikhar.rssm": {
        "d1": {"is_used": False, "device_id": None, "last_verified": None},
        "d2": {"is_used": False, "device_id": None, "last_verified": None}
}
}

# Simple Key Pool: Flat structure, used when package/signature are missing
SIMPLE_KEYS = {
    # Changed the duplicate key from your original snippet to be unique
    "G-0924-3841-A": {"is_used": False, "device_id": None, "last_verified": None},
    "G-0924-3841-B": {"is_used": False, "device_id": None, "last_verified": None}
}

# --- CRYPTOGRAPHY/SECURITY FUNCTIONS ---

def custom_decrypt(encoded_text: str) -> str:
    """Decrypts base64 encoded text using a simple XOR key."""
    # Key construction: "xA9" + "fQ7" + "Ls2"
    key = ("xA9" + "fQ7" + "Ls2").encode('utf-8')
    data = base64.b64decode(encoded_text)
    return "".join(chr(data[i] ^ key[i % len(key)]) for i in range(len(data)))

def verify_signature(sig_enc):
    """Checks if the decrypted signature matches the expected value."""
    try:
        decrypted_sig = custom_decrypt(sig_enc)
        return decrypted_sig == EXPECTED_SIGNATURE
    except Exception as e:
        logging.error(f"Signature decryption failed: {e}")
        return False

# --- API ENDPOINTS ---

@app.route('/keys', methods=['GET'])
def verify_key():
    """Verifies a key using either Secure Mode or Simple Mode."""
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig_enc = request.args.get('sig')

    # Determine if Simple Mode should be used
    is_simple_mode = not package or not sig_enc
    current_time = datetime.now().isoformat()

    if is_simple_mode:
        # --- SIMPLE MODE LOGIC ---
        logging.info("Attempting key verification in SIMPLE MODE.")
        if not key or not device_id:
            return jsonify({"error": "Missing key or device ID for simple verification"}), 400

        if key not in SIMPLE_KEYS:
            return jsonify({"error": "Invalid key"}), 401

        entry = SIMPLE_KEYS[key]

        # Check for device binding conflict
        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key is used by another device (Simple Mode)"}), 403

        # Bind the key
        entry["is_used"] = True
        entry["device_id"] = device_id
        entry["last_verified"] = current_time

        return jsonify({"success": True, "message": "Key verified successfully (Simple Mode)"}), 200

    else:
        # --- SECURE MODE LOGIC ---
        logging.info("Attempting key verification in SECURE MODE.")
        if not key or not device_id or not package or not sig_enc:
            # Should not happen in secure mode, but good to check
            return jsonify({"error": "Missing key, device_id, package, or sig for secure verification"}), 400

        if not verify_signature(sig_enc):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in SECURE_KEYS:
            return jsonify({"error": "PACKAGE NOT FOUND"}), 401

        if key not in SECURE_KEYS[package]:
            return jsonify({"error": "KEY NOT FOUND"}), 401

        entry = SECURE_KEYS[package][key]

        # Check for device binding conflict
        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "KEY IS USED by another device"}), 403

        # Bind the key
        entry["is_used"] = True
        entry["device_id"] = device_id
        entry["last_verified"] = current_time

        return jsonify({"success": True, "message": "Key verified successfully (Secure Mode)"}), 200


@app.route('/ids', methods=['POST'])
def register_device():
    """Binds a device ID to a key, using either Secure Mode or Simple Mode."""
    device_id = request.data.decode('utf-8')
    key = request.args.get('key')
    package = request.args.get('package')
    sig_enc = request.args.get('sig')

    # Determine if Simple Mode should be used
    is_simple_mode = not package or not sig_enc
    current_time = datetime.now().isoformat()

    if is_simple_mode:
        # --- SIMPLE MODE DEVICE REGISTRATION ---
        logging.info("Attempting device registration in SIMPLE MODE.")
        if not device_id or not key:
            return jsonify({"error": "Missing device ID or key for simple registration"}), 400

        if key not in SIMPLE_KEYS:
            return jsonify({"error": "Invalid key"}), 401

        entry = SIMPLE_KEYS[key]

        # Check for device binding conflict
        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key is used by another device (Simple Mode)"}), 403

        # Register the device
        entry["device_id"] = device_id
        entry["is_used"] = True
        entry["last_verified"] = current_time

        return jsonify({"message": "Device registered successfully (Simple Mode)", "key": key}), 201

    else:
        # --- SECURE MODE DEVICE REGISTRATION ---
        logging.info("Attempting device registration in SECURE MODE.")
        if not device_id or not key or not package or not sig_enc:
            return jsonify({"error": "Missing parameters"}), 400

        if not verify_signature(sig_enc):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in SECURE_KEYS or key not in SECURE_KEYS[package]:
            return jsonify({"error": "KEY/PACKAGE NOT FOUND"}), 401

        entry = SECURE_KEYS[package][key]

        # Check for device binding conflict
        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "KEY IS USED by another device"}), 403

        # Register the device
        entry["device_id"] = device_id
        entry["is_used"] = True
        entry["last_verified"] = current_time

        return jsonify({"success": True, "message": "Device registered successfully (Secure Mode)"}), 201


@app.route('/used_keys', methods=['GET'])
def get_used_keys():
    """Returns a list of all keys currently marked as used across both key pools."""
    used_keys_list = []

    # 1. Check Simple Keys
    for key, data in SIMPLE_KEYS.items():
        if data["is_used"]:
            used_keys_list.append({
                "key": key,
                "package": "Simple Mode (No Package)",
                "device_id": data["device_id"],
                "last_verified": data["last_verified"]
            })

    # 2. Check Secure Keys
    for package, keys in SECURE_KEYS.items():
        for key, data in keys.items():
            if data["is_used"]:
                used_keys_list.append({
                    "key": key,
                    "package": package,
                    "device_id": data["device_id"],
                    "last_verified": data["last_verified"]
                })

    return jsonify({"used_keys": used_keys_list}), 200


if __name__ == '__main__':
    # Running the application on a public host and port 5000 is common for deployment.
    app.run(host='0.0.0.0', port=5000, debug=True)
