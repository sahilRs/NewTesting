import base64
import time
import logging
from flask import Flask, request, jsonify

# --- Configuration and Initialization ---

# Set up logging for better error diagnosis
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# The expected signature that the client sends. This MUST be the SHA-256 hash 
# of the official signing certificate, formatted as a colon-separated hex string.
# DO NOT CHANGE THIS unless your app's signing key is updated.
EXPECTED_SIGNATURE = "A4:0D:A8:0A:59:D1:70:CA:A9:50:CF:15:C1:8C:45:4D:47:A3:9B:26:98:9D:8B:64:0E:CD:74:5B:A7:1B:F5:DC"

# The XOR key used for client encryption/server decryption.
XOR_KEY_STRING = "xA9fQ7Ls2" 

# Secure Key Pool: Keys requiring matching package and valid signature.
# Use this pool for your keys like 'd1'.
SECURE_KEYS = {
    # Existing Package
    "com.hul.shikhar.rssm": {
        "d1": {"is_used": False, "device_id": None, "last_verified": None},
        "d2": {"is_used": False, "device_id": None, "last_verified": None}
    },
    # 🎯 NEW PACKAGE ADDED HERE
    "com.sahil.work": {
        "s1": {"is_used": False, "device_id": None, "last_verified": None},
        "s2": {"is_used": False, "device_id": None, "last_verified": None}
    }
}

# Simple Key Pool: Keys requiring only the key and device_id (no package/sig).
# Use this pool for your 'SIMPLE_KEYS'.
SIMPLE_KEYS = {
    "G-0924-3841-A": {"is_used": False, "device_id": None, "last_verified": None},
    "G-0924-3841-B": {"is_used": False, "device_id": None, "last_verified": None}
}

# --- Cryptography Functions ---

def custom_decrypt(encoded_text: str) -> str:
    key = XOR_KEY_STRING.encode('utf-8')
    
    # Fix: re-add missing Base64 padding
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
    """
    Checks if the decrypted signature matches the expected value, 
    making it robust against client Base64 padding and whitespace.
    """
    global EXPECTED_SIGNATURE
    
    try:
        decrypted_sig = custom_decrypt(sig_enc)

        # 🎯 FIX: Normalize both strings before comparison. 
        # This strips all whitespace and trailing '=' from the decrypted signature.
        normalized_decrypted_sig = decrypted_sig.strip().rstrip('=')
        normalized_expected_sig = EXPECTED_SIGNATURE.strip().rstrip('=')

        if normalized_decrypted_sig == normalized_expected_sig:
            return True
        else:
            logging.error(f"❌ SIGNATURE MISMATCH! Expected: '{normalized_expected_sig}' | Received: '{normalized_decrypted_sig}'")
            return False

    except Exception as e:
        logging.error(f"Signature verification failed unexpectedly: {e}")
        return False

# --- API Endpoints ---

@app.route('/keys', methods=['GET'])
def handle_keys():
    """Handles key verification and device key lookup."""
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig = request.args.get('sig')

    # 1. Parameter Check
    if not key or not device_id:
        return jsonify({"error": "Missing 'key' or 'device_id'"}), 400

    # 2. Determine Mode
    is_secure_mode = package and sig
    
    if is_secure_mode:
        logging.debug(f"Attempting key verification for key={key} in SECURE MODE.")
        
        # 3. Secure Mode Logic
        if not verify_signature(sig):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        # Check if package exists, then check if key exists within package
        if package not in SECURE_KEYS or key not in SECURE_KEYS[package]:
            logging.warning(f"Key/Package not found in SECURE_KEYS: package={package}, key={key}")
            return jsonify({"error": "Invalid key or package"}), 401

        entry = SECURE_KEYS[package][key]

        if entry["is_used"] and entry["device_id"] != device_id:
            # Check for existing use
            logging.warning(f"Key {key} used by different device: {entry['device_id']}")
            return jsonify({"error": "Key is used by another device (Secure Mode)"}), 403

        # Update and succeed
        if not entry["is_used"]:
             entry["is_used"] = True
             entry["device_id"] = device_id
             logging.info(f"Key {key} registered to new device {device_id}")

        entry["last_verified"] = time.time()
        
        return jsonify({
            "success": True, 
            "message": "Key verified successfully (Secure Mode)"
        }), 200

    else:
        logging.debug(f"Attempting key verification for key={key} in SIMPLE MODE.")

        # 4. Simple Mode Logic
        if key not in SIMPLE_KEYS:
            # If it's not a SIMPLE key, it's immediately invalid in this mode
            return jsonify({"error": "Invalid key"}), 401

        entry = SIMPLE_KEYS[key]
        
        if entry["is_used"] and entry["device_id"] != device_id:
            return jsonify({"error": "Key is used by another device (Simple Mode)"}), 403

        # Update and succeed
        if not entry["is_used"]:
             entry["is_used"] = True
             entry["device_id"] = device_id
             logging.info(f"Simple Key {key} registered to new device {device_id}")

        entry["last_verified"] = time.time()

        return jsonify({
            "success": True, 
            "message": "Key verified successfully (Simple Mode)"
        }), 200

@app.route('/debug_sig', methods=['GET'])
def debug_signature():
    """TEMPORARY DEBUG: Decrypts and returns the raw signature string for checking."""
    sig = request.args.get('sig')
    if not sig:
        return jsonify({"error": "Missing 'sig' parameter"}), 400

    decrypted_sig = custom_decrypt(sig)
    
    # Also show the normalized version to confirm the stripping works
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
    """Handles device key registration (Secure Mode POST method from client)."""
    
    # 1. Get Parameters from URL
    key = request.args.get('key')
    package = request.args.get('package')
    sig = request.args.get('sig')
    
    # 2. Get device_id from POST body
    try:
        device_id = request.data.decode('utf-8').strip()
    except Exception:
        device_id = None

    # 3. Check Mode and Parameters
    if not key or not package or not sig or not device_id:
        return jsonify({"error": "Missing key, package, sig in URL or device_id in body"}), 400

    logging.debug(f"Attempting key registration for key={key} in SECURE MODE (POST).")

    # 4. Secure Mode Logic (Signature & Key Check)
    if not verify_signature(sig):
        return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

    # Check if package exists, then check if key exists within package
    if package not in SECURE_KEYS or key not in SECURE_KEYS[package]:
        return jsonify({"error": "Invalid key or package"}), 401

    entry = SECURE_KEYS[package][key]

    if entry["is_used"] and entry["device_id"] != device_id:
        return jsonify({"error": "Key is already registered to a different device"}), 403

    # 5. Success: Register/Update Key
    entry["is_used"] = True
    entry["device_id"] = device_id
    entry["last_verified"] = time.time()
    
    logging.info(f"Key {key} successfully registered/re-verified for device {device_id}")

    return jsonify({
        "success": True, 
        "message": "Device registered/verified successfully (Secure Mode)"
    }), 200


# --- Run Application ---

if __name__ == '__main__':
    # Running in debug mode is generally NOT recommended for production/live servers
    # but is useful for initial testing.
    app.run(host='0.0.0.0', port=5000, debug=True)
