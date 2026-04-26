import os
import math
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, abort, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from PIL import Image
import random
from twilio.rest import Client
import razorpay

from config import config
from models import db, Customer, Provider, Admin, Service, Booking, Review, Payment, Message, TimeSlot, OTP, Address, UserRole, BookingStatus, init_services

# Initialize extensions
login_manager = LoginManager()
socketio = SocketIO(cors_allowed_origins="*")
razorpay_client = None
twilio_client = None

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    db.init_app(app)
    login_manager.init_app(app)
    socketio.init_app(app)
    
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # ==================== RAZORPAY INITIALIZATION ====================
    global razorpay_client
    if app.config.get('RAZORPAY_KEY_ID') and app.config.get('RAZORPAY_KEY_SECRET'):
        razorpay_client = razorpay.Client(auth=(
            app.config['RAZORPAY_KEY_ID'],
            app.config['RAZORPAY_KEY_SECRET']
        ))
        print("✅ Razorpay configured")
    else:
        print("⚠️ Razorpay not configured - add keys to .env file")
    
    print(f"Razorpay Key ID: {app.config.get('RAZORPAY_KEY_ID', 'NOT SET')}")
    print(f"Razorpay configured: {razorpay_client is not None}")
    
    # ==================== TWILIO INITIALIZATION ====================
    global twilio_client
    if app.config.get('TWILIO_ACCOUNT_SID') and app.config.get('TWILIO_AUTH_TOKEN'):
        twilio_client = Client(
            app.config['TWILIO_ACCOUNT_SID'],
            app.config['TWILIO_AUTH_TOKEN']
        )
        print("✅ Twilio configured")
    else:
        print("⚠️ Twilio not configured")
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    register_routes(app)
    
    with app.app_context():
        db.create_all()
        print("✅ Database tables created")
        
        # Create admin if not exists
        if not Admin.query.filter_by(email=app.config.get('ADMIN_EMAIL', 'admin@serviq.com')).first():
            admin = Admin(
                full_name='Admin',
                email=app.config.get('ADMIN_EMAIL', 'admin@serviq.com'),
                phone='9999999999',
                role=UserRole.ADMIN
            )
            admin.set_password(app.config.get('ADMIN_PASSWORD', 'Admin@123'))
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created")
        
        # Initialize services
        init_services()
    
    return app

def register_routes(app):
    
    # ==================== HELPER FUNCTIONS ====================
    
    @login_manager.user_loader
    def load_user(user_id):
        user_type = session.get('user_type', 'customer')
        if user_type == 'customer':
            return Customer.query.get(int(user_id))
        elif user_type == 'provider':
            return Provider.query.get(int(user_id))
        elif user_type == 'admin':
            return Admin.query.get(int(user_id))
        return None
    
    @app.context_processor
    def utility_processor():
        pending_count = 0
        if hasattr(current_user, 'is_admin') and current_user.is_admin():
            pending_count = Provider.query.filter_by(is_approved=False).count()
        return dict(
            now=datetime.now,
            timedelta=timedelta,
            pending_approvals_count=pending_count,
            current_user=current_user
        )
    
    def customer_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in.', 'danger')
                return redirect(url_for('login'))
            if not current_user.is_customer():
                flash('Customer access required.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    
    def provider_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in.', 'danger')
                return redirect(url_for('login'))
            if not current_user.is_provider():
                flash('Provider access required.', 'danger')
                return redirect(url_for('dashboard'))
            if not current_user.is_approved:
                flash('Account pending approval.', 'warning')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in.', 'danger')
                return redirect(url_for('login'))
            if not current_user.is_admin():
                flash('Admin access required.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']
    
    def save_photo(file):
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{secrets.token_hex(8)}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            image = Image.open(file)
            image.thumbnail((800, 800))
            image.save(filepath, optimize=True, quality=85)
            return filename
        return None
    
    def generate_otp():
        return ''.join(random.choices(string.digits, k=6))
    
    def send_sms_otp(phone_number, otp_code):
        try:
            if not twilio_client:
                return False, "Twilio not configured"
            message = twilio_client.messages.create(
                body=f"Serviq OTP: {otp_code}. Valid for 10 mins.",
                from_=app.config['TWILIO_PHONE_NUMBER'],
                to=f"+91{phone_number}"
            )
            return True, message.sid
        except Exception as e:
            return False, str(e)
    
    def calculate_distance(lat1, lon1, lat2, lon2):
        R = 6371
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c
    
    # ==================== FILE UPLOAD ====================
    
    @app.route('/uploads/<filename>')
    def uploaded_file(filename):
        try:
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        except:
            return send_from_directory('static/images', 'default-avatar.png')
    
    # ==================== AUTH ROUTES ====================
    
    @app.route('/')
    def index():
        services = Service.query.all()
        featured = Provider.query.filter_by(is_approved=True).order_by(Provider.average_rating.desc()).limit(6).all()
        return render_template('index.html', services=services, featured_providers=featured)
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            user_type = request.form.get('user_type', 'customer')
            
            user = None
            if user_type == 'customer':
                user = Customer.query.filter_by(email=email).first()
            elif user_type == 'provider':
                user = Provider.query.filter_by(email=email).first()
            elif user_type == 'admin':
                user = Admin.query.filter_by(email=email).first()
            
            if user and user.check_password(password):
                if not user.is_active:
                    flash('Account deactivated.', 'danger')
                    return redirect(url_for('login'))
                
                session['user_type'] = user_type
                login_user(user)
                next_page = request.args.get('next')
                
                if next_page:
                    return redirect(next_page)
                
                if user_type == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user_type == 'provider':
                    if not user.is_approved:
                        flash('Account pending approval.', 'warning')
                        return redirect(url_for('index'))
                    return redirect(url_for('provider_dashboard'))
                else:
                    return redirect(url_for('customer_dashboard'))
            else:
                flash('Invalid credentials.', 'danger')
        
        return render_template('login.html')
    
    @app.route('/register/customer', methods=['GET', 'POST'])
    def register_customer():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')
            address = request.form.get('address')
            city = request.form.get('city')
            pincode = request.form.get('pincode')
            
            if Customer.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('register_customer'))
            
            if Customer.query.filter_by(phone=phone).first():
                flash('Phone already registered.', 'danger')
                return redirect(url_for('register_customer'))
            
            customer = Customer(
                full_name=full_name,
                email=email,
                phone=phone,
                role=UserRole.CUSTOMER,
                address=address,
                city=city,
                pincode=pincode
            )
            customer.set_password(password)
            
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        customer.profile_photo = filename
            
            db.session.add(customer)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        return render_template('register_customer.html')
    
    @app.route('/register/provider', methods=['GET', 'POST'])
    def register_provider():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')
            city = request.form.get('city')
            starting_price = float(request.form.get('starting_price', 0))
            years_experience = int(request.form.get('years_experience', 0))
            description = request.form.get('description')
            # Handle empty latitude/longitude values
            lat_value = request.form.get('latitude', '')
            lng_value = request.form.get('longitude', '')
            latitude = float(lat_value) if lat_value and lat_value.strip() else 0.0
            longitude = float(lng_value) if lng_value and lng_value.strip() else 0.0
            
            if Provider.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('register_provider'))
            
            if Provider.query.filter_by(phone=phone).first():
                flash('Phone already registered.', 'danger')
                return redirect(url_for('register_provider'))
            
            provider = Provider(
                full_name=full_name,
                email=email,
                phone=phone,
                city=city,
                starting_price=starting_price,
                years_experience=years_experience,
                description=description,
                latitude=latitude,
                longitude=longitude,
                is_approved=False,
                role=UserRole.PROVIDER
            )
            provider.set_password(password)
            
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        provider.profile_photo = filename
            
            service_ids = request.form.getlist('services')
            for sid in service_ids:
                service = Service.query.get(int(sid))
                if service:
                    provider.services.append(service)
            
            db.session.add(provider)
            db.session.commit()
            
            flash('Registration successful! Pending admin approval.', 'success')
            return redirect(url_for('login'))
        
        services = Service.query.all()
        return render_template('register_provider.html', services=services)
    
    @app.route('/send-otp', methods=['POST'])
    def send_otp():
        try:
            phone = request.json.get('phone')
            if not phone or len(phone) != 10:
                return jsonify({'success': False, 'message': 'Invalid phone number'})
            
            otp_code = generate_otp()
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            
            otp = OTP(phone=phone, otp=otp_code, purpose='login', expires_at=expires_at)
            db.session.add(otp)
            db.session.commit()
            
            success, msg = send_sms_otp(phone, otp_code)
            if success:
                return jsonify({'success': True, 'message': 'OTP sent'})
            else:
                return jsonify({'success': True, 'message': 'Demo mode', 'otp': otp_code})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})
    
    @app.route('/verify-otp', methods=['POST'])
    def verify_otp():
        phone = request.json.get('phone')
        otp_code = request.json.get('otp')
        
        otp = OTP.query.filter_by(phone=phone, otp=otp_code, is_verified=False)\
            .filter(OTP.expires_at > datetime.utcnow()).first()
        
        if otp:
            otp.is_verified = True
            db.session.commit()
            
            customer = Customer.query.filter_by(phone=phone).first()
            provider = Provider.query.filter_by(phone=phone).first()
            
            if customer:
                session['user_type'] = 'customer'
                login_user(customer)
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            elif provider:
                session['user_type'] = 'provider'
                login_user(provider)
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            else:
                session['phone_verified'] = phone
                return jsonify({'success': True, 'redirect': url_for('choose_registration')})
        
        return jsonify({'success': False, 'message': 'Invalid OTP'})
    
    @app.route('/choose-registration')
    def choose_registration():
        if not session.get('phone_verified'):
            return redirect(url_for('login'))
        return render_template('choose_registration.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        session.clear()
        flash('Logged out.', 'info')
        return redirect(url_for('index'))
    
    @app.route('/dashboard')
    @login_required
    def dashboard():
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        elif current_user.is_provider():
            return redirect(url_for('provider_dashboard'))
        else:
            return redirect(url_for('customer_dashboard'))
    
    # ==================== CUSTOMER ROUTES ====================
    
    @app.route('/customer/dashboard')
    @login_required
    @customer_required
    def customer_dashboard():
        upcoming = Booking.query.filter_by(
            customer_id=current_user.id
        ).filter(
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
        ).order_by(Booking.service_date).limit(5).all()
        
        past = Booking.query.filter_by(
            customer_id=current_user.id, status=BookingStatus.COMPLETED
        ).order_by(Booking.completed_date.desc()).limit(5).all()
        
        return render_template('customer_dashboard.html',
                             upcoming_bookings=upcoming,
                             past_bookings=past)
    
    @app.route('/customer/update-profile', methods=['POST'])
    @login_required
    @customer_required
    def update_profile():
        if request.method == 'POST':
            current_user.full_name = request.form.get('full_name')
            current_user.phone = request.form.get('phone')
            current_user.address = request.form.get('address')
            current_user.city = request.form.get('city')
            current_user.pincode = request.form.get('pincode')
            
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        current_user.profile_photo = filename
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        
        return redirect(url_for('customer_dashboard'))
    
    @app.route('/customer/change-password', methods=['POST'])
    @login_required
    @customer_required
    def change_password():
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
        
        return redirect(url_for('customer_dashboard'))
    
    @app.route('/customer/bookings')
    @login_required
    @customer_required
    def customer_bookings():
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        
        query = Booking.query.filter_by(customer_id=current_user.id)
        if status:
            query = query.filter_by(status=status)
        
        bookings = query.order_by(Booking.created_at.desc()).paginate(page=page, per_page=10)
        return render_template('customer_bookings.html', bookings=bookings)
    
    @app.route('/customer/booking/<int:booking_id>')
    @login_required
    @customer_required
    def customer_booking_detail(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id:
            abort(403)
        return render_template('booking_detail.html', booking=booking)
    
    @app.route('/customer/cancel-booking/<int:booking_id>', methods=['POST'])
    @login_required
    @customer_required
    def cancel_booking(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id:
            abort(403)
        
        reason = request.form.get('reason', 'Cancelled by customer')
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_date = datetime.utcnow()
        booking.cancellation_reason = reason
        
        if booking.time_slot_id:
            slot = TimeSlot.query.get(booking.time_slot_id)
            if slot:
                slot.is_booked = False
                slot.booking_id = None
        
        db.session.commit()
        flash('Booking cancelled successfully.', 'success')
        return redirect(url_for('customer_bookings'))
    
    @app.route('/customer/add-review/<int:booking_id>', methods=['POST'])
    @login_required
    @customer_required
    def add_review(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id:
            abort(403)
        
        if booking.status != BookingStatus.COMPLETED:
            flash('Only completed bookings can be reviewed.', 'danger')
            return redirect(url_for('customer_booking_detail', booking_id=booking_id))
        
        existing = Review.query.filter_by(booking_id=booking_id).first()
        if existing:
            flash('You have already reviewed this booking.', 'warning')
            return redirect(url_for('customer_booking_detail', booking_id=booking_id))
        
        rating = int(request.form.get('rating'))
        comment = request.form.get('comment')
        
        review = Review(
            booking_id=booking_id,
            customer_id=current_user.id,
            provider_id=booking.provider_id,
            rating=rating,
            comment=comment
        )
        
        db.session.add(review)
        
        provider = booking.provider
        reviews = Review.query.filter_by(provider_id=provider.id).all()
        total = sum(r.rating for r in reviews) + rating
        provider.average_rating = total / (len(reviews) + 1)
        provider.total_reviews = len(reviews) + 1
        
        db.session.commit()
        flash('Review added successfully!', 'success')
        return redirect(url_for('customer_booking_detail', booking_id=booking_id))
    
    @app.route('/customer/addresses')
    @login_required
    @customer_required
    def customer_addresses():
        return render_template('customer_addresses.html', addresses=current_user.addresses)
    
    # ==================== PROVIDER ROUTES ====================
    
    @app.route('/provider/dashboard')
    @login_required
    @provider_required
    def provider_dashboard():
        today = datetime.today().date()
        
        today_bookings = Booking.query.filter_by(
            provider_id=current_user.id, service_date=today
        ).filter(
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
        ).all()
        
        upcoming = Booking.query.filter_by(
            provider_id=current_user.id
        ).filter(
            Booking.service_date > today,
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])
        ).order_by(Booking.service_date).limit(10).all()
        
        reviews = Review.query.filter_by(
            provider_id=current_user.id
        ).order_by(Review.created_at.desc()).limit(5).all()
        
        total_earnings = db.session.query(db.func.sum(Booking.total_amount))\
            .filter_by(provider_id=current_user.id, payment_status='paid').scalar() or 0
        
        completed = Booking.query.filter_by(
            provider_id=current_user.id, status=BookingStatus.COMPLETED
        ).count()
        
        return render_template('provider_dashboard.html',
                             today_bookings=today_bookings,
                             upcoming_bookings=upcoming,
                             recent_reviews=reviews,
                             total_earnings=total_earnings,
                             completed_bookings=completed)
    
    @app.route('/provider/update-profile', methods=['POST'])
    @login_required
    @provider_required
    def update_provider_profile():
        if request.method == 'POST':
            current_user.full_name = request.form.get('full_name')
            current_user.phone = request.form.get('phone')
            current_user.city = request.form.get('city')
            current_user.starting_price = float(request.form.get('starting_price', 0))
            current_user.description = request.form.get('description')
            
            if 'profile_photo' in request.files:
                file = request.files['profile_photo']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        current_user.profile_photo = filename
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        
        return redirect(url_for('provider_dashboard'))
    
    @app.route('/provider/change-password', methods=['POST'])
    @login_required
    @provider_required
    def provider_change_password():
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Password changed successfully!', 'success')
        
        return redirect(url_for('provider_dashboard'))
    
    @app.route('/provider/bookings')
    @login_required
    @provider_required
    def provider_bookings():
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        
        query = Booking.query.filter_by(provider_id=current_user.id)
        if status:
            query = query.filter_by(status=status)
        
        bookings = query.order_by(Booking.created_at.desc()).paginate(page=page, per_page=10)
        return render_template('provider_bookings.html', bookings=bookings)
    
    @app.route('/provider/booking/<int:booking_id>')
    @login_required
    @provider_required
    def provider_booking_detail(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.provider_id != current_user.id:
            abort(403)
        return render_template('booking_detail.html', booking=booking)
    
    @app.route('/provider/update-booking-status/<int:booking_id>', methods=['POST'])
    @login_required
    @provider_required
    def update_booking_status(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.provider_id != current_user.id:
            abort(403)
        
        new_status = request.form.get('status')
        if new_status in ['confirmed', 'completed', 'cancelled']:
            booking.status = new_status
            if new_status == 'completed':
                booking.completed_date = datetime.utcnow()
            elif new_status == 'cancelled':
                booking.cancelled_date = datetime.utcnow()
                if booking.time_slot_id:
                    slot = TimeSlot.query.get(booking.time_slot_id)
                    if slot:
                        slot.is_booked = False
                        slot.booking_id = None
            
            db.session.commit()
            flash(f'Booking status updated to {new_status}.', 'success')
        
        return redirect(url_for('provider_booking_detail', booking_id=booking_id))
    
    @app.route('/provider/time-slots', methods=['GET', 'POST'])
    @login_required
    @provider_required
    def manage_time_slots():
        if request.method == 'POST':
            date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
            start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time()
            end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time()
            
            existing = TimeSlot.query.filter_by(
                provider_id=current_user.id,
                date=date,
                start_time=start_time
            ).first()
            
            if existing:
                flash('Time slot already exists.', 'danger')
            else:
                slot = TimeSlot(
                    provider_id=current_user.id,
                    date=date,
                    start_time=start_time,
                    end_time=end_time
                )
                db.session.add(slot)
                db.session.commit()
                flash('Time slot added successfully!', 'success')
            
            return redirect(url_for('manage_time_slots'))
        
        today = datetime.today().date()
        slots = TimeSlot.query.filter(
            TimeSlot.provider_id == current_user.id,
            TimeSlot.date >= today
        ).order_by(TimeSlot.date, TimeSlot.start_time).all()
        
        return render_template('manage_slots.html', slots=slots)
    
    @app.route('/provider/delete-slot/<int:slot_id>', methods=['POST'])
    @login_required
    @provider_required
    def delete_time_slot(slot_id):
        slot = TimeSlot.query.get_or_404(slot_id)
        if slot.provider_id != current_user.id:
            abort(403)
        
        if not slot.is_booked:
            db.session.delete(slot)
            db.session.commit()
            flash('Time slot deleted successfully.', 'success')
        else:
            flash('Cannot delete a booked time slot.', 'danger')
        
        return redirect(url_for('manage_time_slots'))
    
    @app.route('/provider/earnings')
    @login_required
    @provider_required
    def provider_earnings():
        completed = Booking.query.filter_by(
            provider_id=current_user.id, status=BookingStatus.COMPLETED
        ).order_by(Booking.completed_date.desc()).all()
        
        total_earnings = sum(b.total_amount for b in completed)
        
        return render_template('provider_earnings.html',
                             bookings=completed,
                             total_earnings=total_earnings)
    
    @app.route('/provider/reviews')
    @login_required
    @provider_required
    def provider_reviews():
        reviews = Review.query.filter_by(provider_id=current_user.id)\
            .order_by(Review.created_at.desc()).all()
        return render_template('provider_reviews.html', reviews=reviews)
    
    # ==================== PUBLIC ROUTES ====================
    
    @app.route('/providers')
    def providers():
        service_id = request.args.get('service', type=int)
        city = request.args.get('city')
        min_price = request.args.get('min_price', type=float)
        max_price = request.args.get('max_price', type=float)
        min_rating = request.args.get('min_rating', type=float)
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        radius = request.args.get('radius', type=float, default=10)
        
        filters = {
            'service_id': service_id,
            'city': city,
            'min_price': min_price,
            'max_price': max_price,
            'min_rating': min_rating,
            'lat': lat,
            'lng': lng,
            'radius': radius
        }
        
        query = Provider.query.filter_by(is_approved=True, is_active=True)
        
        if service_id:
            query = query.join(Provider.services).filter(Service.id == service_id)
        
        if city:
            query = query.filter(Provider.city.ilike(f'%{city}%'))
        
        if min_price is not None:
            query = query.filter(Provider.starting_price >= min_price)
        
        if max_price is not None:
            query = query.filter(Provider.starting_price <= max_price)
        
        if min_rating is not None:
            query = query.filter(Provider.average_rating >= min_rating)
        
        providers_list = query.all()
        
        # Add services to each provider for template
        for p in providers_list:
            p.services_list = p.services
        
        # Calculate distances if location provided
        if lat and lng:
            for p in providers_list:
                if p.latitude and p.longitude:
                    dist = calculate_distance(lat, lng, p.latitude, p.longitude)
                    if dist <= radius:
                        p.distance = round(dist, 2)
            providers_list = [p for p in providers_list if hasattr(p, 'distance')]
            providers_list.sort(key=lambda x: x.distance)
        
        services = Service.query.all()
        
        # Convert providers to JSON-serializable format
        providers_json = []
        for p in providers_list:
            providers_json.append({
                'id': p.id,
                'full_name': p.full_name,
                'city': p.city,
                'latitude': p.latitude,
                'longitude': p.longitude,
                'average_rating': p.average_rating,
                'total_reviews': p.total_reviews,
                'starting_price': p.starting_price,
                'years_experience': p.years_experience,
                'profile_photo': p.profile_photo,
                'distance': getattr(p, 'distance', None)
            })
        
        return render_template('providers.html',
                             providers=providers_list,
                             providers_json=providers_json,
                             services=services,
                             filters=filters)
    
    @app.route('/provider/<int:provider_id>')
    def provider_detail(provider_id):
        provider = Provider.query.get_or_404(provider_id)
        if not provider.is_approved:
            abort(404)
        
        reviews = Review.query.filter_by(provider_id=provider_id).order_by(Review.created_at.desc()).all()
        
        today = datetime.today().date()
        slots = TimeSlot.query.filter(
            TimeSlot.provider_id == provider_id,
            TimeSlot.date >= today,
            TimeSlot.is_booked == False
        ).order_by(TimeSlot.date, TimeSlot.start_time).limit(20).all()
        
        return render_template('provider_detail.html',
                             provider=provider,
                             reviews=reviews,
                             available_slots=slots)
    
    @app.route('/book/<int:provider_id>', methods=['GET', 'POST'])
    @login_required
    def book_service(provider_id):
        provider = Provider.query.get_or_404(provider_id)
        
        if request.method == 'POST':
            service_id = request.form.get('service_id')
            time_slot_id = request.form.get('time_slot_id')
            service_date = datetime.strptime(request.form.get('service_date'), '%Y-%m-%d').date()
            service_time = datetime.strptime(request.form.get('service_time'), '%H:%M').time()
            address = request.form.get('address')
            city = request.form.get('city')
            pincode = request.form.get('pincode')
            
            time_slot = TimeSlot.query.filter_by(
                id=time_slot_id, provider_id=provider_id,
                date=service_date, start_time=service_time, is_booked=False
            ).first()
            
            if not time_slot:
                flash('Time slot unavailable.', 'danger')
                return redirect(url_for('book_service', provider_id=provider_id))
            
            service = Service.query.get(service_id)
            
            booking = Booking(
                booking_number=Booking().generate_booking_number(),
                customer_id=current_user.id,
                provider_id=provider_id,
                service_id=service_id,
                service_name=service.name,
                service_price=provider.starting_price,
                total_amount=provider.starting_price,
                address_line1=address,
                city=city,
                pincode=pincode,
                service_date=service_date,
                service_time=service_time
            )
            
            db.session.add(booking)
            db.session.flush()
            
            time_slot.is_booked = True
            time_slot.booking_id = booking.id
            db.session.commit()
            
            return redirect(url_for('payment', booking_id=booking.id))
        
        services = provider.services
        today = datetime.today().date()
        slots = TimeSlot.query.filter(
            TimeSlot.provider_id == provider_id,
            TimeSlot.date >= today,
            TimeSlot.is_booked == False
        ).order_by(TimeSlot.date, TimeSlot.start_time).all()
        
        return render_template('booking.html',
                             provider=provider,
                             services=services,
                             available_slots=slots)
    
    @app.route('/payment/<int:booking_id>', methods=['GET', 'POST'])
    @login_required
    def payment(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        
        if request.method == 'POST':
            if not razorpay_client:
                flash('Payment gateway not configured.', 'danger')
                return redirect(url_for('booking_detail', booking_id=booking_id))
            
            order_data = {
                'amount': int(booking.total_amount * 100),
                'currency': 'INR',
                'receipt': booking.booking_number,
                'payment_capture': 1
            }
            try:
                order = razorpay_client.order.create(data=order_data)
                booking.razorpay_order_id = order['id']
                db.session.commit()
                return jsonify({
                    'success': True,
                    'order_id': order['id'],
                    'amount': order['amount'],
                    'key_id': app.config['RAZORPAY_KEY_ID']
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
        
        return render_template('payment.html', booking=booking)
    
    @app.route('/payment/status/<int:booking_id>')
    @login_required
    def payment_status(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id:
            abort(403)
        return render_template('payment_status.html', booking=booking)
    
    @app.route('/payment/verify', methods=['POST'])
    @login_required
    def verify_payment():
        data = request.json
        try:
            if not razorpay_client:
                return jsonify({'success': False, 'error': 'Payment gateway not configured'})
            
            params = {
                'razorpay_order_id': data['razorpay_order_id'],
                'razorpay_payment_id': data['razorpay_payment_id'],
                'razorpay_signature': data['razorpay_signature']
            }
            razorpay_client.utility.verify_payment_signature(params)
            
            booking = Booking.query.filter_by(razorpay_order_id=data['razorpay_order_id']).first()
            if booking:
                booking.payment_status = 'paid'
                booking.status = BookingStatus.CONFIRMED
                booking.razorpay_payment_id = data['razorpay_payment_id']
                db.session.commit()
                return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    # ==================== BOOKING CONFIRM (BYPASS) ====================
    
    @app.route('/booking/confirm/<int:booking_id>')
    @login_required
    def confirm_booking(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id:
            abort(403)
        
        booking.payment_status = 'paid'
        booking.status = BookingStatus.CONFIRMED
        db.session.commit()
        
        flash('Booking confirmed successfully!', 'success')
        return redirect(url_for('booking_detail', booking_id=booking_id))
    
    # ==================== MESSAGING ====================
    
    @app.route('/messages/<int:booking_id>')
    @login_required
    def messages(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id and booking.provider_id != current_user.id:
            abort(403)
        
        messages = Message.query.filter_by(booking_id=booking_id).order_by(Message.created_at).all()
        return render_template('chat.html', booking=booking, messages=messages)
    
    @app.route('/send-message', methods=['POST'])
    @login_required
    def send_message():
        booking_id = request.form.get('booking_id')
        message_text = request.form.get('message')
        
        if not message_text:
            return jsonify({'success': False, 'error': 'Message cannot be empty'})
        
        booking = Booking.query.get_or_404(booking_id)
        if booking.customer_id != current_user.id and booking.provider_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'})
        
        if current_user.is_customer():
            message = Message(
                booking_id=booking_id,
                customer_id=current_user.id,
                provider_id=booking.provider_id,
                message=message_text,
                sender_type='customer'
            )
        else:
            message = Message(
                booking_id=booking_id,
                customer_id=booking.customer_id,
                provider_id=current_user.id,
                message=message_text,
                sender_type='provider'
            )
        
        db.session.add(message)
        db.session.commit()
        
        # Emit socket event
        socketio.emit('new_message', {
            'message': message_text,
            'sender_id': current_user.id,
            'sender_name': current_user.full_name,
            'sender_type': 'customer' if current_user.is_customer() else 'provider',
            'recipient_id': booking.provider_id if current_user.is_customer() else booking.customer_id,
            'booking_id': booking_id,
            'timestamp': message.created_at.isoformat()
        }, room=f'booking_{booking_id}')
        
        return jsonify({'success': True})
    
    @socketio.on('join')
    def handle_join(data):
        booking_id = data.get('booking_id')
        user_id = data.get('user_id')
        room = f'booking_{booking_id}'
        join_room(room)
        emit('user_joined', {'user_id': user_id}, room=room)
    
    @socketio.on('leave')
    def handle_leave(data):
        booking_id = data.get('booking_id')
        user_id = data.get('user_id')
        room = f'booking_{booking_id}'
        leave_room(room)
        emit('user_left', {'user_id': user_id}, room=room)
    
    # ==================== ADMIN ROUTES ====================
    
    @app.route('/admin/dashboard')
    @login_required
    @admin_required
    def admin_dashboard():
        total_customers = Customer.query.count()
        total_providers = Provider.query.count()
        pending_providers = Provider.query.filter_by(is_approved=False).count()
        total_bookings = Booking.query.count()
        completed_bookings = Booking.query.filter_by(status=BookingStatus.COMPLETED).count()
        total_revenue = db.session.query(db.func.sum(Booking.total_amount))\
            .filter(Booking.payment_status == 'paid').scalar() or 0
        
        recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(10).all()
        recent_providers = Provider.query.order_by(Provider.created_at.desc()).limit(10).all()
        
        # Monthly revenue chart data
        monthly_revenue = []
        for i in range(6):
            month_start = datetime.now().replace(day=1) - timedelta(days=30*i)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            revenue = db.session.query(db.func.sum(Booking.total_amount))\
                .filter(Booking.completed_date >= month_start,
                       Booking.completed_date <= month_end,
                       Booking.payment_status == 'paid').scalar() or 0
            monthly_revenue.append({
                'month': month_start.strftime('%b'),
                'revenue': float(revenue)
            })
        
        return render_template('admin_dashboard.html',
                             total_customers=total_customers,
                             total_providers=total_providers,
                             pending_providers=pending_providers,
                             total_bookings=total_bookings,
                             completed_bookings=completed_bookings,
                             total_revenue=total_revenue,
                             recent_bookings=recent_bookings,
                             recent_providers=recent_providers,
                             monthly_revenue=monthly_revenue[::-1])
    
    @app.route('/admin/providers')
    @login_required
    @admin_required
    def admin_providers():
        status = request.args.get('status', 'all')
        page = request.args.get('page', 1, type=int)
    
        query = Provider.query
        if status == 'pending':
            query = query.filter_by(is_approved=False)
        elif status == 'approved':
            query = query.filter_by(is_approved=True)
    
        providers = query.order_by(Provider.created_at.desc()).paginate(page=page, per_page=20)
    
        return render_template('approvals.html', providers=providers.items, current_status=status)
    
    @app.route('/admin/customers')
    @login_required
    @admin_required
    def admin_customers():
        page = request.args.get('page', 1, type=int)
        customers = Customer.query.order_by(Customer.created_at.desc()).paginate(page=page, per_page=20)
        return render_template('admin/customers.html', customers=customers)
    
    @app.route('/admin/customer/<int:customer_id>')
    @login_required
    @admin_required
    def admin_customer_detail(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        bookings = Booking.query.filter_by(customer_id=customer_id)\
            .order_by(Booking.created_at.desc()).limit(20).all()
        return render_template('admin/customer_detail.html', customer=customer, bookings=bookings)
    
    @app.route('/admin/customers/<int:customer_id>/toggle-status', methods=['POST'])
    @login_required
    @admin_required
    def toggle_customer_status(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        data = request.get_json()
        activate = data.get('activate', False)
    
        customer.is_active = activate
        db.session.commit()
    
        status = 'activated' if activate else 'blocked'
        flash(f'Customer {customer.full_name} has been {status}.', 'success')
        return jsonify({'success': True})
    
    @app.route('/admin/bookings')
    @login_required
    @admin_required
    def admin_bookings():
        status = request.args.get('status')
        page = request.args.get('page', 1, type=int)
        
        query = Booking.query
        if status:
            query = query.filter_by(status=status)
        
        bookings = query.order_by(Booking.created_at.desc()).paginate(page=page, per_page=20)
        return render_template('admin/bookings.html', bookings=bookings, current_status=status)
    
    @app.route('/admin/booking/<int:booking_id>')
    @login_required
    @admin_required
    def admin_booking_detail(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        return render_template('booking_detail.html', booking=booking)
    
    @app.route('/admin/provider/<int:provider_id>')
    @login_required
    @admin_required
    def admin_provider_detail(provider_id):
        provider = Provider.query.get_or_404(provider_id)
        bookings = Booking.query.filter_by(provider_id=provider_id)\
            .order_by(Booking.created_at.desc()).limit(20).all()
        return render_template('admin/provider_detail.html', provider=provider, bookings=bookings)
    
    @app.route('/admin/approve-provider/<int:provider_id>', methods=['POST'])
    @login_required
    @admin_required
    def approve_provider(provider_id):
        from datetime import datetime
        
        provider = Provider.query.get_or_404(provider_id)
        provider.is_approved = True
        provider.approved_date = datetime.utcnow()
        db.session.commit()
        flash(f'Provider {provider.full_name} approved successfully.', 'success')
        return redirect(url_for('admin_providers'))
    
    @app.route('/admin/reject-provider/<int:provider_id>', methods=['POST'])
    @login_required
    @admin_required
    def reject_provider(provider_id):
        provider = Provider.query.get_or_404(provider_id)
        reason = request.form.get('reason', 'No reason provided')
        provider.rejection_reason = reason
        provider.is_active = False
        db.session.commit()
        flash(f'Provider {provider.full_name} rejected.', 'warning')
        return redirect(url_for('admin_providers'))
    
    @app.route('/admin/services')
    @login_required
    @admin_required
    def admin_services():
        services = Service.query.all()
        return render_template('admin/services.html', services=services)
    
    @app.route('/admin/add-service', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def add_service():
        if request.method == 'POST':
            name = request.form.get('name')
            category = request.form.get('category')
            description = request.form.get('description')
            icon = request.form.get('icon', 'fas fa-tools')
            
            service = Service(
                name=name,
                category=category,
                description=description,
                icon=icon
            )
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        service.image = filename
            
            db.session.add(service)
            db.session.commit()
            flash('Service added successfully!', 'success')
            return redirect(url_for('admin_services'))
        
        return render_template('admin/add_service.html')
    
    @app.route('/admin/edit-service/<int:service_id>', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def edit_service(service_id):
        service = Service.query.get_or_404(service_id)
        
        if request.method == 'POST':
            service.name = request.form.get('name')
            service.category = request.form.get('category')
            service.description = request.form.get('description')
            service.icon = request.form.get('icon', service.icon)
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    filename = save_photo(file)
                    if filename:
                        service.image = filename
            
            db.session.commit()
            flash('Service updated successfully!', 'success')
            return redirect(url_for('admin_services'))
        
        return render_template('admin/edit_service.html', service=service)
    
    @app.route('/admin/delete-service/<int:service_id>', methods=['POST'])
    @login_required
    @admin_required
    def delete_service(service_id):
        service = Service.query.get_or_404(service_id)
        db.session.delete(service)
        db.session.commit()
        flash('Service deleted successfully.', 'success')
        return redirect(url_for('admin_services'))
    
    @app.route('/admin/reports')
    @login_required
    @admin_required
    def admin_reports():
        total_revenue = db.session.query(db.func.sum(Booking.total_amount))\
            .filter(Booking.payment_status == 'paid').scalar() or 0
        
        platform_fee = total_revenue * 0.10
        provider_payout = total_revenue - platform_fee
        
        bookings_by_status = db.session.query(Booking.status, db.func.count())\
            .group_by(Booking.status).all()
        
        top_providers = db.session.query(
            Provider.id,
            Provider.full_name,
            db.func.count(Booking.id).label('total_bookings'),
            db.func.sum(Booking.total_amount).label('total_revenue')
        ).join(Booking).filter(Booking.payment_status == 'paid')\
         .group_by(Provider.id).order_by(db.func.count(Booking.id).desc()).limit(10).all()
        
        return render_template('admin/reports.html',
                             total_revenue=total_revenue,
                             platform_fee=platform_fee,
                             provider_payout=provider_payout,
                             bookings_by_status=bookings_by_status,
                             top_providers=top_providers)
    
    @app.route('/admin/settings', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def admin_settings():
        if request.method == 'POST':
            current_user.full_name = request.form.get('full_name')
            current_user.email = request.form.get('email')
            current_user.phone = request.form.get('phone')
            
            new_password = request.form.get('new_password')
            if new_password:
                current_user.set_password(new_password)
            
            db.session.commit()
            flash('Settings updated successfully!', 'success')
        
        return render_template('admin/settings.html')
    
    # ==================== API ROUTES ====================
    
    @app.route('/api/providers/nearby')
    def api_nearby_providers():
        lat = request.args.get('lat', type=float)
        lng = request.args.get('lng', type=float)
        service_id = request.args.get('service_id', type=int)
        radius = request.args.get('radius', type=float, default=10)
        
        if not lat or not lng:
            return jsonify({'error': 'Latitude and longitude required'}), 400
        
        query = Provider.query.filter_by(is_approved=True, is_active=True)
        
        if service_id:
            query = query.join(Provider.services).filter(Service.id == service_id)
        
        providers = query.all()
        nearby = []
        
        for p in providers:
            if p.latitude and p.longitude:
                dist = calculate_distance(lat, lng, p.latitude, p.longitude)
                if dist <= radius:
                    nearby.append({
                        'id': p.id,
                        'name': p.full_name,
                        'city': p.city,
                        'latitude': p.latitude,
                        'longitude': p.longitude,
                        'distance': round(dist, 2),
                        'rating': p.average_rating,
                        'price': p.starting_price,
                        'profile_photo': p.profile_photo
                    })
        
        return jsonify({'providers': sorted(nearby, key=lambda x: x['distance'])})
    
    @app.route('/api/bookings/<int:booking_id>/status')
    @login_required
    def api_booking_status(booking_id):
        booking = Booking.query.get_or_404(booking_id)
        
        if not (current_user.id == booking.customer_id or 
                current_user.id == booking.provider_id or
                current_user.is_admin()):
            return jsonify({'error': 'Unauthorized'}), 403
        
        return jsonify({
            'booking_id': booking.id,
            'booking_number': booking.booking_number,
            'status': booking.status,
            'service_date': booking.service_date.isoformat(),
            'service_time': booking.service_time.strftime('%H:%M'),
            'total_amount': float(booking.total_amount),
            'payment_status': booking.payment_status
        })
    
    @app.route('/api/provider/<int:provider_id>/availability')
    def api_provider_availability(provider_id):
        date = request.args.get('date')
        
        if not date:
            return jsonify({'error': 'Date required'}), 400
        
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
        
        slots = TimeSlot.query.filter(
            TimeSlot.provider_id == provider_id,
            TimeSlot.date == date_obj,
            TimeSlot.is_booked == False
        ).order_by(TimeSlot.start_time).all()
        
        return jsonify({
            'date': date,
            'slots': [{
                'id': slot.id,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M')
            } for slot in slots]
        })
    
    # ==================== STATIC PAGES ====================
    
    @app.route('/about')
    def about():
        return render_template('about.html')
    
    @app.route('/contact', methods=['GET', 'POST'])
    def contact():
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            message = request.form.get('message')
            flash('Thank you for contacting us! We will get back to you soon.', 'success')
            return redirect(url_for('contact'))
        
        return render_template('contact.html')
    
    @app.route('/faq')
    def faq():
        faqs = [
            {'question': 'How do I book a service?', 'answer': 'Simply browse providers, select a service, choose a time slot, and complete the payment.'},
            {'question': 'How are service prices determined?', 'answer': 'Prices are set by individual service providers based on their experience and service quality.'},
            {'question': 'Can I cancel my booking?', 'answer': 'Yes, you can cancel up to 24 hours before the service time for a full refund.'},
            {'question': 'How do I become a service provider?', 'answer': 'Click on "Register as Provider" and fill out the application form. Our team will review and approve it.'}
        ]
        return render_template('faq.html', faqs=faqs)
    
    @app.route('/search')
    def search():
        query = request.args.get('q', '')
        if not query:
            return redirect(url_for('index'))
        
        providers = Provider.query.filter(
            Provider.is_approved == True,
            Provider.full_name.ilike(f'%{query}%') |
            Provider.city.ilike(f'%{query}%') |
            Provider.description.ilike(f'%{query}%')
        ).limit(20).all()
        
        services = Service.query.filter(
            Service.name.ilike(f'%{query}%') |
            Service.category.ilike(f'%{query}%') |
            Service.description.ilike(f'%{query}%')
        ).limit(20).all()
        
        return render_template('search_results.html',
                             query=query,
                             providers=providers,
                             services=services)
    
    # ==================== ERROR HANDLERS ====================
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # ==================== WEBHOOKS ====================
    
    @app.route('/webhooks/razorpay', methods=['POST'])
    def razorpay_webhook():
        data = request.json
        event = data.get('event')
        
        if event == 'payment.captured':
            payment_id = data['payload']['payment']['entity']['id']
            order_id = data['payload']['payment']['entity']['order_id']
            
            booking = Booking.query.filter_by(razorpay_order_id=order_id).first()
            if booking and booking.payment_status != 'paid':
                booking.payment_status = 'paid'
                booking.status = BookingStatus.CONFIRMED
                booking.razorpay_payment_id = payment_id
                db.session.commit()
                
                socketio.emit('payment_success', {
                    'booking_id': booking.id,
                    'booking_number': booking.booking_number
                }, room=f'booking_{booking.id}')
        
        return jsonify({'status': 'received'}), 200
    
    return app

# Create app instance
app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True)