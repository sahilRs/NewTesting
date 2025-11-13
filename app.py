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


@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()

    # Validate input
    if not data or 'school_id' not in data or 'class_id' not in data:
        return jsonify({"status": "failed", "reason": "missing_parameters"}), 400

    school_id = data['school_id']
    class_id = str(data['class_id']).strip()

    # Step 1: Verify school_id
    if school_id != VALID_SCHOOL_ID:
        return jsonify({"status": "failed", "reason": "invalid_school_id"}), 401

    # Step 2: Verify class_id
    if class_id not in STUDENT_DATABASE:
        return jsonify({"status": "failed", "reason": "invalid_class_id"}), 401

    # Step 3: Return student list
    students = STUDENT_DATABASE[class_id]
    return jsonify({"status": "success", "class_id": class_id, "students": students}), 200


# --- Run Application ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
