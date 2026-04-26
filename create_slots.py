from app import app
from models import db, TimeSlot, Provider
from datetime import datetime, timedelta

print("=" * 50)
print("Creating Time Slots for Provider")
print("=" * 50)

with app.app_context():
    # Find the provider
    provider = Provider.query.first()
    
    if not provider:
        print("No provider found!")
        print("Available providers:")
        all_providers = Provider.query.all()
        for p in all_providers:
            print(f"  - {p.full_name} (ID: {p.id})")
    else:
        print(f"Found provider: {provider.full_name} (ID: {provider.id})")
        
        # Delete all existing time slots for this provider
        deleted = TimeSlot.query.filter_by(provider_id=provider.id).delete()
        print(f"Deleted {deleted} existing slots")
        
        # Create new time slots for next 30 days
        today = datetime.now().date()
        slots_created = 0
        
        for i in range(30):
            date = today + timedelta(days=i)
            
            # Morning slot: 9 AM - 12 PM
            slot1 = TimeSlot(
                provider_id=provider.id,
                date=date,
                start_time=datetime.strptime("09:00", "%H:%M").time(),
                end_time=datetime.strptime("12:00", "%H:%M").time(),
                is_booked=False
            )
            db.session.add(slot1)
            
            # Afternoon slot: 2 PM - 5 PM
            slot2 = TimeSlot(
                provider_id=provider.id,
                date=date,
                start_time=datetime.strptime("14:00", "%H:%M").time(),
                end_time=datetime.strptime("17:00", "%H:%M").time(),
                is_booked=False
            )
            db.session.add(slot2)
            
            # Evening slot: 6 PM - 9 PM
            slot3 = TimeSlot(
                provider_id=provider.id,
                date=date,
                start_time=datetime.strptime("18:00", "%H:%M").time(),
                end_time=datetime.strptime("21:00", "%H:%M").time(),
                is_booked=False
            )
            db.session.add(slot3)
            
            slots_created += 3
        
        db.session.commit()
        print(f"SUCCESS! Created {slots_created} time slots for {provider.full_name}")
        print(f"Slots available for the next 30 days")
        print(f"Each day has: 9AM-12PM, 2PM-5PM, 6PM-9PM")
        
        # Verify slots were created
        verify_slots = TimeSlot.query.filter_by(provider_id=provider.id).count()
        print(f"\nVerification: {verify_slots} total slots in database")
        
        # Show next 5 available slots
        upcoming = TimeSlot.query.filter_by(
            provider_id=provider.id,
            is_booked=False
        ).order_by(TimeSlot.date, TimeSlot.start_time).limit(5).all()
        
        print(f"\nNext 5 available slots:")
        for slot in upcoming:
            start = slot.start_time.strftime('%I:%M %p')
            end = slot.end_time.strftime('%I:%M %p')
            print(f"  {slot.date}: {start} - {end}")

print("\n" + "=" * 50)
print("Done! Refresh your booking page.")
print("=" * 50)