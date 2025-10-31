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
# This MUST be at the top
load_dotenv()

# --- AI Helper Functions ---
# We load models "on-demand" (inside the function) to save memory

def get_category_from_image(media_url):
    """Downloads an image, runs YOLO on it, and returns a category."""
    try:
        # <-- FIX: Load model inside the function
        yolo_model = YOLO('yolov8n.pt') 

        # --- NEW SIMPLER CODE ---
        # Pass the URL DIRECTLY to the predict function.
        # The AI will handle the download and opening.
        results = yolo_model.predict(media_url)
        # --- END NEW CODE ---

        # Get the top detection
        if results[0].names:
            top_result_index = results[0].probs.top1
            top_category = results[0].names[top_result_index]

            # Simple mapping (you can expand this)
            if 'pothole' in top_category:
                return 'Pothole'
            if 'person' in top_category:
                return 'Social Issue'

            return top_category

        return "Uncategorized Image"

    except Exception as e:
        print(f"Error processing image: {e}")
        return "Uncategorized"
    

def get_text_from_audio(media_url):
    """Downloads an audio/video file, runs Whisper, and returns the text."""
    try:
        # Load model inside the function to save memory
        whisper_model = whisper.load_model('tiny')
        response = requests.get(media_url)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        
        result = whisper_model.transcribe(temp_file_path)
        os.remove(temp_file_path) # Clean up the temp file
        
        return result.get('text', '')
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        return ""

def get_category_from_text(text_description):
    """Runs a simple keyword search to categorize text."""
    text_lower = text_description.lower()
    
    if 'pothole' in text_lower or 'road broken' in text_lower:
        return 'Pothole'
    if 'streetlight' in text_lower or 'light' in text_lower or 'lamp' in text_lower:
        return 'Streetlight Issue'
    if 'trash' in text_lower or 'garbage' in text_lower:
        return 'Waste Management'
    
    return 'General Inquiry'

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Allows your team's apps to call your API

# --- Supabase Connection ---
# This correctly reads the variables from your .env file
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("FATAL ERROR: SUPABASE_URL and SUPABASE_KEY not found in .env file or Environment Variables")

supabase: Client = create_client(url, key)


# --- API Routes ---

@app.route('/')
def home():
    """A test route to see if the server is running."""
    return "Python API for Smart City App is running!"

@app.route('/api/issue', methods=['POST'])
def create_issue():
    """This endpoint creates a new issue (now with media and AI)."""
    try:
        data = request.get_json()
        media_url = data.get('media_url')
        media_type = data.get('media_type')
        description_text = data.get('description_text', '')
        
        ai_category = "Uncategorized"
        ai_transcription = ""

        # --- AI PROCESSING ---
        if media_type == 'image':
            ai_category = get_category_from_image(media_url)
        
        elif media_type == 'audio' or media_type == 'video':
            ai_transcription = get_text_from_audio(media_url)
            ai_category = get_category_from_text(ai_transcription)
            description_text = f"User Text: {description_text}\n\nAudio Transcription: {ai_transcription}"
        
        elif description_text: # Text-only issue
            ai_category = get_category_from_text(description_text)
        # --- END AI PROCESSING ---
        
        insert_data = {
            "description_text": description_text,
            "lat": data.get('lat'),
            "lng": data.get('lng'),
            "media_url": media_url,
            "media_type": media_type,
            "status": "Pending",
            "category": ai_category
        }
        
        response = supabase.table('issues').insert(insert_data).execute()
        new_issue = response.data[0]
        
        return jsonify(new_issue), 201

    except Exception as e:
        print(f"Error creating issue: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/issues', methods=['GET'])
def get_issues():
    """This endpoint gets all issues for the admin dashboard."""
    try:
        response = supabase.table('issues').select('*').order('created_at', desc=True).execute()
        issues = response.data
        return jsonify(issues), 200

    except Exception as e:
        print(f"Error getting issues: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/issue/<int:issue_id>', methods=['PUT'])
def update_issue(issue_id):
    """This endpoint updates a single issue (e.g., status or assignment)."""
    try:
        data = request.get_json()
        update_data = {}

        if 'status' in data:
            update_data['status'] = data.get('status')
        
        if 'assigned_to' in data:
            update_data['assigned_to'] = data.get('assigned_to')
        
        if not update_data:
            return jsonify({"error": "No valid fields to update"}), 400

        response = supabase.table('issues') \
                         .update(update_data) \
                         .eq('id', issue_id) \
                         .execute()
        
        updated_issue = response.data[0]
        return jsonify(updated_issue), 200

    except Exception as e:
        print(f"Error updating issue: {e}")
        return jsonify({"error": str(e)}), 500

# --- This runs the app locally ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
