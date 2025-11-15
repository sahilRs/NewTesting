from flask import Flask, request, jsonify
import os
import json
import base64

app = Flask(__name__)

DB_FILE = "students_db.json"

# --- Initialize DB if it doesn't exist ---
if not os.path.exists(DB_FILE):
    STUDENT_DATABASE = {
        "9": [
            {
                "student_name": "RAVI KUMAR",
                "student_class": "9",
                "student_fathername": "RAKESH KUMAR",
                "student_mothername": "PRIYA KUMARI",
                "student_rollno": 11,
                "student_address": "PATNA, INDIA",
                "student_number": "9801234567",
                "student_image": "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"  # empty base64
            },
            {
                "student_name": "ANITA SINGH",
                "student_class": "9",
                "student_fathername": "SURESH SINGH",
                "student_mothername": "KAVITA SINGH",
                "student_rollno": 12,
                "student_address": "DELHI, INDIA",
                "student_number": "9812345678",
                "student_image": ""
            }
        ],
        "12": [
            {
                "student_name": "SAHIL ALAM",
                "student_class": "12",
                "student_fathername": "TESTF",
                "student_mothername": "TESTM",
                "student_rollno": 28,
                "student_address": "DELHI, INDIA",
                "student_number": "95026367272",
                "student_image": ""
            }
        ]
    }
    with open(DB_FILE, "w") as f:
        json.dump(STUDENT_DATABASE, f, indent=4)

# --- Helper functions ---
def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

# --- Verify School ID and Class ---
@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()
    if not data or 'school_id' not in data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_parameters"}), 400

    school_id = data['school_id']
    class_id = str(data['class_id']).strip()
    VALID_SCHOOL_ID = "SCHL123"

    if school_id != VALID_SCHOOL_ID:
        return jsonify({"status": "failed", "reason": "invalid_school_id"}), 401

    db = load_db()
    if class_id not in db:
        return jsonify({"status": "failed", "reason": "invalid_class_id"}), 401

    return jsonify({"status": "success", "class_id": class_id, "students": db[class_id]}), 200

# --- Show all students in a class ---
@app.route('/datashow90', methods=['POST'])
def datashow90():
    data = request.get_json()
    if not data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_class_id"}), 400

    class_id = str(data['class_id']).strip()
    db = load_db()
    if class_id not in db:
        return jsonify({"status": "failed", "reason": "invalid_class_id"}), 404

    return jsonify({"status": "success", "class_id": class_id, "students": db[class_id]}), 200

# --- Add new student ---
@app.route('/addstudents67', methods=['POST'])
def add_student():
    data = request.get_json()
    class_id = str(data.get("class_id")).strip()
    db = load_db()

    if class_id not in db:
        db[class_id] = []

    new_student = {
        "student_name": data.get("student_name"),
        "student_class": class_id,
        "student_fathername": data.get("student_fathername"),
        "student_mothername": data.get("student_mothername"),
        "student_rollno": int(data.get("student_rollno")),
        "student_address": data.get("student_address"),
        "student_number": data.get("student_number"),
        "student_image": data.get("student_image", "")  # optional Base64 image
    }

    db[class_id].append(new_student)
    save_db(db)
    return jsonify({"status": "success", "student": new_student}), 200

# --- Add new class ---
@app.route('/addclass90', methods=['POST'])
def add_class():
    data = request.get_json()
    if not data or 'school_id' not in data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_parameters"}), 400

    school_id = data.get("school_id")
    class_id = str(data.get("class_id")).strip()
    VALID_SCHOOL_ID = "SCHL123"

    if school_id != VALID_SCHOOL_ID:
        return jsonify({"status": "failed", "reason": "invalid_school_id"}), 401

    db = load_db()
    if class_id in db:
        return jsonify({"status": "failed", "reason": "class_already_exists"}), 409

    db[class_id] = []
    save_db(db)
    return jsonify({"status": "success", "class_id": class_id}), 200

# --- Update student ---
@app.route('/updateStudent90', methods=['POST'])
def update_student():
    data = request.get_json()
    school_id = data.get("school_id")
    class_id = str(data.get("class_id")).strip()
    rollno = int(data.get("student_rollno"))

    if school_id != "SCHL123":
        return jsonify({"status":"failed","reason":"invalid_school_id"}),401

    db = load_db()
    if class_id not in db:
        return jsonify({"status":"failed","reason":"invalid_class_id"}),404

    for student in db[class_id]:
        if student["student_rollno"] == rollno:
            student["student_name"] = data.get("student_name")
            student["student_fathername"] = data.get("student_fathername")
            student["student_mothername"] = data.get("student_mothername")
            student["student_address"] = data.get("student_address")
            student["student_number"] = data.get("student_number")
            student["student_image"] = data.get("student_image", student.get("student_image",""))
            save_db(db)
            return jsonify({"status":"success"}),200

    return jsonify({"status":"failed","reason":"student_not_found"}),404

# --- Delete student ---
@app.route('/deleteStudent90', methods=['POST'])
def delete_student():
    data = request.get_json()
    school_id = data.get("school_id")
    class_id = str(data.get("class_id")).strip()
    rollno = int(data.get("student_rollno"))

    if school_id != "SCHL123":
        return jsonify({"status":"failed","reason":"invalid_school_id"}),401

    db = load_db()
    if class_id not in db:
        return jsonify({"status":"failed","reason":"invalid_class_id"}),404

    db[class_id] = [s for s in db[class_id] if s["student_rollno"] != rollno]
    save_db(db)
    return jsonify({"status":"success"}),200

# --- Run Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
