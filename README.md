# TravelGoApp

A simple Flask web application with MongoDB integration for user registration.

## Setup Instructions

1. **Clone or download this project folder.**
2. **Create a virtual environment (optional but recommended):**
   
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```
   
3. **Install dependencies:**
   
   ```powershell
   pip install -r requirements.txt
   ```

4. **Update your MongoDB password:**
   
   - Open `app.py` and replace `<db_password>` in the MongoDB connection string with your actual MongoDB password.

5. **Run the Flask app:**
   
   ```powershell
   python app.py
   ```
   
   The app will be available at [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

## Project Structure

- `app.py` — Main Flask application
- `templates/` — HTML templates (index, register, dashboard)
- `requirements.txt` — Python dependencies
- `venv/` — (Optional) Python virtual environment

---

**Note:** This project is for educational/demo purposes. Passwords are stored in plain text for simplicity—never do this in production! Always hash passwords and use secure authentication.
