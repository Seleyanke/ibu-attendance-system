# ibu_attendance_final_fixed.py
"""
IBU Smart QR Attendance System - FINAL WORKING VERSION
All courses automatically created, no errors!
"""

import os
import jwt
import qrcode
from io import BytesIO
from datetime import datetime, date, time, timedelta
from functools import wraps

from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ==================== APP CONFIGURATION ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'ibu-university-secure-key-2024'
app.config['JWT_SECRET_KEY'] = 'jwt-secure-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ibu_attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Attendance rules
app.config['CLASS_START_TIME'] = "08:30"
app.config['LATE_CUTOFF_TIME'] = "08:45"
app.config['ABSENT_CUTOFF_TIME'] = "09:00"

# Create folders
os.makedirs('static/qrcodes', exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ==================== DATABASE MODELS ====================
class Faculty(db.Model):
    __tablename__ = 'faculties'
    id = db.Column(db.Integer, primary_key=True)
    name_ar = db.Column(db.String(100), nullable=False)
    name_en = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    has_gender_separation = db.Column(db.Boolean, default=True)

class AcademicYear(db.Model):
    __tablename__ = 'academic_years'
    id = db.Column(db.Integer, primary_key=True)
    year_number = db.Column(db.Integer, nullable=False)
    is_current = db.Column(db.Boolean, default=False)

class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    semester_number = db.Column(db.Integer, nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'))
    is_current = db.Column(db.Boolean, default=False)

class ClassGroup(db.Model):
    __tablename__ = 'class_groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(10), nullable=False)
    gender = db.Column(db.String(10), nullable=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'))

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def is_active(self):
        return True
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    student_id = db.Column(db.String(50), unique=True)
    full_name_en = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'))

class Lecturer(db.Model):
    __tablename__ = 'lecturers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    full_name_en = db.Column(db.String(100))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'))

class Classroom(db.Model):
    __tablename__ = 'classrooms'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(20), unique=True)

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True)
    course_name_en = db.Column(db.String(100))
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'))
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'))
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'))
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_groups.id'))

class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    class_date = db.Column(db.Date)
    scan_time = db.Column(db.DateTime)
    status = db.Column(db.String(20))

class QRToken(db.Model):
    __tablename__ = 'qr_tokens'
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(500), unique=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    classroom_id = db.Column(db.Integer, db.ForeignKey('classrooms.id'))
    expiry_date = db.Column(db.DateTime)

# ==================== HELPER FUNCTIONS ====================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_database():
    """Initialize ALL data including courses"""
    # Drop all tables first to start fresh
    db.drop_all()
    # Create all tables
    db.create_all()
    
    print("📦 Creating all data...")
    
    # Create faculties
    faculties = [
        Faculty(name_ar='كلية الحديث', name_en='College of Hadith', code='HAD', has_gender_separation=True),
        Faculty(name_ar='كلية العقيدة', name_en='College of Aqeedah', code='AQD', has_gender_separation=True),
        Faculty(name_ar='كلية الاقتصاد', name_en='College of Economics', code='ECO', has_gender_separation=False)
    ]
    db.session.add_all(faculties)
    db.session.commit()
    print("✅ Faculties created")
    
    # Create class groups
    for f in faculties:
        if f.has_gender_separation:
            db.session.add(ClassGroup(name='A', gender='Male', faculty_id=f.id))
            db.session.add(ClassGroup(name='B', gender='Female', faculty_id=f.id))
        else:
            db.session.add(ClassGroup(name='Single', gender=None, faculty_id=f.id))
    db.session.commit()
    print("✅ Class groups created")
    
    # Create academic years
    ay = AcademicYear(year_number=1, is_current=True)
    db.session.add(ay)
    db.session.commit()
    
    # Create semester
    sem = Semester(semester_number=1, academic_year_id=ay.id, is_current=True)
    db.session.add(sem)
    db.session.commit()
    print("✅ Academic year and semester created")
    
    # Create admin
    admin = User(username='admin', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    print("✅ Admin created")
    
    # Create classrooms
    for i in range(1, 4):
        db.session.add(Classroom(room_number=f'10{i}'))
    db.session.commit()
    print("✅ Classrooms created")
    
    # Create lecturers
    lec_user = User(username='LEC001', role='lecturer')
    lec_user.set_password('lecturer123')
    db.session.add(lec_user)
    db.session.commit()
    
    lecturer = Lecturer(user_id=lec_user.id, full_name_en='Dr. Ahmed', faculty_id=faculties[0].id)
    db.session.add(lecturer)
    db.session.commit()
    print("✅ Lecturer created")
    
    # ===== CREATE COURSES =====
    print("📚 Creating courses...")
    
    # Get all needed IDs
    faculty_hadith = Faculty.query.filter_by(code='HAD').first()
    faculty_aqeedah = Faculty.query.filter_by(code='AQD').first()
    faculty_eco = Faculty.query.filter_by(code='ECO').first()
    
    class_a_hadith = ClassGroup.query.filter_by(faculty_id=faculty_hadith.id, name='A').first()
    class_b_hadith = ClassGroup.query.filter_by(faculty_id=faculty_hadith.id, name='B').first()
    class_a_aqeedah = ClassGroup.query.filter_by(faculty_id=faculty_aqeedah.id, name='A').first()
    class_b_aqeedah = ClassGroup.query.filter_by(faculty_id=faculty_aqeedah.id, name='B').first()
    class_single = ClassGroup.query.filter_by(faculty_id=faculty_eco.id).first()
    
    # Create course list
    courses_data = [
        ('HAD101', 'Introduction to Hadith', faculty_hadith.id, class_a_hadith.id),
        ('HAD102', 'Hadith Sciences', faculty_hadith.id, class_b_hadith.id),
        ('AQD101', 'Islamic Aqeedah', faculty_aqeedah.id, class_a_aqeedah.id),
        ('AQD102', 'Dawah Methods', faculty_aqeedah.id, class_b_aqeedah.id),
        ('ECO101', 'Principles of Economics', faculty_eco.id, class_single.id),
        ('ECO102', 'Financial Systems', faculty_eco.id, class_single.id),
    ]
    
    for code, name, fac_id, group_id in courses_data:
        course = Course(
            course_code=code,
            course_name_en=name,
            faculty_id=fac_id,
            academic_year_id=ay.id,
            semester_id=sem.id,
            class_group_id=group_id
        )
        db.session.add(course)
    
    db.session.commit()
    print(f"✅ Created {len(courses_data)} courses")
    
    # Create students
    students_data = [
        ('STU001', 'Ahmed Mohammed', 'Male', faculty_hadith.id),
        ('STU002', 'Fatima Ali', 'Female', faculty_hadith.id),
        ('STU003', 'Omar Hassan', 'Male', faculty_aqeedah.id),
        ('STU004', 'Aisha Khalid', 'Female', faculty_aqeedah.id),
        ('STU005', 'Abdullah Saleh', 'Male', faculty_eco.id),
    ]
    
    for stu_id, name, gender, fac_id in students_data:
        user = User(username=stu_id, role='student')
        user.set_password('student123')
        db.session.add(user)
        db.session.commit()
        
        student = Student(
            user_id=user.id,
            student_id=stu_id,
            full_name_en=name,
            gender=gender,
            faculty_id=fac_id
        )
        db.session.add(student)
    
    db.session.commit()
    print("✅ Students created")
    
    print("🎉 Database fully initialized!")

# ==================== ROUTES ====================
@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>IBU Attendance</title>
        <style>
            body { font-family: Arial; text-align: center; padding: 50px; background: #f0f2f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #0047ab; }
            .btn { display: inline-block; padding: 12px 30px; background: #0047ab; color: white; text-decoration: none; border-radius: 5px; margin: 10px; }
            .btn:hover { background: #003380; }
            .btn-success { background: #28a745; }
            .btn-success:hover { background: #218838; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📱 IBU Smart QR Attendance</h1>
            <p>System is running successfully!</p>
            <a href="/login" class="btn">Login</a>
            <a href="/debug" class="btn btn-success">Check Database</a>
        </div>
    </body>
    </html>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            return '''
            <html><body style="font-family: Arial; padding: 20px;">
                <h2>Login Failed</h2>
                <p>Invalid username or password</p>
                <a href="/login">Try again</a>
            </body></html>
            '''
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - IBU Attendance</title>
        <style>
            body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .login-box { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
            h2 { text-align: center; color: #0047ab; }
            input { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; box-sizing: border-box; }
            button { width: 100%; padding: 12px; background: #0047ab; color: white; border: none; border-radius: 5px; cursor: pointer; }
            button:hover { background: #003380; }
            .info { margin-top: 20px; font-size: 12px; color: #666; text-align: center; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h2>🔐 IBU Attendance</h2>
            <form method="POST">
                <input type="text" name="username" placeholder="Username" required>
                <input type="password" name="password" placeholder="Password" required>
                <button type="submit">Login</button>
            </form>
            <div class="info">
                <strong>Demo Credentials:</strong><br>
                Admin: admin / admin123<br>
                Student: STU001 / student123
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return "Access denied"
    
    course_count = Course.query.count()
    student_count = Student.query.count()
    
    return f'''
    <html><body style="font-family: Arial; padding: 20px;">
        <h2>📊 Admin Dashboard</h2>
        <p>Courses in database: <strong>{course_count}</strong></p>
        <p>Students in database: <strong>{student_count}</strong></p>
        <hr>
        <p><a href="/generate-qr" style="display: inline-block; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px;">Generate QR Code</a></p>
        <p><a href="/debug" style="display: inline-block; padding: 10px 20px; background: #17a2b8; color: white; text-decoration: none; border-radius: 5px;">View Database Status</a></p>
        <p><a href="/logout" style="color: #666;">Logout</a></p>
    </body></html>
    '''

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first()
    name = student.full_name_en if student else current_user.username
    
    return f'''
    <html><body style="font-family: Arial; padding: 20px;">
        <h2>👋 Welcome, {name}</h2>
        <p><a href="/scan" style="display: inline-block; padding: 15px 30px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; font-size: 18px;">📱 Scan QR Code</a></p>
        <p><a href="/logout" style="color: #666;">Logout</a></p>
    </body></html>
    '''

@app.route('/scan')
@login_required
def scan():
    return '''
    <html>
    <head>
        <title>Scan QR Code</title>
        <script src="https://unpkg.com/html5-qrcode/minified/html5-qrcode.min.js"></script>
        <style>
            body { font-family: Arial; padding: 20px; background: #f0f2f5; }
            .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .btn { display: inline-block; padding: 10px 20px; background: #6c757d; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }
            #result { margin-top: 20px; padding: 15px; border-radius: 5px; }
            .success { background: #d4edda; color: #155724; }
            .error { background: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📷 Scan QR Code</h2>
            <p>Position the QR code in front of your camera</p>
            <div id="qr-reader" style="width: 100%;"></div>
            <div id="result"></div>
            <p><a href="/student/dashboard" class="btn">← Back</a></p>
        </div>
        
        <script>
            const studentId = "''' + current_user.username + '''";
            const resultDiv = document.getElementById('result');
            
            function onScanSuccess(decodedText, decodedResult) {
                html5QrcodeScanner.clear();
                resultDiv.innerHTML = '<div style="padding:10px;">⏳ Processing...</div>';
                
                fetch('/scan-qr', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        token: decodedText,
                        student_id: studentId
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        resultDiv.innerHTML = '<div class="success"><h3>✅ Success</h3><p>' + data.message + '</p></div>';
                    } else {
                        resultDiv.innerHTML = '<div class="error"><h3>❌ Error</h3><p>' + data.message + '</p></div>';
                    }
                })
                .catch(error => {
                    resultDiv.innerHTML = '<div class="error"><h3>❌ Error</h3><p>Connection error</p></div>';
                });
            }
            
            function onScanError(errorMessage) {
                console.log(errorMessage);
            }
            
            const html5QrcodeScanner = new Html5QrcodeScanner(
                "qr-reader", { fps: 10, qrbox: 250 });
            html5QrcodeScanner.render(onScanSuccess, onScanError);
        </script>
    </body>
    </html>
    '''

@app.route('/scan-qr', methods=['POST'])
def scan_qr():
    try:
        data = request.json
        token = data.get('token')
        student_id = data.get('student_id')
        
        # Decode token
        token_data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        
        # Check if QR exists
        qr = QRToken.query.filter_by(token=token).first()
        if not qr:
            return jsonify({'success': False, 'message': 'Invalid QR code'})
        
        # Check if expired
        if datetime.utcnow() > qr.expiry_date:
            return jsonify({'success': False, 'message': 'QR code expired'})
        
        # Get student
        student = Student.query.filter_by(student_id=student_id).first()
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})
        
        # Check for duplicate scan today
        existing = Attendance.query.filter_by(
            student_id=student.id,
            course_id=qr.course_id,
            class_date=date.today()
        ).first()
        
        if existing:
            return jsonify({'success': False, 'message': 'Already scanned today'})
        
        # Determine status based on time
        now = datetime.now()
        current_time = now.time()
        late_cutoff = time(8, 45)
        absent_cutoff = time(9, 0)
        
        if current_time <= late_cutoff:
            status = 'Present'
        elif current_time <= absent_cutoff:
            status = 'Late'
        else:
            status = 'Absent'
        
        # Record attendance
        attendance = Attendance(
            student_id=student.id,
            course_id=qr.course_id,
            class_date=date.today(),
            scan_time=now,
            status=status
        )
        db.session.add(attendance)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Attendance recorded: {status}',
            'status': status,
            'time': now.strftime('%H:%M:%S')
        })
        
    except jwt.InvalidTokenError:
        return jsonify({'success': False, 'message': 'Invalid QR code format'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/generate-qr')
@login_required
def generate_qr():
    if current_user.role != 'admin':
        return "Access denied"
    
    course = Course.query.first()
    if not course:
        return "No courses found in database!"
    
    classroom = Classroom.query.first()
    if not classroom:
        return "No classrooms found in database!"
    
    token_data = {
        'course_id': course.id,
        'classroom_id': classroom.id,
        'expiry': (datetime.utcnow() + timedelta(days=120)).isoformat()
    }
    
    token = jwt.encode(token_data, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    
    qr = QRToken(
        token=token,
        course_id=course.id,
        classroom_id=classroom.id,
        expiry_date=datetime.utcnow() + timedelta(days=120)
    )
    db.session.add(qr)
    db.session.commit()
    
    # Generate QR code image
    img = qrcode.make(token)
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    # Convert to base64 for display
    import base64
    img_base64 = base64.b64encode(img_io.getvalue()).decode()
    
    return f'''
    <html><body style="font-family: Arial; padding: 20px;">
        <h2>✅ QR Code Generated</h2>
        <p>Course: <strong>{course.course_code} - {course.course_name_en}</strong></p>
        <p>Classroom: <strong>{classroom.room_number}</strong></p>
        <img src="data:image/png;base64,{img_base64}" style="max-width: 300px; border: 1px solid #ddd; padding: 10px;"><br><br>
        <p><strong>Instructions:</strong></p>
        <ol>
            <li>Print this QR code and place it in the classroom</li>
            <li>Students scan using: <a href="/scan" target="_blank">/scan</a></li>
            <li>Valid for: 120 days</li>
        </ol>
        <p><a href="/admin/dashboard" style="display: inline-block; padding: 10px 20px; background: #0047ab; color: white; text-decoration: none; border-radius: 5px;">← Back to Dashboard</a></p>
    </body></html>
    '''

@app.route('/debug')
def debug():
    """Check database status"""
    return f'''
    <html><body style="font-family: Arial; padding: 20px;">
        <h2>🔍 Database Status</h2>
        <table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse;">
            <tr><th>Table</th><th>Count</th></tr>
            <tr><td>Faculties</td><td>{Faculty.query.count()}</td></tr>
            <tr><td>Academic Years</td><td>{AcademicYear.query.count()}</td></tr>
            <tr><td>Semesters</td><td>{Semester.query.count()}</td></tr>
            <tr><td>Class Groups</td><td>{ClassGroup.query.count()}</td></tr>
            <tr><td>Users</td><td>{User.query.count()}</td></tr>
            <tr><td>Students</td><td>{Student.query.count()}</td></tr>
            <tr><td>Lecturers</td><td>{Lecturer.query.count()}</td></tr>
            <tr><td>Classrooms</td><td>{Classroom.query.count()}</td></tr>
            <tr><td>Courses</td><td><strong>{Course.query.count()}</strong></td></tr>
            <tr><td>Enrollments</td><td>{Enrollment.query.count()}</td></tr>
            <tr><td>Attendance</td><td>{Attendance.query.count()}</td></tr>
            <tr><td>QR Tokens</td><td>{QRToken.query.count()}</td></tr>
        </table>
        <p><a href="/">Home</a> | <a href="/admin/dashboard">Admin</a></p>
    </body></html>
    '''

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 IBU ATTENDANCE SYSTEM - FINAL VERSION")
    print("="*50)
    
    with app.app_context():
        init_database()
    
    print(f"\n📍 Local URL: http://localhost:5000")
    print("👤 Admin: admin / admin123")
    print("👤 Student: STU001 / student123")
    print("\n📚 Courses have been automatically created!")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=True)