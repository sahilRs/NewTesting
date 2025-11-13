from flask import Flask, request, jsonify
import os
import json

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
                "student_number": "9801234567"
            },
            {
                "student_name": "ANITA SINGH",
                "student_class": "9",
                "student_fathername": "SURESH SINGH",
                "student_mothername": "KAVITA SINGH",
                "student_rollno": 12,
                "student_address": "DELHI, INDIA",
                "student_number": "9812345678"
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
                "student_number": "95026367272"
            },
            {
                "student_name": "MOHIT VERMA",
                "student_class": "12",
                "student_fathername": "ARUN VERMA",
                "student_mothername": "GEETA VERMA",
                "student_rollno": 29,
                "student_address": "NOIDA, INDIA",
                "student_number": "9810098100"
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

# --- Verify Route ---
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

# --- Add Student Route ---
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
        "student_number": data.get("student_number")
    }

    db[class_id].append(new_student)
    save_db(db)
    return jsonify({"status": "success", "student": new_student}), 200

# --- Run Server ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
