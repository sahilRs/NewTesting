from flask import Flask, request, jsonify
from datetime import datetime
import base64

app = Flask(__name__)

EXPECTED_SIGNATURE = "BC:ED:D6:DE:6B:B0:3B:3B:1A:A3:49:DB:00:4E:97:D8:DA:F7:EC:FD:4E:20:24:84:37:6D:23:64:BE:C0:AA:BA"

valid_keys = {
    "com.sahil.work": {
        "dark": {"is_used": False, "device_id": None},
        "darkss": {"is_used": False, "device_id": None}
    }
}

def custom_decrypt(encoded_text: str) -> str:
    key = ("xA9" + "fQ7" + "Ls2").encode('utf-8')
    data = base64.b64decode(encoded_text)
    return "".join(chr(data[i] ^ key[i % len(key)]) for i in range(len(data)))

def verify_signature(sig_enc):
    try:
        return custom_decrypt(sig_enc) == EXPECTED_SIGNATURE
    except:
        return False

@app.route('/keys', methods=['GET'])
def verify_key():
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig_enc = request.args.get('sig')

    if not key or not device_id or not package or not sig_enc:
        return jsonify({"error": "Missing parameters"}), 400

    if not verify_signature(sig_enc):
        return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

    if package not in valid_keys:
        return jsonify({"error": "PACKAGE NOT FOUND"}), 401

    if key not in valid_keys[package]:
        return jsonify({"error": "KEY NOT FOUND"}), 401

    entry = valid_keys[package][key]
    if entry["is_used"] and entry["device_id"] != device_id:
        return jsonify({"error": "KEY IS USED"}), 403

    entry["is_used"] = True
    entry["device_id"] = device_id

    return jsonify({"success": True, "message": "Key verified successfully"}), 200


# ✅ POST = register, GET = list registered
@app.route('/ids', methods=['GET', 'POST'])
def handle_ids():
    if request.method == 'POST':
        # Register new device
        device_id = request.data.decode('utf-8')
        key = request.args.get('key')
        package = request.args.get('package')
        sig_enc = request.args.get('sig')

        if not device_id or not key or not package or not sig_enc:
            return jsonify({"error": "Missing parameters"}), 400

        if not verify_signature(sig_enc):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        if package not in valid_keys or key not in valid_keys[package]:
            return jsonify({"error": "KEY/PACKAGE NOT FOUND"}), 401

        valid_keys[package][key]["device_id"] = device_id
        valid_keys[package][key]["is_used"] = True

        return jsonify({"success": True, "message": "Device registered successfully"}), 201

    else:
        # Return all keys with device IDs
        return jsonify(valid_keys), 200


if __name__ == '__main__':
    app.run(debug=True)
