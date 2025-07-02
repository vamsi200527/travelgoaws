from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import boto3
from boto3.dynamodb.conditions import Key, Attr
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import uuid
import random

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# AWS Setup using IAM Role
REGION = 'ap-south-1'  # Replace with your actual AWS region
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns_client = boto3.client('sns', region_name=REGION)

users_table = dynamodb.Table('travelgo_users')
trains_table = dynamodb.Table('trains')
bookings_table = dynamodb.Table('bookings')

SNS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:353250843450:TravelGoBookingTopic'  # Replace with actual SNS topic ARN

def send_sns_notification(subject, message):
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
    except Exception as e:
        print(f"SNS Error: {e}")


def send_sns_notification(subject, message):
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
    except Exception as e:
        print(f"SNS Error: {e}")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        existing = users_table.get_item(Key={'email': email})
        if 'Item' in existing:
            flash('Email already exists!', 'error')
            return render_template('register.html')
        hashed_password = generate_password_hash(password)
        users_table.put_item(Item={'email': email, 'password': hashed_password})
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_table.get_item(Key={'email': email})
        if 'Item' in user and check_password_hash(user['Item']['password'], password):
            session['email'] = email
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password!', 'error')
            return render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))
    user_email = session['email']
    response = bookings_table.query(
        KeyConditionExpression=Key('user_email').eq(user_email),
        ScanIndexForward=False
    )
    bookings = response.get('Items', [])
    for booking in bookings:
        if 'total_price' in booking:
            try:
                booking['total_price'] = float(booking['total_price'])
            except Exception:
                booking['total_price'] = 0.0
    return render_template('dashboard.html', username=user_email, bookings=bookings)

@app.route('/train')
def train():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('train.html')

@app.route('/confirm_train_details')
def confirm_train_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking_details = {
        'name': request.args.get('name'),
        'train_number': request.args.get('trainNumber'),
        'source': request.args.get('source'),
        'destination': request.args.get('destination'),
        'departure_time': request.args.get('departureTime'),
        'arrival_time': request.args.get('arrivalTime'),
        'price_per_person': Decimal(request.args.get('price')),
        'travel_date': request.args.get('date'),
        'num_persons': int(request.args.get('persons')),
        'item_id': request.args.get('trainId'),
        'booking_type': 'train',
        'user_email': session['email'],
        'total_price': Decimal(request.args.get('price')) * int(request.args.get('persons'))
    }

    response = bookings_table.query(
        IndexName='GSI_ItemDate',
        KeyConditionExpression=Key('item_id').eq(booking_details['item_id']) & Key('travel_date').eq(booking_details['travel_date'])
    )

    booked_seats = set()
    for b in response.get('Items', []):
        if 'seats_display' in b:
            booked_seats.update(b['seats_display'].split(', '))

    all_seats = [f"S{i}" for i in range(1, 101)]
    available_seats = [seat for seat in all_seats if seat not in booked_seats]

    if len(available_seats) < booking_details['num_persons']:
        flash("Not enough seats available.", "error")
        return redirect(url_for("train"))

    session['pending_booking'] = booking_details
    return render_template('confirm_train_details.html', booking=booking_details, available_seats=available_seats[:booking_details['num_persons']])

@app.route('/final_confirm_train_booking', methods=['POST'])
def final_confirm_train_booking():
    if 'email' not in session:
        return jsonify({'success': False, 'message': 'User not logged in'}), 401

    booking_data = session.pop('pending_booking', None)
    if not booking_data:
        return jsonify({'success': False, 'message': 'No pending booking found'}), 400

    response = bookings_table.query(
        IndexName='GSI_ItemDate',
        KeyConditionExpression=Key('item_id').eq(booking_data['item_id']) & Key('travel_date').eq(booking_data['travel_date'])
    )

    booked_seats = set()
    for b in response.get('Items', []):
        if 'seats_display' in b:
            booked_seats.update(b['seats_display'].split(', '))

    all_seats = [f"S{i}" for i in range(1, 101)]
    available_seats = [seat for seat in all_seats if seat not in booked_seats]

    if len(available_seats) < booking_data['num_persons']:
        return jsonify({'success': False, 'message': 'Not enough seats available'}), 400

    allocated_seats = random.sample(available_seats, booking_data['num_persons'])
    booking_data['seats_display'] = ', '.join(allocated_seats)
    booking_data['booking_id'] = str(uuid.uuid4())
    booking_data['booking_date'] = datetime.now().isoformat()

    bookings_table.put_item(Item=booking_data)

    send_sns_notification(
        subject="Train Booking Confirmed",
        message=f"Train {booking_data['train_number']} from {booking_data['source']} to {booking_data['destination']} on {booking_data['travel_date']} is confirmed.\nSeats: {booking_data['seats_display']}\nTotal: ₹{booking_data['total_price']}"
    )

    return jsonify({'success': True, 'message': 'Train booking confirmed successfully!', 'redirect': url_for('dashboard')})

@app.route('/bus')
def bus():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('bus.html')

@app.route('/confirm_bus_details')
def confirm_bus_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking_details = {
        'name': request.args.get('name'),
        'source': request.args.get('source'),
        'destination': request.args.get('destination'),
        'time': request.args.get('time'),
        'type': request.args.get('type'),
        'price_per_person': Decimal(request.args.get('price')),
        'travel_date': request.args.get('date'),
        'num_persons': int(request.args.get('persons')),
        'item_id': request.args.get('busId'),
        'booking_type': 'bus',
        'user_email': session['email'],
        'total_price': Decimal(request.args.get('price')) * int(request.args.get('persons'))
    }
    session['pending_booking'] = booking_details
    return render_template('confirm_bus_details.html', booking=booking_details)

@app.route('/select_bus_seats')
def select_bus_seats():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = {
        'name': request.args.get('name'),
        'source': request.args.get('source'),
        'destination': request.args.get('destination'),
        'time': request.args.get('time'),
        'type': request.args.get('type'),
        'price_per_person': Decimal(request.args.get('price')),
        'travel_date': request.args.get('date'),
        'num_persons': int(request.args.get('persons')),
        'item_id': request.args.get('busId'),
        'booking_type': 'bus',
        'user_email': session['email'],
        'total_price': Decimal(request.args.get('price')) * int(request.args.get('persons'))
    }

    # Get booked seats
    response = bookings_table.query(
        IndexName='GSI_ItemDate',
        KeyConditionExpression=Key('item_id').eq(booking['item_id']) & Key('travel_date').eq(booking['travel_date'])
    )

    booked_seats = set()
    for b in response.get('Items', []):
        if 'seats_display' in b:
            booked_seats.update(b['seats_display'].split(', '))

    all_seats = [f"S{i}" for i in range(1, 41)]
    session['pending_booking'] = booking

    return render_template("select_bus_seats.html", booking=booking, booked_seats=booked_seats, all_seats=all_seats)

@app.route('/final_confirm_bus_booking', methods=['POST'])
def final_confirm_bus_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = session.pop('pending_booking', None)
    selected_seats = request.form['selected_seats']

    if not booking or not selected_seats:
        flash("Booking failed! Missing data.", "error")
        return redirect(url_for("bus"))

    # Prevent double booking
    response = bookings_table.query(
        IndexName='GSI_ItemDate',
        KeyConditionExpression=Key('item_id').eq(booking['item_id']) & Key('travel_date').eq(booking['travel_date'])
    )
    existing = set()
    for b in response.get('Items', []):
        if 'seats_display' in b:
            existing.update(b['seats_display'].split(', '))

    selected = selected_seats.split(', ')
    if any(s in existing for s in selected):
        flash("One or more selected seats are already booked!", "error")
        return redirect(url_for("bus"))

    booking['seats_display'] = selected_seats
    booking['booking_id'] = str(uuid.uuid4())
    booking['booking_date'] = datetime.now().isoformat()

    bookings_table.put_item(Item=booking)
    
    send_sns_notification(
        subject="Bus Booking Confirmed",
        message=f"Your bus from {booking['source']} to {booking['destination']} on {booking['travel_date']} is confirmed.\nSeats: {booking['seats_display']}\nTotal: ₹{booking['total_price']}"
    )

    flash('Bus booking confirmed!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/flight')
def flight():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('flight.html')

@app.route('/confirm_flight_details')
def confirm_flight_details():
    booking = {
        'flight_id': request.args['flight_id'],
        'airline': request.args['airline'],
        'flight_number': request.args['flight_number'],
        'source': request.args['source'],
        'destination': request.args['destination'],
        'departure_time': request.args['departure'],
        'arrival_time': request.args['arrival'],
        'travel_date': request.args['date'],
        'num_persons': int(request.args['passengers']),
        'price_per_person': float(request.args['price']),
    }
    booking['total_price'] = booking['price_per_person'] * booking['num_persons']
    return render_template('confirm_flight_details.html', booking=booking)

@app.route('/confirm_flight_booking', methods=['POST'])
def confirm_flight_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = {
        'booking_type': 'flight',
        'flight_id': request.form['flight_id'],
        'airline': request.form['airline'],
        'flight_number': request.form['flight_number'],
        'source': request.form['source'],
        'destination': request.form['destination'],
        'departure_time': request.form['departure_time'],
        'arrival_time': request.form['arrival_time'],
        'travel_date': request.form['travel_date'],
        'num_persons': int(request.form['num_persons']),
        'price_per_person': Decimal(request.form['price_per_person']),
        'total_price': Decimal(request.form['total_price']),
        'user_email': session['email'],
        'booking_date': datetime.now().isoformat(),
        'booking_id': str(uuid.uuid4())
    }

    bookings_table.put_item(Item=booking)

    # ✅ SNS for Flight
    send_sns_notification(
        subject="Flight Booking Confirmed",
        message=f"Your flight booking on {booking['travel_date']} from {booking['source']} to {booking['destination']} with {booking['airline']} is confirmed.\nTotal: ₹{booking['total_price']}"
    )

    flash('Flight booking confirmed successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/hotel')
def hotel():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('hotel.html')

@app.route('/confirm_hotel_details')
def confirm_hotel_details():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = {
        'name': request.args.get('name'),
        'location': request.args.get('location'),
        'checkin_date': request.args.get('checkin'),
        'checkout_date': request.args.get('checkout'),
        'num_rooms': int(request.args.get('rooms')),
        'num_guests': int(request.args.get('guests')),
        'price_per_night': Decimal(request.args.get('price')),
        'rating': int(request.args.get('rating'))
    }

    ci = datetime.fromisoformat(booking['checkin_date'])
    co = datetime.fromisoformat(booking['checkout_date'])
    nights = (co - ci).days
    booking['nights'] = nights
    booking['total_price'] = booking['price_per_night'] * booking['num_rooms'] * nights

    return render_template('confirm_hotel_details.html', booking=booking)

@app.route('/confirm_hotel_booking', methods=['POST'])
def confirm_hotel_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking = {
        'booking_type': 'hotel',
        'name': request.form['hotel_name'],
        'location': request.form['location'],
        'checkin_date': request.form['checkin'],
        'checkout_date': request.form['checkout'],
        'num_rooms': int(request.form['rooms']),
        'num_guests': int(request.form['guests']),
        'price_per_night': Decimal(request.form['price']),
        'rating': int(request.form['rating']),
        'user_email': session['email'],
        'booking_date': datetime.now().isoformat(),
        'booking_id': str(uuid.uuid4())
    }

    ci = datetime.fromisoformat(booking['checkin_date'])
    co = datetime.fromisoformat(booking['checkout_date'])
    nights = (co - ci).days
    booking['total_price'] = booking['price_per_night'] * booking['num_rooms'] * nights

    bookings_table.put_item(Item=booking)

    # ✅ SNS for Hotel
    send_sns_notification(
        subject="Hotel Booking Confirmed",
        message=f"Hotel booking at {booking['name']} in {booking['location']} from {booking['checkin_date']} to {booking['checkout_date']} is confirmed.\nTotal: ₹{booking['total_price']}"
    )

    flash('Hotel booking confirmed successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/cancel_booking', methods=['POST'])
def cancel_booking():
    if 'email' not in session:
        return redirect(url_for('login'))

    booking_id = request.form.get('booking_id')
    user_email = session['email']

    if not booking_id:
        flash("Error: Booking ID is missing for cancellation.", 'error')
        return redirect(url_for('dashboard'))

    try:
        bookings_table.delete_item(
            Key={'user_email': user_email, 'booking_date': request.form.get('booking_date')}
        )
        flash(f"Booking cancelled successfully!", 'success')
    except Exception as e:
        flash(f"Failed to cancel booking: {str(e)}", 'error')

    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')