from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

# ---------------------------------------------
# Each package has its own valid keys
# ---------------------------------------------
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


# ---------------------------------------------------------
# /keys — same as before, but with package name verification
# ---------------------------------------------------------
@app.route('/keys', methods=['GET'])
def verify_key():
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package_name = request.args.get('package')

    # 🧩 Old style error handling
    if not key or not device_id or not package_name:
        return jsonify({"error": "Missing key or device ID"}), 400

    # ✅ Check if package exists
    if package_name not in valid_keys:
        return jsonify({"error": "Invalid package name"}), 401

    # ✅ Check if key exists in that package
    package_keys = valid_keys[package_name]
    if key not in package_keys:
        return jsonify({"error": "Invalid key"}), 401

    key_data = package_keys[key]

    # ✅ Device binding check (same as before)
    if key_data["is_used"] and key_data["device_id"] != device_id:
        return jsonify({"error": "Key already in use by another device"}), 403

    # ✅ Mark as used
    package_keys[key] = {
        "is_used": True,
        "device_id": device_id,
        "last_verified": datetime.now().isoformat()
    }

    # ✅ Old style success response
    return jsonify({
        "success": True,
        "message": "Key verified successfully"
    })


# ---------------------------------------------------------
# /ids — unchanged (same as before)
# ---------------------------------------------------------
@app.route('/ids', methods=['GET', 'POST'])
def manage_device_ids():
    if request.method == 'GET':
        devices = {
            f"{pkg}.{key}": data["device_id"]
            for pkg, keys in valid_keys.items()
            for key, data in keys.items() if data["is_used"]
        }
        return jsonify(devices)

    elif request.method == 'POST':
        device_id = request.data.decode('utf-8')
        key = request.args.get('key')
        package = request.args.get('package')

        if not device_id or not key or not package:
            return jsonify({"error": "Missing device ID, key, or package"}), 400

        if package not in valid_keys:
            return jsonify({"error": "Invalid package name"}), 401

        package_keys = valid_keys[package]
        if key not in package_keys:
            return jsonify({"error": "Invalid key"}), 401

        key_data = package_keys[key]

        if key_data["is_used"] and key_data["device_id"] != device_id:
            return jsonify({"error": "Key already in use"}), 403

        package_keys[key]["device_id"] = device_id
        package_keys[key]["is_used"] = True
        package_keys[key]["last_verified"] = datetime.now().isoformat()

        return jsonify({
            "message": "Device registered successfully",
            "key": key
        }), 201


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
