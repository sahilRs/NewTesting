from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

DB_FILE = "students_db.json"

# --- Initialize DB if it doesn't exist ---
if not os.path.exists(DB_FILE):

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
        "student_number": data.get("student_number")
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

    # Create empty list for new class
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
