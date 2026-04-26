from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import string

db = SQLAlchemy()

# ==================== ENUMS ====================

class UserRole:
    CUSTOMER = 'customer'
    PROVIDER = 'provider'
    ADMIN = 'admin'

class BookingStatus:
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'

# ==================== MODELS ====================

class Customer(db.Model, UserMixin):
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_photo = db.Column(db.String(200), default='default-avatar.png')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default=UserRole.CUSTOMER)
    
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    pincode = db.Column(db.String(10))
    
    # Relationships
    bookings = db.relationship('Booking', backref='customer', lazy=True, foreign_keys='Booking.customer_id')
    reviews = db.relationship('Review', backref='customer', lazy=True)
    addresses = db.relationship('Address', backref='customer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_customer(self):
        return True
    
    def is_provider(self):
        return False
    
    def is_admin(self):
        return False

class Provider(db.Model, UserMixin):
    __tablename__ = 'providers'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_photo = db.Column(db.String(200), default='default-avatar.png')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default=UserRole.PROVIDER)
    
    city = db.Column(db.String(100))
    description = db.Column(db.Text)
    starting_price = db.Column(db.Float, default=0)
    years_experience = db.Column(db.Integer, default=0)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_approved = db.Column(db.Boolean, default=False)
    approved_date = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(200))
    average_rating = db.Column(db.Float, default=0)
    total_reviews = db.Column(db.Integer, default=0)
    
    # Working hours
    work_start = db.Column(db.String(5), default='09:00')
    work_end = db.Column(db.String(5), default='18:00')
    slot_duration = db.Column(db.Integer, default=60)
    break_start = db.Column(db.String(5), default='')
    break_end = db.Column(db.String(5), default='')
    weekend_days = db.Column(db.String(50), default='')
    
    # Relationships
    services = db.relationship('Service', secondary='provider_services', backref='providers')
    bookings = db.relationship('Booking', backref='provider', lazy=True, foreign_keys='Booking.provider_id')
    reviews = db.relationship('Review', backref='provider', lazy=True)
    time_slots = db.relationship('TimeSlot', backref='provider', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_customer(self):
        return False
    
    def is_provider(self):
        return True
    
    def is_admin(self):
        return False

class Admin(db.Model, UserMixin):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    profile_photo = db.Column(db.String(200), default='default-avatar.png')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), default=UserRole.ADMIN)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_customer(self):
        return False
    
    def is_provider(self):
        return False
    
    def is_admin(self):
        return True

class Service(db.Model):
    __tablename__ = 'services'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.Text)
    icon = db.Column(db.String(50), default='fas fa-tools')
    image = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Association table for many-to-many relationship between providers and services
provider_services = db.Table('provider_services',
    db.Column('provider_id', db.Integer, db.ForeignKey('providers.id')),
    db.Column('service_id', db.Integer, db.ForeignKey('services.id'))
)

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_number = db.Column(db.String(20), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'))
    service_name = db.Column(db.String(100))
    service_price = db.Column(db.Float)
    total_amount = db.Column(db.Float, nullable=False)
    address_line1 = db.Column(db.String(200))
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100))
    pincode = db.Column(db.String(10))
    service_date = db.Column(db.Date, nullable=False)
    service_time = db.Column(db.Time, nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey('time_slots.id'))
    status = db.Column(db.String(20), default=BookingStatus.PENDING)
    payment_status = db.Column(db.String(20), default='pending')
    razorpay_order_id = db.Column(db.String(100))
    razorpay_payment_id = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_date = db.Column(db.DateTime)
    cancelled_date = db.Column(db.DateTime)
    cancellation_reason = db.Column(db.String(200))
    
    def generate_booking_number(self):
        prefix = 'SRV'
        random_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        return f"{prefix}{random_str}"

class Review(db.Model):
    __tablename__ = 'reviews'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    sender_type = db.Column(db.String(20))  # 'customer' or 'provider'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TimeSlot(db.Model):
    __tablename__ = 'time_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey('providers.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_booked = db.Column(db.Boolean, default=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('provider_id', 'date', 'start_time', name='unique_time_slot'),
    )

class OTP(db.Model):
    __tablename__ = 'otps'
    
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(20), default='login')
    is_verified = db.Column(db.Boolean, default=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Address(db.Model):
    __tablename__ = 'addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    address_line1 = db.Column(db.String(200), nullable=False)
    address_line2 = db.Column(db.String(200))
    city = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    razorpay_payment_id = db.Column(db.String(100))
    razorpay_order_id = db.Column(db.String(100))
    razorpay_signature = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== INIT FUNCTIONS ====================

def init_services():
    """Initialize default services if none exist"""
    if Service.query.count() == 0:
        services = [
            # Home Services
            ('Electrician', 'Home Services', 'Electrical repairs, installations, and maintenance', 'fas fa-bolt'),
            ('Plumber', 'Home Services', 'Plumbing repairs, installations, and maintenance', 'fas fa-wrench'),
            ('Carpenter', 'Home Services', 'Woodworking, furniture repair, and installation', 'fas fa-hammer'),
            ('AC Service', 'Home Services', 'AC repair, maintenance, and installation', 'fas fa-snowflake'),
            ('Painter', 'Home Services', 'Interior and exterior painting services', 'fas fa-paint-roller'),
            ('Cleaner', 'Home Services', 'House and office cleaning services', 'fas fa-broom'),
            ('Gardener', 'Home Services', 'Garden maintenance and landscaping', 'fas fa-seedling'),
            ('Pest Control', 'Home Services', 'Pest removal and prevention services', 'fas fa-bug'),
            
            # Appliance Services
            ('Refrigerator Repair', 'Appliance Services', 'Refrigerator repair and maintenance', 'fas fa-thermometer-half'),
            ('Washing Machine Repair', 'Appliance Services', 'Washing machine repair services', 'fas fa-t-shirt'),
            ('Microwave Repair', 'Appliance Services', 'Microwave oven repair', 'fas fa-micro-wave'),
            ('TV Repair', 'Appliance Services', 'Television repair services', 'fas fa-tv'),
            
            # Beauty & Wellness
            ('Salon at Home', 'Beauty & Wellness', 'Haircut, styling, and beauty services at home', 'fas fa-cut'),
            ('Massage Therapy', 'Beauty & Wellness', 'Professional massage therapy', 'fas fa-hand-sparkles'),
            ('Yoga Classes', 'Beauty & Wellness', 'Personal yoga training at home', 'fas fa-pray'),
            
            # Automotive
            ('Car Wash', 'Automotive', 'Car washing and detailing services', 'fas fa-car'),
            ('Car Repair', 'Automotive', 'Basic car repair and maintenance', 'fas fa-wrench'),
            
            # Technology
            ('Computer Repair', 'Technology', 'Computer hardware and software repair', 'fas fa-laptop'),
            ('Mobile Repair', 'Technology', 'Smartphone repair services', 'fas fa-mobile-alt'),
            ('WiFi Installation', 'Technology', 'Home WiFi setup and configuration', 'fas fa-wifi'),
            
            # Moving Services
            ('Packers & Movers', 'Moving Services', 'Packing and moving services', 'fas fa-truck-moving'),
        ]
        
        for name, category, desc, icon in services:
            service = Service(name=name, category=category, description=desc, icon=icon)
            db.session.add(service)
        
        db.session.commit()
        print(f"✅ {len(services)} default services initialized")