import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv


# ... (your other imports) ...
import whisper
import requests
from PIL import Image
from ultralytics import YOLO
import io
import os
import tempfile

# --- AI Model Loading ---
# Load models once when the app starts
# This is slow, but only happens on startup
print("Loading AI models...")
yolo_model = YOLO('yolov8n.pt')  # 'n' is the nano model, fast and small
whisper_model = whisper.load_model('tiny') # 'tiny' is the fastest model
print("AI models loaded.")


# --- AI Helper Functions ---

def get_category_from_image(media_url):
    """Downloads an image, runs YOLO on it, and returns a category."""
    try:
        response = requests.get(media_url)
        img = Image.open(io.BytesIO(response.content))
        
        # Run YOLO model on the image
        results = yolo_model.predict(img)
        
        # Get the top detection
        if results[0].names:
            top_result_index = results[0].probs.top1
            top_category = results[0].names[top_result_index]
            
            # Simple mapping from YOLO classes to your categories
            # You will need to expand this list!
            if 'pothole' in top_category:
                return 'Pothole'
            if 'person' in top_category: # Example
                return 'Social Issue'
            
            return top_category # Return the detected object name
        
        return "Uncategorized Image"
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return "Uncategorized"

def get_text_from_audio(media_url):
    """Downloads an audio/video file, runs Whisper, and returns the text."""
    try:
        response = requests.get(media_url)
        
        # Create a temporary file to save the audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        
        # Run Whisper to transcribe the audio file
        result = whisper_model.transcribe(temp_file_path)
        
        # Delete the temporary file
        os.remove(temp_file_path)
        
        return result.get('text', '')
        
    except Exception as e:
        print(f"Error processing audio: {e}")
        return ""

def get_category_from_text(text_description):
    """Runs a simple keyword search to categorize text."""
    text_lower = text_description.lower()
    
    # You will build a better keyword list here
    if 'pothole' in text_lower or 'road broken' in text_lower:
        return 'Pothole'
    if 'streetlight' in text_lower or 'light' in text_lower or 'lamp' in text_lower:
        return 'Streetlight Issue'
    if 'trash' in text_lower or 'garbage' in text_lower:
        return 'Waste Management'
    
    return 'General Inquiry'

# --- (Your @app.route('/') function and others go below this) ---


# Load your secret keys from the .env file
load_dotenv()

app = Flask(__name__)
CORS(app) # This allows anyone (your team) to call your API

# Initialize your Supabase connection
url = os.environ.get("https://juxefzyltfqwanmrzmtk.supabase.co")
key = os.environ.get("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imp1eGVmenlsdGZxd2FubXJ6bXRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjE3OTgwODIsImV4cCI6MjA3NzM3NDA4Mn0.xyydZEdTbr5LCu7woXQdkUYzgHtvLgiTJqnc5I6a6cg")
supabase: Client = create_client(url, key)

# This is a "test route" to see if your server is running
@app.route('/')
def home():
    return "Python API for Smart City App is running!"

# --- PHASE 1 ENDPOINTS ---

# This endpoint creates a new text-only issue
# This endpoint creates a new issue (now with media)
    @app.route('/api/issue', methods=['POST'])
    def create_issue():
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
                # First, get text from the audio
                ai_transcription = get_text_from_audio(media_url)
                # Then, categorize that text
                ai_category = get_category_from_text(ai_transcription)
                
                # If user also sent text, combine them
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
                "category": ai_category  # <-- WE ARE NOW ADDING THE AI CATEGORY!
            }
            
            response = supabase.table('issues').insert(insert_data).execute()
            new_issue = response.data[0]
            
            return jsonify(new_issue), 201

        except Exception as e:
            return jsonify({"error": str(e)}), 500
# You will add more endpoints here later (GET /api/issues, PUT /api/issue/:id)

# This runs the app
if __name__ == '__main__':
    app.run(debug=True, port=5000)

# ... (your get_issues function is above this) ...

    # This endpoint updates a single issue (e.g., changes its status)
    # This endpoint updates a single issue (e.g., status or assignment)
    @app.route('/api/issue/<int:issue_id>', methods=['PUT'])
    def update_issue(issue_id):
        try:
            # 1. Get the new data from the request
            data = request.get_json()
            
            # 2. Prepare the data to update
            #    This is flexible. It will only update the fields that are sent.
            update_data = {}
            if 'status' in data:
                update_data['status'] = data.get('status')
            
            if 'assigned_to' in data:
                update_data['assigned_to'] = data.get('assigned_to') # <-- NEW
            
            if not update_data:
                return jsonify({"error": "No valid fields to update"}), 400

            # 3. Update the 'issues' table where the 'id' matches
            response = supabase.table('issues') \
                             .update(update_data) \
                             .eq('id', issue_id) \
                             .execute()
            
            # 4. Return the updated issue data
            updated_issue = response.data[0]
            return jsonify(updated_issue), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500
    # ... (your if __name__ == '__main__': is below this) ...