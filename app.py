from flask import Flask, request, jsonify
from datetime import datetime
import base64

app = Flask(__name__)

EXPECTED_SIGNATURE = "BC:ED:D6:DE:6B:B0:3B:3B:1A:A3:49:DB:00:4E:97:D8:DA:F7:EC:FD:4E:20:24:84:37:6D:23:64:BE:C0:AA:BA"

valid_keys = {
    "com.sahil.work": {
        "dark": {"is_used": False, "device_id": None, "last_verified": None},
        "darkss": {"is_used": False, "device_id": None, "last_verified": None}
    },
    "com.dark": {
        "gggg": {"is_used": False, "device_id": None, "last_verified": None},
        "hhhh": {"is_used": False, "device_id": None, "last_verified": None}
    }
}

def custom_decrypt(encoded_text: str) -> str:
    p1 = "xA9"
    p2 = "fQ7"
    p3 = "Ls2"
    key = (p1 + p2 + p3).encode('utf-8')

    data = base64.b64decode(encoded_text)
    out = bytearray()
    for i in range(len(data)):
        out.append(data[i] ^ key[i % len(key)])
    return out.decode('utf-8')

def verify_signature(sig_enc):
    try:
        signature_plain = custom_decrypt(sig_enc)
    except:
        return False
    return signature_plain == EXPECTED_SIGNATURE

@app.route('/keys', methods=['GET'])
def verify_key():
    key = request.args.get('key')
    device_id = request.args.get('device_id')
    package = request.args.get('package')
    sig_enc = request.args.get('sig')

    if not key or not device_id or not package or not sig_enc:
        return jsonify({"error": "Missing parameters"}), 400

    # signature check HAR CASE ME SAME ERROR
    if not verify_signature(sig_enc):
        return jsonify({"error": "Verification failed"}), 403

    if package not in valid_keys:
        return jsonify({"error": "Invalid package"}), 401

    if key not in valid_keys[package]:
        return jsonify({"error": "Key does not belong to this app"}), 401

    key_data = valid_keys[package][key]
    if key_data["is_used"] and key_data["device_id"] != device_id:
        return jsonify({"error": "Key already in use"}), 403

    valid_keys[package][key] = {
        "is_used": True,
        "device_id": device_id,
        "last_verified": datetime.now().isoformat()
    }

    return jsonify({"success": True, "message": "Key verified successfully"}), 200

@app.route('/ids', methods=['POST'])
def register_device():
    device_id = request.data.decode('utf-8')
    key = request.args.get('key')
    package = request.args.get('package')
    sig_enc = request.args.get('sig')

    if not device_id or not key or not package or not sig_enc:
        return jsonify({"error": "Missing parameters"}), 400

    if not verify_signature(sig_enc):
        return jsonify({"error": "Verification failed"}), 403

    if package not in valid_keys or key not in valid_keys[package]:
        return jsonify({"error": "Invalid key or package"}), 401

    key_data = valid_keys[package][key]
    if key_data["is_used"] and key_data["device_id"] != device_id:
        return jsonify({"error": "Key already in use"}), 403

    valid_keys[package][key]["device_id"] = device_id
    valid_keys[package][key]["is_used"] = True
    valid_keys[package][key]["last_verified"] = datetime.now().isoformat()

    return jsonify({"message": "Device registered successfully", "key": key}), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
