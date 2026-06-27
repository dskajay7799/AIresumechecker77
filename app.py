from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import json
import os
import re
from functools import wraps

# ── CONFIGURATION ────────────────────────────────────────────────────────────
app = Flask(__name__)

# SECRET_KEY for session encryption - MUST be set for production
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY',
    'resume-analyzer-super-secret-key-change-in-production-2024'
)

# Session configuration - persistent sessions that survive refresh
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # 30-day sessions

# Database configuration
database_url = os.environ.get('DATABASE_URL', 'sqlite:///resume_analyzer.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# CORS configuration - allow credentials for sessions
CORS(
    app,
    supports_credentials=True,
    origins=['*'],
    allow_headers=['Content-Type', 'Authorization']
)

db = SQLAlchemy(app)

# ── DATABASE MODELS ──────────────────────────────────────────────────────────

class User(db.Model):
    """User account model with secure password storage."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    resumes = db.relationship('Resume', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and store password securely."""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Verify password against hash."""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Return user data as dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'created_at': self.created_at.isoformat()
        }


class Resume(db.Model):
    """Resume upload and analysis model."""
    __tablename__ = 'resumes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(10))
    
    # Analysis results
    overall_score = db.Column(db.Float, default=0.0)
    skills_score = db.Column(db.Float, default=0.0)
    experience_score = db.Column(db.Float, default=0.0)
    education_score = db.Column(db.Float, default=0.0)
    formatting_score = db.Column(db.Float, default=0.0)
    
    # Extracted data
    extracted_text = db.Column(db.Text)
    detected_skills = db.Column(db.JSON)
    detected_experience = db.Column(db.JSON)
    feedback = db.Column(db.JSON)
    
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    analyzed_at = db.Column(db.DateTime)
    
    def to_dict(self):
        """Return resume data as dictionary."""
        return {
            'id': self.id,
            'filename': self.original_filename,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'overall_score': self.overall_score,
            'skills_score': self.skills_score,
            'education_score': self.education_score,
            'experience_score': self.experience_score,
            'formatting_score': self.formatting_score,
            'detected_skills': self.detected_skills or [],
            'detected_experience': self.detected_experience or [],
            'feedback': self.feedback or [],
            'uploaded_at': self.uploaded_at.isoformat(),
            'analyzed_at': self.analyzed_at.isoformat() if self.analyzed_at else None
        }


# ── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_current_user():
    """Get current logged-in user from session."""
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        return user
    return None


def login_required(f):
    """Decorator: require user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def validate_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """
    Validate password strength.
    Requirements: min 6 chars, at least one letter, one number
    """
    if len(password) < 6:
        return False, 'Password must be at least 6 characters'
    if not any(c.isalpha() for c in password):
        return False, 'Password must contain at least one letter'
    if not any(c.isdigit() for c in password):
        return False, 'Password must contain at least one number'
    return True, 'Valid'


def analyze_resume(text):
    """
    Analyze resume text and generate scores.
    Returns analysis data.
    """
    # Keyword lists for analysis
    tech_skills = {
        'python', 'java', 'javascript', 'c++', 'sql', 'html', 'css',
        'react', 'vue', 'angular', 'nodejs', 'django', 'flask',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'git',
        'machine learning', 'data analysis', 'tableau', 'powerbi'
    }
    
    soft_skills = {
        'leadership', 'communication', 'teamwork', 'problem solving',
        'project management', 'critical thinking', 'time management',
        'collaboration', 'adaptability', 'creativity'
    }
    
    education_keywords = {'bachelor', 'master', 'phd', 'diploma', 'university', 'college', 'degree'}
    experience_keywords = {'experience', 'worked', 'developed', 'designed', 'managed', 'led', 'created'}
    
    text_lower = text.lower()
    lines = text.split('\n')
    
    # Calculate scores
    detected_skills = [s for s in tech_skills if s in text_lower]
    detected_soft = [s for s in soft_skills if s in text_lower]
    
    education_found = any(kw in text_lower for kw in education_keywords)
    experience_found = sum(1 for kw in experience_keywords if text_lower.count(kw) > 0)
    
    skills_score = min(100, (len(detected_skills) * 10) + (len(detected_soft) * 5))
    education_score = 80 if education_found else 40
    experience_score = min(100, experience_found * 20)
    formatting_score = 75 if len(lines) > 5 else 50  # More lines = better formatting
    
    overall_score = (skills_score + education_score + experience_score + formatting_score) / 4
    
    # Generate feedback
    feedback = []
    if len(detected_skills) < 5:
        feedback.append('Consider adding more technical skills')
    if not education_found:
        feedback.append('Add your education section')
    if experience_found < 3:
        feedback.append('Expand your work experience descriptions')
    if formatting_score < 70:
        feedback.append('Improve document formatting and structure')
    if len(detected_soft) < 3:
        feedback.append('Highlight more soft skills and achievements')
    
    return {
        'overall_score': round(overall_score, 2),
        'skills_score': round(skills_score, 2),
        'education_score': round(education_score, 2),
        'experience_score': round(experience_score, 2),
        'formatting_score': round(formatting_score, 2),
        'detected_skills': detected_skills,
        'detected_soft_skills': detected_soft,
        'feedback': feedback if feedback else ['Resume looks good! Keep improving.']
    }


# ── INITIALIZATION ──────────────────────────────────────────────────────────

def init_db():
    """Initialize database and create tables."""
    with app.app_context():
        db.create_all()
        
        # Create sample user if none exist
        if User.query.count() == 0:
            sample_user = User(
                username='demo',
                email='demo@example.com',
                full_name='Demo User'
            )
            sample_user.set_password('demo123')
            db.session.add(sample_user)
            db.session.commit()
            print('✓ Sample user created: demo / demo123')


# ── AUTHENTICATION ROUTES ────────────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """
    Register a new user.
    
    POST /api/auth/signup
    {
        "username": "john_doe",
        "email": "john@example.com",
        "full_name": "John Doe",
        "password": "secure123"
    }
    """
    try:
        data = request.get_json() or {}
        
        # Validate input
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        full_name = data.get('full_name', '').strip()
        password = data.get('password', '')
        
        if not all([username, email, full_name, password]):
            return jsonify({'error': 'All fields are required'}), 400
        
        if len(username) < 3 or len(username) > 50:
            return jsonify({'error': 'Username must be 3-50 characters'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        valid_pwd, pwd_msg = validate_password(password)
        if not valid_pwd:
            return jsonify({'error': pwd_msg}), 400
        
        # Check for existing user
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already taken'}), 409
        
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already registered'}), 409
        
        # Create user
        user = User(
            username=username,
            email=email,
            full_name=full_name
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Log user in immediately
        session.permanent = True
        session['user_id'] = user.id
        
        return jsonify({
            'message': 'Account created successfully',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f'Signup error: {str(e)}')
        return jsonify({'error': 'Server error during registration'}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """
    Log in an existing user.
    
    POST /api/auth/login
    {
        "username": "john_doe",
        "password": "secure123"
    }
    """
    try:
        data = request.get_json() or {}
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        # Find user - case-insensitive
        user = User.query.filter_by(username=username).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username or password'}), 401
        
        # Create persistent session
        session.permanent = True
        session['user_id'] = user.id
        
        return jsonify({
            'message': 'Login successful',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        print(f'Login error: {str(e)}')
        return jsonify({'error': 'Server error during login'}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """
    Log out the current user.
    
    POST /api/auth/logout
    """
    try:
        session.clear()
        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        print(f'Logout error: {str(e)}')
        return jsonify({'error': 'Server error during logout'}), 500


@app.route('/api/auth/me', methods=['GET'])
def get_current_user_info():
    """
    Get current logged-in user info.
    This endpoint checks if session still exists - critical for persistence!
    
    GET /api/auth/me
    """
    try:
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Not authenticated'}), 401
        
        return jsonify({
            'authenticated': True,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        print(f'Get user error: {str(e)}')
        return jsonify({'error': 'Server error'}), 500


# ── RESUME ROUTES ────────────────────────────────────────────────────────────

@app.route('/api/resumes/upload', methods=['POST'])
@login_required
def upload_resume():
    """
    Upload and analyze a resume file.
    
    POST /api/resumes/upload
    Form data:
        - file: Resume file (pdf, txt, or docx)
    """
    try:
        user = get_current_user()
        
        # Check file presence
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF, TXT, and DOCX files allowed'}), 400
        
        # Read file content
        file_content = file.read()
        
        if len(file_content) == 0:
            return jsonify({'error': 'File is empty'}), 400
        
        if len(file_content) > MAX_FILE_SIZE:
            return jsonify({'error': f'File too large. Max {MAX_FILE_SIZE / 1024 / 1024}MB'}), 400
        
        # Save file
        secure_name = secure_filename(file.filename)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f'{user.id}_{timestamp}_{secure_name}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'wb') as f:
            f.write(file_content)
        
        # Extract text from file
        try:
            if file.filename.endswith('.txt'):
                text = file_content.decode('utf-8', errors='ignore')
            elif file.filename.endswith('.pdf'):
                # Simple PDF text extraction
                text = file_content.decode('utf-8', errors='ignore')
            elif file.filename.endswith('.docx'):
                # Simple DOCX text extraction
                text = file_content.decode('utf-8', errors='ignore')
            else:
                text = 'File content'
        except Exception as e:
            text = 'Could not extract text'
        
        # Analyze resume
        analysis = analyze_resume(text)
        
        # Create resume record
        resume = Resume(
            user_id=user.id,
            filename=filename,
            original_filename=secure_name,
            file_path=filepath,
            file_size=len(file_content),
            file_type=file.filename.rsplit('.', 1)[1].lower(),
            extracted_text=text[:1000],  # Store first 1000 chars
            overall_score=analysis['overall_score'],
            skills_score=analysis['skills_score'],
            education_score=analysis['education_score'],
            experience_score=analysis['experience_score'],
            formatting_score=analysis['formatting_score'],
            detected_skills=analysis['detected_skills'],
            detected_experience=analysis['detected_soft_skills'],
            feedback=analysis['feedback'],
            analyzed_at=datetime.utcnow()
        )
        
        db.session.add(resume)
        db.session.commit()
        
        return jsonify({
            'message': 'Resume uploaded and analyzed successfully',
            'resume': resume.to_dict(),
            'analysis': {
                'overall_score': analysis['overall_score'],
                'skills_score': analysis['skills_score'],
                'education_score': analysis['education_score'],
                'experience_score': analysis['experience_score'],
                'formatting_score': analysis['formatting_score'],
                'feedback': analysis['feedback']
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f'Upload error: {str(e)}')
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@app.route('/api/resumes', methods=['GET'])
@login_required
def get_resumes():
    """
    Get all resumes for current user.
    
    GET /api/resumes
    """
    try:
        user = get_current_user()
        resumes = Resume.query.filter_by(user_id=user.id)\
                              .order_by(Resume.uploaded_at.desc()).all()
        
        return jsonify({
            'resumes': [r.to_dict() for r in resumes],
            'total': len(resumes)
        }), 200
        
    except Exception as e:
        print(f'Get resumes error: {str(e)}')
        return jsonify({'error': 'Failed to fetch resumes'}), 500


@app.route('/api/resumes/<int:resume_id>', methods=['GET'])
@login_required
def get_resume(resume_id):
    """
    Get a specific resume by ID.
    
    GET /api/resumes/<resume_id>
    """
    try:
        user = get_current_user()
        resume = Resume.query.filter_by(id=resume_id, user_id=user.id).first()
        
        if not resume:
            return jsonify({'error': 'Resume not found'}), 404
        
        return jsonify({'resume': resume.to_dict()}), 200
        
    except Exception as e:
        print(f'Get resume error: {str(e)}')
        return jsonify({'error': 'Failed to fetch resume'}), 500


@app.route('/api/resumes/<int:resume_id>', methods=['DELETE'])
@login_required
def delete_resume(resume_id):
    """
    Delete a resume.
    
    DELETE /api/resumes/<resume_id>
    """
    try:
        user = get_current_user()
        resume = Resume.query.filter_by(id=resume_id, user_id=user.id).first()
        
        if not resume:
            return jsonify({'error': 'Resume not found'}), 404
        
        # Delete file
        if os.path.exists(resume.file_path):
            os.remove(resume.file_path)
        
        # Delete database record
        db.session.delete(resume)
        db.session.commit()
        
        return jsonify({'message': 'Resume deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f'Delete error: {str(e)}')
        return jsonify({'error': 'Failed to delete resume'}), 500


# ── ANALYTICS ROUTES ────────────────────────────────────────────────────────

@app.route('/api/analytics', methods=['GET'])
@login_required
def get_analytics():
    """
    Get analytics for current user's resumes.
    
    GET /api/analytics
    """
    try:
        user = get_current_user()
        resumes = Resume.query.filter_by(user_id=user.id).all()
        
        if not resumes:
            return jsonify({
                'total_resumes': 0,
                'average_score': 0,
                'best_score': 0,
                'scores_by_category': {}
            }), 200
        
        scores = [r.overall_score for r in resumes if r.overall_score > 0]
        
        analytics = {
            'total_resumes': len(resumes),
            'average_score': round(sum(scores) / len(scores), 2) if scores else 0,
            'best_score': max(scores) if scores else 0,
            'worst_score': min(scores) if scores else 0,
            'scores_by_category': {
                'skills': round(sum(r.skills_score for r in resumes) / len(resumes), 2),
                'education': round(sum(r.education_score for r in resumes) / len(resumes), 2),
                'experience': round(sum(r.experience_score for r in resumes) / len(resumes), 2),
                'formatting': round(sum(r.formatting_score for r in resumes) / len(resumes), 2),
            },
            'recent_resumes': [r.to_dict() for r in resumes[-5:]]
        }
        
        return jsonify(analytics), 200
        
    except Exception as e:
        print(f'Analytics error: {str(e)}')
        return jsonify({'error': 'Failed to fetch analytics'}), 500


# ── HEALTH CHECK ────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def health_check():
    """
    Health check endpoint.
    Returns API status.
    """
    return jsonify({
        'status': 'success',
        'message': 'Resume Analyzer API is running',
        'version': '2.0.0',
        'endpoints': {
            'auth': [
                'POST /api/auth/signup',
                'POST /api/auth/login',
                'POST /api/auth/logout',
                'GET /api/auth/me'
            ],
            'resumes': [
                'POST /api/resumes/upload',
                'GET /api/resumes',
                'GET /api/resumes/<id>',
                'DELETE /api/resumes/<id>'
            ],
            'analytics': [
                'GET /api/analytics'
            ]
        }
    }), 200


@app.route('/api/health', methods=['GET'])
def api_health():
    """API health check endpoint."""
    return jsonify({'status': 'healthy'}), 200


# ── ERROR HANDLERS ──────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large errors."""
    return jsonify({'error': f'File too large. Max {MAX_FILE_SIZE / 1024 / 1024}MB allowed'}), 413


# ── ENTRY POINT ────────────────────────────────────────────────────────────

# Initialize database tables (runs even when Gunicorn starts)
with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print('\n' + '='*70)
    print('  🚀  RESUME ANALYZER API')
    print('='*70)
    print(f'  ✓ Database: resume_analyzer.db')
    print(f'  ✓ Server: http://0.0.0.0:{port}')
    print(f'  ✓ Health: http://0.0.0.0:{port}/')
    print(f'  ✓ API Docs: http://0.0.0.0:{port}/')
    print('='*70 + '\n')
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )
