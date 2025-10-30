from flask import Flask, request, jsonify
import base64

app = Flask(__name__)

# The single allowed package (exact match)
ALLOWED_PACKAGE = "com.sahil.work"

EXPECTED_SIGNATURE = "BC:ED:D6:DE:6B:B0:3B:3B:1A:A3:49:DB:00:4E:97:D8:DA:F7:EC:FD:4E:20:24:84:37:6D:23:64:BE:C0:AA:BA"

valid_keys = {
    "com.sahil.work": {
        "dark": {"is_used": False, "device_id": None},
        "darkss": {"is_used": False, "device_id": None}
    }
}

def custom_decrypt(encoded_text: str) -> str:
    # same xor decryption used by the Android client
    key = ("xA9" + "fQ7" + "Ls2").encode('utf-8')
    try:
        data = base64.b64decode(encoded_text)
    except Exception:
        return ""  # invalid base64
    return "".join(chr(data[i] ^ key[i % len(key)]) for i in range(len(data)))

def verify_signature(sig_enc):
    try:
        return custom_decrypt(sig_enc) == EXPECTED_SIGNATURE
    except:
        return False

def normalize_param(p):
    # safe normalization: None -> "", strip whitespace
    if p is None:
        return ""
    return p.strip()

@app.route('/keys', methods=['GET'])
def verify_key():
    # read raw params
    key = normalize_param(request.args.get('key'))
    device_id = normalize_param(request.args.get('device_id'))
    package = normalize_param(request.args.get('package'))
    sig_enc = normalize_param(request.args.get('sig'))

    # debug logs to console so you can see what's arriving
    print("DEBUG /keys -> package(received): {!r}, key(received): {!r}, device_id(received): {!r}".format(package, key, device_id))

    if not key or not device_id or not package or not sig_enc:
        return jsonify({"error": "Missing parameters"}), 400

    if not verify_signature(sig_enc):
        return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

    # STRICT package check: must exactly equal ALLOWED_PACKAGE
    if package != ALLOWED_PACKAGE:
        # show what was expected vs received for debugging
        print("PACKAGE MISMATCH: expected={!r} received={!r}".format(ALLOWED_PACKAGE, package))
        return jsonify({"error": "PACKAGE NOT FOUND"}), 401

    # now safe to check key under that package
    if key not in valid_keys.get(package, {}):
        return jsonify({"error": "KEY NOT FOUND"}), 401

    entry = valid_keys[package][key]

    if entry["is_used"] and entry["device_id"] != device_id:
        return jsonify({"error": "KEY IS USED"}), 403

    entry["is_used"] = True
    entry["device_id"] = device_id

    return jsonify({"success": True, "message": "Key verified successfully"}), 200


@app.route('/ids', methods=['GET', 'POST'])
def handle_ids():
    if request.method == 'POST':
        device_id = request.data.decode('utf-8').strip()
        key = normalize_param(request.args.get('key'))
        package = normalize_param(request.args.get('package'))
        sig_enc = normalize_param(request.args.get('sig'))

        print("DEBUG /ids POST -> package(received): {!r}, key(received): {!r}, device_id(received): {!r}".format(package, key, device_id))

        if not device_id or not key or not package or not sig_enc:
            return jsonify({"error": "Missing parameters"}), 400

        if not verify_signature(sig_enc):
            return jsonify({"error": "SIGNATURE VERIFICATION FAILED"}), 403

        # Strict check here as well
        if package != ALLOWED_PACKAGE:
            print("PACKAGE MISMATCH (ids): expected={!r} received={!r}".format(ALLOWED_PACKAGE, package))
            return jsonify({"error": "PACKAGE NOT FOUND"}), 401

        if key not in valid_keys.get(package, {}):
            return jsonify({"error": "KEY NOT FOUND"}), 401

        valid_keys[package][key]["device_id"] = device_id
        valid_keys[package][key]["is_used"] = True

        return jsonify({"success": True, "message": "Device registered successfully"}), 201

    else:
        return jsonify(valid_keys), 200


if __name__ == '__main__':
    # debug=True prints reloader logs; use it while testing
    app.run(debug=True)
