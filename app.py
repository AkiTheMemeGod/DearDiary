from flask import Flask, render_template, redirect, url_for, flash, request, send_file
import io
import json
from extensions import db, login_manager, migrate
from models import User, DiaryEntry, EntryImage
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import login_user, login_required, logout_user, current_user
from textblob import TextBlob
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = '9012j3ikajlkanslkdnaljsdnlihwh90odwj;aoilasndasiojdq9poijanskj,dbas,jdamsd'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = 'static/uploads'

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Routes
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash('Invalid username or password')
        return render_template('auth.html', mode='login')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists')
                return redirect(url_for('signup'))
            
            new_user = User(username=username, password_hash=generate_password_hash(password, method='scrypt'))
            db.session.add(new_user)
            db.session.commit()
            
            login_user(new_user)
            return redirect(url_for('dashboard'))
        return render_template('auth.html', mode='signup')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Dashboard is now the "Cover" page
        # Fetch latest image for the "Memories" card
        latest_image = EntryImage.query.join(DiaryEntry).filter(
            DiaryEntry.user_id == current_user.id
        ).order_by(EntryImage.created_at.desc()).first()
        
        return render_template('dashboard.html', user=current_user, latest_image=latest_image)

    @app.route('/entries')
    @login_required
    def entries():
        entries = DiaryEntry.query.filter_by(user_id=current_user.id).order_by(DiaryEntry.created_at.desc()).all()
        return render_template('entries.html', entries=entries)

    @app.route('/write')
    @login_required
    def new_entry_page():
        return render_template('write.html')

    @app.route('/entry/<int:entry_id>')
    @login_required
    def entry_detail(entry_id):
        entry = DiaryEntry.query.get_or_404(entry_id)
        if entry.author != current_user:
            return "Unauthorized", 403
        return render_template('entry_detail.html', entry=entry)

    @app.route('/entry/new', methods=['POST'])
    @login_required
    def new_entry():
        title = request.form.get('title')
        content = request.form.get('content')
        mood = request.form.get('mood')
        
        if not mood and content:
            blob = TextBlob(content)
            polarity = blob.sentiment.polarity
            
            if polarity > 0.5:
                mood = "Radiant"
            elif polarity > 0.1:
                mood = "Optimistic"
            elif polarity > -0.1:
                mood = "Reflective"
            elif polarity > -0.5:
                mood = "Melancholic"
            else:
                mood = "Desolate"
        
        entry = DiaryEntry(title=title, content=content, mood=mood, author=current_user)
        
        # Parse coordinates
        coords_data = {}
        if request.form.get('image_coordinates'):
            try:
                raw_coords = json.loads(request.form.get('image_coordinates'))
                # Create a map: filename -> {x, y, rotation}
                for item in raw_coords:
                    coords_data[item['filename']] = item
            except:
                pass

        # Handle images
        if 'images' in request.files:
            files = request.files.getlist('images')
            for file in files:
                if file and file.filename:
                    # Use original filename for coordinate lookup
                    original_filename = file.filename
                    safe_filename = secure_filename(file.filename)
                    
                    # Get coords if available
                    x = 0
                    y = 0
                    rot = 0.0
                    
                    # Check against the original filename sent from client
                    if original_filename in coords_data:
                        x = coords_data[original_filename].get('x', 0)
                        y = coords_data[original_filename].get('y', 0)
                        rot = coords_data[original_filename].get('rot', 0)

                    # Read binary data
                    file_data = file.read()
                    
                    image = EntryImage(
                        filename=safe_filename, 
                        data=file_data, 
                        mimetype=file.mimetype,
                        x_pos=x,
                        y_pos=y,
                        rotation=rot,
                        entry=entry
                    )
                    db.session.add(image)

        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('dashboard'))

    @app.route('/image/<int:image_id>')
    @login_required
    def get_image(image_id):
        image = EntryImage.query.get_or_404(image_id)
        if image.entry.author != current_user:
            return "Unauthorized", 403
        return send_file(
            io.BytesIO(image.data),
            mimetype=image.mimetype,
            as_attachment=False,
            download_name=image.filename
        )

    @app.route('/entry/delete/<int:id>', methods=['POST'])
    @login_required
    def delete_entry(id):
        entry = DiaryEntry.query.get_or_404(id)
        if entry.author != current_user:
            return "Unauthorized", 403
        db.session.delete(entry)
        db.session.commit()
        return redirect(url_for('dashboard'))

    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
