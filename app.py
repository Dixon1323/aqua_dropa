from flask import Flask, request, jsonify, render_template, redirect, url_for, send_from_directory, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Order
import qrcode
import os
from itsdangerous import URLSafeSerializer
from flask_migrate import Migrate
import secrets
from dotenv import load_dotenv
from datetime import datetime, timedelta


load_dotenv()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///water_company.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'fallback-key')
db.init_app(app)
migrate = Migrate(app, db)
host_addr = "http://localhost:5000"

s = URLSafeSerializer(app.secret_key)

def encrypt_data(data):
    return s.dumps(data)

def decrypt_data(token):
    try:
        return s.loads(token)
    except Exception as e:
        return None

@app.route('/')
def index():
    if 'role' not in session:
        return redirect(url_for('login'))
    if session['role'] == 'admin':
        return render_template('index.html')
        # return redirect(url_for('dashboard'))
    elif session['role'] == 'delivery_agent':
        return redirect(url_for('delivery_agent_dashboard'))

@app.route('/admin/dashboard')
def dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # Fetch statistics from the database
    total_users = User.query.filter_by(role='user').count()
    print("total users: ",total_users)
    total_delivery_agents = User.query.filter_by(role='delivery_agent').count()
    print("total delivery agents: ", total_delivery_agents)
    total_orders = Order.query.count()
    print("total orders :",total_orders)
    pending_orders = Order.query.filter_by(status='Pending').count()
    print("pending orders :",pending_orders)
    delivered_orders = Order.query.filter_by(status='Delivered').count()
    print("delivered orders :",delivered_orders)

    # Orders in the last 24 hours
    last_24_hours = datetime.now() - timedelta(hours=24)
    orders_last_24_hours = Order.query.filter(Order.timestamp >= last_24_hours).count()
    print("order in last 24 hours :",orders_last_24_hours)

  

    # Pass data to the template
    return render_template(
        'index.html',
        total_users=total_users,
        total_delivery_agents=total_delivery_agents,
        total_orders=total_orders,
        pending_orders=pending_orders,
        delivered_orders=delivered_orders,
        orders_last_24_hours=orders_last_24_hours,
    )



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']  # Changed from email to username
        password = request.form['password']
        user = User.query.filter_by(name=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('index'))
            elif user.role == 'delivery_agent':
                return redirect(url_for('delivery_agent_dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials.")
    return render_template('login.html')


@app.route('/delivery_agent_dashboard')
def delivery_agent_dashboard():
    print(f"User session: {session.get('user_id')}, role: {session.get('role')}")

    if 'role' not in session or session['role'] != 'delivery_agent':
        return redirect(url_for('login'))
    
    delivery_agent_id = session['user_id']
    assigned_orders = Order.query.filter_by(delivery_agent_id=delivery_agent_id, status='Pending').all()
    
    return render_template('delivery_agent_dashboard.html', orders=assigned_orders)


@app.route('/logout_agent', methods=['POST'])
def logout_agent():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/admin/create_user_form')
def create_user_form():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    return render_template('create_user.html')

@app.route('/admin/edit_user_form')
def edit_user_form():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    users = User.query.filter_by(role='user').all()
    return render_template('edit_user.html', users=users)

@app.route('/admin/get_user/<int:id>', methods=['GET'])
def get_user(id):
    user = User.query.get(id)
    if user:
        return jsonify({
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "address": user.address,
            "location": user.location
        })
    return jsonify({"message": "User not found"}), 404


@app.route('/admin/reset_password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if not new_password:
            flash("Password field cannot be empty.")
            return redirect(request.url)

        user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        
        flash("Password has been reset successfully.")
        return redirect(url_for('view_delivery_agents'))
    
    return render_template('reset_password.html', user=user)



@app.route('/admin/view_users')
def view_users():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get the current page number from the request arguments (default to 1 if not provided)
    page = request.args.get('page', 1, type=int)
    
    # Define the number of users per page
    per_page = 10
    
    # Use the paginate method to retrieve users with pagination
    users = User.query.filter_by(role='user').paginate(page=page, per_page=per_page)
    
    return render_template('view_users.html', users=users)

@app.route('/admin/view_delivery_agents')
def view_delivery_agents():
    # Check admin authentication
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get page number and items per page from query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    
    # Query delivery agents with pagination
    delivery_agents = User.query.filter_by(role='delivery_agent').paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    # Calculate total pages and items
    total_agents = User.query.filter_by(role='delivery_agent').count()
    total_pages = (total_agents + per_page - 1) // per_page
    
    return render_template(
        'view_delivery_agents.html',
        agents=delivery_agents,
        per_page=per_page,
        total_pages=total_pages,
        current_page=page
    )


@app.route('/admin/create_user', methods=['POST'])
def create_user():
    data = request.form
    new_user = User(name=data['name'],email=data['email'],phone=data['phone'],address=data['address'],location=data.get('location'),role='user')
    db.session.add(new_user)
    db.session.commit()

    # Generate the encrypted QR code
    qr_data = encrypt_data(new_user.id)
    qr_url = f"{host_addr}/order/{qr_data}"
    qr = qrcode.make(qr_url)
    qr_file_path = os.path.join('static', 'qr_codes', f"{new_user.id}.png")
    qr.save(qr_file_path)

    # Save the path to the QR code image in the database
    new_user.qr_code = f"qr_codes/{new_user.id}.png"
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/admin/edit_user', methods=['POST'])
def edit_user():
    data = request.form
    user = User.query.get(data['id'])
    if user:
        user.name = data.get('name', user.name)
        user.email = data.get('email', user.email)
        user.phone = data.get('phone', user.phone)
        user.address = data.get('address', user.address)
        user.location = data.get('location', user.location)
        db.session.commit()
        return redirect(url_for('index'))
    return jsonify({"message": "User not found"}), 404

@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    user_name = request.form.get('name')
    if not user_name:
        return jsonify({"message": "No user name provided"}), 400

    user = User.query.filter_by(name=user_name).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    try:
        # If the user has associated orders, handle them first
        orders = Order.query.filter_by(user_id=user.id).all()
        for order in orders:
            # You can either delete these orders or nullify the user_id
            db.session.delete(order)  # Option 1: Delete the order
            # order.user_id = None  # Option 2: Nullify the foreign key (requires nullable=True in the model)

        # Now delete the user
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User and associated orders deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Error occurred: {str(e)}"}), 500


@app.route('/admin/delete_delivery_agent', methods=['POST'])
def delete_delivery_agent():
    agent_name = request.form.get('name')
    if not agent_name:
        return jsonify({"message": "No delivery agent name provided"}), 400

    agent = User.query.filter_by(name=agent_name, role='delivery_agent').first()
    if agent:
        db.session.delete(agent)
        db.session.commit()
        return redirect(url_for('view_delivery_agents'))

    return jsonify({"message": "Delivery agent not found"}), 404


@app.route('/admin/get_pending_orders_count')
def get_pending_orders_count():
    # Replace with actual database query to count pending orders
    pending_orders_count = Order.query.filter_by(status='Pending').count()
    # print("pending orders: ",pending_orders_count)
    return jsonify({'count': pending_orders_count})



@app.route('/admin/view_orders', methods=['GET'])
def view_orders():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get parameters from the request arguments
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)  # Default to 10 items per page
    status_filter = request.args.get('status', None)
    

    # Build the query with optional status filter
    query = Order.query
    

    if status_filter:
        query = query.filter_by(status=status_filter)

    query = query.order_by(Order.id.desc())

    # Apply pagination
    orders = query.paginate(page=page, per_page=per_page)
    
    # Fetch delivery agents for the form
    delivery_agents = User.query.filter_by(role='delivery_agent').all()
    
    return render_template('view_orders.html', orders=orders, delivery_agents=delivery_agents, per_page=per_page, status_filter=status_filter)


@app.route('/admin/assign_delivery_agent/<int:order_id>', methods=['POST'])
def assign_delivery_agent(order_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    delivery_agent_id = request.form.get('delivery_agent_id')
    order = Order.query.get(order_id)
    
    if order and delivery_agent_id:
        delivery_agent = User.query.get(delivery_agent_id)
        order.delivery_agent = delivery_agent
        db.session.commit()
    
    return redirect(url_for('view_orders'))


# @app.route('/admin/mark_delivered/<int:id>', methods=['POST'])
# def mark_delivered(id):
#     if 'role' not in session or session['role'] != 'admin':
#         return redirect(url_for('login'))
#     order = Order.query.get(id)
#     if order:
#         order.status = 'Delivered'
#         db.session.commit()
#         return redirect(url_for('view_orders'))
#     return jsonify({"message": "Order not found"}), 404



@app.route('/admin/mark_delivered/<int:id>', methods=['POST'])
def mark_delivered(id):
    # Check if the user is logged in and has the 'admin' role
    if 'role' not in session or session['role'] not in ['admin']:
        flash('You must be logged in as an admin to perform this action.')
        return redirect(url_for('login'))
    
    # Fetch the order by ID
    order = Order.query.get(id)
    
    # Check if the order exists
    if order:
        # Update the order status
        order.status = 'Delivered'
        db.session.commit()
        flash('Order marked as delivered.')
        return redirect(url_for('view_orders'))
    
    # Return an error response if the order is not found
    flash('Order not found.')
    return redirect(url_for('view_orders'))

@app.route('/delivery_agent/mark_delivered/<int:id>', methods=['POST'])
def delivery_agent_mark_delivered(id):
    # Debugging: Print session details
    print(f"Session: {session}")
    
    # Check if the user is logged in and has the 'delivery_agent' role
    if 'role' not in session or session['role'] != 'delivery_agent':
        flash('You must be logged in as a delivery agent to perform this action.')
        return redirect(url_for('login'))
    
    # Fetch the order by ID
    order = Order.query.get(id)
    
    # Check if the order exists
    if order:
        # Update the order status
        order.status = 'Delivered'
        db.session.commit()
        flash('Order marked as delivered.')
        return redirect(url_for('delivery_agent_dashboard'))
    
    # Return an error response if the order is not found
    flash('Order not found.')
    return redirect(url_for('delivery_agent_dashboard'))


@app.route('/admin/regenerate_qr_code/<int:user_id>', methods=['POST'])
def regenerate_qr_code(user_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user:
        # Generate the new encrypted QR code
        qr_data = encrypt_data(user.id)
        qr_url = f"{host_addr}/order/{qr_data}"
        qr = qrcode.make(qr_url)
        qr_file_path = os.path.join('static', 'qr_codes', f"{user.id}.png")
        qr.save(qr_file_path)

        # Update the path to the new QR code image in the database
        user.qr_code = f"qr_codes/{user.id}.png"
        db.session.commit()
        
        return redirect(url_for('view_users'))
    return jsonify({"message": "User not found"}), 404

@app.route('/admin/create_delivery_agent', methods=['GET', 'POST'])
def create_delivery_agent():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        data = request.form
        new_agent = User(
            name=data['name'],
            email=data['email'],
            phone=data['phone'],
            address=data['address'],
            role='delivery_agent'
        )
        new_agent.password = generate_password_hash(data['password'], method='pbkdf2:sha256')
        db.session.add(new_agent)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('create_delivery_agent.html')
    



@app.route('/order/<token>', methods=['GET', 'POST'])
def place_order(token):
    user_id = decrypt_data(token)
    if not user_id:
        return jsonify({"message": "Invalid or expired QR code"}), 404

    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    if request.method == 'POST':
        password = request.form['password']
        
        # Check password
        if password.lower() != f"{user.name.lower()}{user.id}":
            return jsonify({"message": "Invalid password. Please try again."}), 400
        
        # Extract product type and quantity
        product_type = request.form['product_type']
        quantity = request.form['quantity']
        
        # Create a new order
        new_order = Order(user_id=user_id, product_type=product_type, quantity=quantity)
        db.session.add(new_order)
        db.session.commit()

        return jsonify({"message": "Order placed successfully!"}), 200  # Return success response
    
    # For GET request, render the order form
    return render_template('order.html', user_id=user_id)



@app.route('/admin/download_qr_code/<int:user_id>', methods=['GET'])
def download_qr_code(user_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user and user.qr_code:
        return send_from_directory('static', user.qr_code, as_attachment=True)
    return jsonify({"message": "User or QR code not found"}), 404

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Create default admin user if not already created
        if not User.query.filter_by(name='admin').first():  # Changed from email to name
            default_admin = User(
                name='admin',
                email='admin@example.com',  # Default email, not used for login
                password=generate_password_hash('admin123', method='pbkdf2:sha256'),
                role='admin'
            )
            db.session.add(default_admin)
            db.session.commit()
    app.run(debug=True)
