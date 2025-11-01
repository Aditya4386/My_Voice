import os
import io
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

# --- AI Imports ---
import whisper
import requests
from PIL import Image
from ultralytics import YOLO

# Load your secret keys from the .env file
load_dotenv()

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Allows your team's apps to call your API

# --- Supabase Connection ---
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY") # Your SERVICE_ROLE key

if not url or not key:
    print("FATAL ERROR: SUPABASE_URL and SUPABASE_KEY not found")

# We initialize Supabase with the SERVICE_ROLE key for admin powers
supabase: Client = create_client(url, key)


# --- NEW: Authentication Helper ---
def get_user_from_token():
    """Gets the user's info from the Authorization token."""
    try:
        # The app (Person 2/3) must send a header like:
        # "Authorization: Bearer [THEIR_TOKEN_FROM_SUPABASE_LOGIN]"
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None, {"error": "Missing Authorization header"}, 401

        jwt_token = auth_header.split(" ")[1]
        
        # We use Supabase to validate the token and get the user
        user_response = supabase.auth.get_user(jwt_token)
        user = user_response.user
        
        if not user:
            return None, {"error": "Invalid token"}, 401
            
        # Get the user's role from our 'profiles' table
        profile_response = supabase.table('profiles').select('role').eq('id', user.id).single().execute()
        role = profile_response.data.get('role', 'citizen')

        return user, role, None # user, role, no error
    
    except Exception as e:
        print(f"Auth error: {e}")
        return None, {"error": "Invalid token"}, 401

# --- AI Helper Functions ---
# (These are the same as before, no changes needed)
def get_category_from_image(media_url):
    try:
        yolo_model = YOLO('yolov8n.pt') 
        response = requests.get(media_url)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        results = yolo_model.predict(temp_file_path)
        os.remove(temp_file_path)
        
        if results[0].names:
            top_result_index = results[0].probs.top1
            top_category = results[0].names[top_result_index]
            if 'pothole' in top_category: return 'Pothole'
            if 'person' in top_category: return 'Social Issue'
            return top_category
        return "Uncategorized Image"
    except Exception as e:
        print(f"Error processing image: {e}")
        return "Uncategorized"

def get_text_from_audio(media_url):
    try:
        whisper_model = whisper.load_model('tiny')
        response = requests.get(media_url)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        result = whisper_model.transcribe(temp_file_path)
        os.remove(temp_file_path)
        return result.get('text', '')
    except Exception as e:
        print(f"Error processing audio: {e}")
        return ""

def get_category_from_text(text_description):
    text_lower = text_description.lower()
    if 'pothole' in text_lower or 'road broken' in text_lower: return 'Pothole'
    if 'streetlight' in text_lower or 'light' in text_lower: return 'Streetlight Issue'
    if 'trash' in text_lower or 'garbage' in text_lower: return 'Waste Management'
    return 'General Inquiry'

# --- API Routes (Now Secured) ---

@app.route('/')
def home():
    return "Python API for Smart City App is running!"

@app.route('/api/issue', methods=['POST'])
def create_issue():
    """Creates a new issue (SECURED)"""
    user, role, error = get_user_from_token()
    if error:
        return jsonify(error), 401 # Return 401 Unauthorized

    try:
        data = request.get_json()
        media_url = data.get('media_url')
        media_type = data.get('media_type')
        description_text = data.get('description_text', '')
        
        ai_category = "Uncategorized"
        if media_type == 'image':
            ai_category = get_category_from_image(media_url)
        elif media_type == 'audio' or media_type == 'video':
            ai_transcription = get_text_from_audio(media_url)
            description_text = f"User Text: {description_text}\n\nAudio Transcription: {ai_transcription}"
            ai_category = get_category_from_text(description_text)
        elif description_text:
            ai_category = get_category_from_text(description_text)
        
        insert_data = {
            "description_text": description_text,
            "lat": data.get('lat'),
            "lng": data.get('lng'),
            "media_url": media_url,
            "media_type": media_type,
            "status": "Pending",
            "category": ai_category,
            "submitted_by": user.id  # <-- FINAL FIX: We add the user's ID!
        }
        
        response = supabase.table('issues').insert(insert_data).execute()
        new_issue = response.data[0]
        return jsonify(new_issue), 201

    except Exception as e:
        print(f"Error creating issue: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/issues', methods=['GET'])
def get_issues():
    """Gets all issues (SECURED - Admin Only)"""
    user, role, error = get_user_from_token()
    if error:
        return jsonify(error), 401
        
    # <-- FINAL FIX: Only allow "admin" to see all issues
    if role != 'admin':
        return jsonify({"error": "You must be an admin to access this"}), 403 # 403 Forbidden

    try:
        response = supabase.table('issues').select('*').order('created_at', desc=True).execute()
        issues = response.data
        return jsonify(issues), 200
    except Exception as e:
        print(f"Error getting issues: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/issue/<int:issue_id>', methods=['PUT'])
def update_issue(issue_id):
    """Updates an issue (SECURED - Admin Only)"""
    user, role, error = get_user_from_token()
    if error:
        return jsonify(error), 401

    if role != 'admin':
        return jsonify({"error": "You must be an admin to access this"}), 403

    try:
        data = request.get_json()
        update_data = {}
        if 'status' in data:
            update_data['status'] = data.get('status')
        if 'assigned_to' in data:
            update_data['assigned_to'] = data.get('assigned_to')
        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        response = supabase.table('issues').update(update_data).eq('id', issue_id).execute()
        updated_issue = response.data[0]
        return jsonify(updated_issue), 200
    except Exception as e:
        print(f"Error updating issue: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/operator/location', methods=['POST'])
def update_operator_location():
    """Updates an operator's live GPS location (SECURED)"""
    user, role, error = get_user_from_token()
    if error:
        return jsonify(error), 401

    # <-- FINAL FIX: Only operators can update their location
    if role != 'operator':
        return jsonify({"error": "You must be an operator to update location"}), 403

    try:
        data = request.get_json()
        new_location = {"lat": data.get('lat'), "lng": data.get('lng')}

        # Use the user.id from the token, not from the JSON body
        response = supabase.table('operators') \
                         .update({"current_location": new_location}) \
                         .eq('user_id', user.id) \
                         .execute()
        
        if not response.data:
            return jsonify({"error": "Operator profile not found"}), 404

        return jsonify(response.data[0]), 200
    except Exception as e:
        print(f"Error updating location: {e}")
        return jsonify({"error": str(e)}), 500

# --- This runs the app locally ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)

