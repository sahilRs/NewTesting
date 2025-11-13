from flask import Flask, request, jsonify
import os

app = Flask(__name__)

# --- Dummy Database ---
VALID_SCHOOL_ID = "SCHL123"

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

# --- Verify Route ---
@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()

    if not data or 'school_id' not in data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_parameters"}), 400

    school_id = data['school_id']
    class_id = str(data['class_id']).strip()

    if school_id != VALID_SCHOOL_ID:
        return jsonify({"status": "failed", "reason": "invalid_school_id"}), 401

    if class_id not in STUDENT_DATABASE:
        return jsonify({"status": "failed", "reason": "invalid_class_id"}), 401

    students = STUDENT_DATABASE[class_id]
    return jsonify({"status": "success", "class_id": class_id, "students": students}), 200

# --- Datashow Route ---
@app.route('/datashow90', methods=['POST'])
def datashow90():
    data = request.get_json()

    if not data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_class_id"}), 400

    class_id = str(data['class_id']).strip()

    if class_id not in STUDENT_DATABASE:
        return jsonify({"status": "failed", "reason": "invalid_class_id"}), 404

    return jsonify({
        "status": "success",
        "class_id": class_id,
        "students": STUDENT_DATABASE[class_id]
    }), 200

# --- New Route: Add Students ---
@app.route('/addstudents67', methods=['POST'])
def addstudents67():
    data = request.get_json()

    required_fields = [
        "student_name",
        "student_class",
        "student_fathername",
        "student_mothername",
        "student_rollno",
        "student_address",
        "student_number"
    ]

    if not data or not all(field in data for field in required_fields):
        return jsonify({"status": "failed", "reason": "missing_parameters"}), 400

    class_id = str(data["student_class"]).strip()

    # If class does not exist, create it
    if class_id not in STUDENT_DATABASE:
        STUDENT_DATABASE[class_id] = []

    # Check for duplicate roll number
    for student in STUDENT_DATABASE[class_id]:
        if student["student_rollno"] == data["student_rollno"]:
            return jsonify({"status": "failed", "reason": "duplicate_rollno"}), 409

    # Add new student
    new_student = {
        "student_name": data["student_name"],
        "student_class": data["student_class"],
        "student_fathername": data["student_fathername"],
        "student_mothername": data["student_mothername"],
        "student_rollno": data["student_rollno"],
        "student_address": data["student_address"],
        "student_number": data["student_number"]
    }

    STUDENT_DATABASE[class_id].append(new_student)

    return jsonify({"status": "success", "message": "student_added", "student": new_student}), 200

# --- Run Application ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
