from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ===========================================
# PACKAGE → KEYS (1 KEY = 1 DEVICE)
# ===========================================
valid_keys = {
    "com.sahil.worl": {
        "dark": {"is_used": False, "device_id": None, "last_verified": None},
        "darkss": {"is_used": False, "device_id": None, "last_verified": None}
    },
    "com.dark": {
        "gggg": {"is_used": False, "device_id": None, "last_verified": None},
        "hhhh": {"is_used": False, "device_id": None, "last_verified": None}
    }
}

# ===========================================
# VERIFY KEY (APP LAUNCH)
# ===========================================
@app.route('/keys', methods=['GET'])
def verify_key():
    package = request.args.get('package')
    key = request.args.get('key')
    device_id = request.args.get('device_id')

    if not package or not key or not device_id:
        return jsonify({"error": "Missing package, key or device_id"}), 400

    if package not in valid_keys:
        return jsonify({"error": "Invalid package"}), 401

    if key not in valid_keys[package]:
        return jsonify({"error": "Invalid key for this package"}), 401

    key_data = valid_keys[package][key]

    # ✅ HARD ONE DEVICE LOCK
    if key_data["device_id"] is not None and key_data["device_id"] != device_id:
        return jsonify({"error": "KEY LOCKED TO ANOTHER DEVICE"}), 403

    # First time bind
    if key_data["device_id"] is None:
        valid_keys[package][key]["device_id"] = device_id

    valid_keys[package][key]["is_used"] = True
    valid_keys[package][key]["last_verified"] = datetime.now().isoformat()

    return jsonify({"success": True, "message": "Key verified successfully"})

# ===========================================
# REGISTER DEVICE (FIRST LOGIN)
# ===========================================
@app.route('/ids', methods=['POST'])
def register_device():
    package = request.args.get('package')
    key = request.args.get('key')
    device_id = request.data.decode('utf-8')

    if not package or not key or not device_id:
        return jsonify({"error": "Missing package, key or device_id"}), 400

    if package not in valid_keys or key not in valid_keys[package]:
        return jsonify({"error": "Invalid package or key"}), 401

    key_data = valid_keys[package][key]

    # ✅ Prevent use on another device
    if key_data["device_id"] is not None and key_data["device_id"] != device_id:
        return jsonify({"error": "KEY ALREADY LINKED TO ANOTHER DEVICE"}), 403

    valid_keys[package][key]["device_id"] = device_id
    valid_keys[package][key]["is_used"] = True
    valid_keys[package][key]["last_verified"] = datetime.now().isoformat()

    return jsonify({"message": "Device registered successfully"}), 201


# ===========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
