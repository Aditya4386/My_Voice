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
import logging

# Load your secret keys from the .env file
# This MUST be at the top
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# --- AI Helper Functions ---
# We load models "on-demand" (inside the function) to save memory

def get_category_from_image(media_url):
    """Downloads an image, runs YOLO on it, and returns a category."""
    try:
        # Load model inside the function to save memory
        yolo_model = YOLO('yolov8n.pt')

        # Download the image with a timeout and write to a temp file
        response = requests.get(media_url, timeout=15)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        # Run YOLO model on the saved image file
        results = yolo_model.predict(source=temp_file_path, save=False)

        # Delete the temporary file right away
        try:
            os.remove(temp_file_path)
        except Exception:
            pass

        # Validate results and extract the top class in a robust way
        if not results or len(results) == 0:
            return "Uncategorized Image"

        r = results[0]

        # If no boxes detected, return default
        boxes = getattr(r, 'boxes', None)
        if not boxes or len(boxes) == 0:
            return "Uncategorized Image"

        # Try to get confidences and class indices; fall back to the first detection
        try:
            confs = getattr(boxes, 'conf', None)
            clss = getattr(boxes, 'cls', None)

            # Convert to python lists if they are tensors
            if hasattr(confs, 'cpu'):
                confs = confs.cpu().numpy().tolist()
            if hasattr(clss, 'cpu'):
                clss = clss.cpu().numpy().tolist()

            if confs and clss:
                top_idx = int(confs.index(max(confs)))
                class_idx = int(clss[top_idx])
            else:
                # fallback
                class_idx = int(clss[0]) if clss else 0
        except Exception:
            # As a last resort, try to use the first box's class
            try:
                class_idx = int(boxes.cls[0].item())
            except Exception:
                class_idx = 0

        # Resolve names: results[0].names is usually a dict mapping idx->name
        names = getattr(r, 'names', None) or (getattr(yolo_model, 'model', None) and getattr(yolo_model.model, 'names', None))
        if isinstance(names, dict):
            top_category = names.get(class_idx, str(class_idx))
        else:
            try:
                top_category = names[class_idx]
            except Exception:
                top_category = str(class_idx)

        # Simple mapping (you can expand this)
        top_lower = top_category.lower()
        if 'pothole' in top_lower:
            return 'Pothole'
        if 'person' in top_lower:
            return 'Social Issue'

        return top_category

    except Exception:
        logger.exception("Error processing image from URL: %s", media_url)
        return "Uncategorized"
    

def get_text_from_audio(media_url):
    """Downloads an audio/video file, runs Whisper, and returns the text."""
    try:
        # Load model inside the function to save memory
        whisper_model = whisper.load_model('tiny')
        # Add timeout and check status to avoid silent hangs
        response = requests.get(media_url, timeout=30)
        response.raise_for_status()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name
        
        result = whisper_model.transcribe(temp_file_path)
        os.remove(temp_file_path) # Clean up the temp file
        
        return result.get('text', '')
        
    except Exception:
        logger.exception("Error processing audio from URL: %s", media_url)
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
    # Fail fast with a clear message rather than creating a client with None
    raise RuntimeError("FATAL ERROR: SUPABASE_URL and SUPABASE_KEY not found in .env file or Environment Variables")

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
        logger.info("[create_issue] Received request data: %s", data)
        media_url = data.get('media_url')
        media_type = data.get('media_type')
        description_text = data.get('description_text', '')

        ai_category = "Uncategorized"
        ai_transcription = ""

        # --- AI PROCESSING ---
        if media_type == 'image':
            logger.info("[create_issue] Processing image via get_category_from_image...")
            ai_category = get_category_from_image(media_url)

        elif media_type == 'audio' or media_type == 'video':
            logger.info("[create_issue] Processing audio/video via get_text_from_audio...")
            ai_transcription = get_text_from_audio(media_url)
            ai_category = get_category_from_text(ai_transcription)
            description_text = f"User Text: {description_text}\n\nAudio Transcription: {ai_transcription}"

        elif description_text:  # Text-only issue
            ai_category = get_category_from_text(description_text)
        # --- END AI PROCESSING ---

        insert_data = {
            "description_text": description_text,
            "lat": data.get('lat'),
            "lng": data.get('lng'),
            "media_url": media_url,
            "media_type": media_type,
            "status": "Pending",
            "category": ai_category,
        }

        logger.info("[create_issue] Inserting to Supabase, insert_data: %s", insert_data)
        response = supabase.table('issues').insert(insert_data).execute()

        # Defensive: ensure response has expected data
        if not hasattr(response, 'data') or not response.data:
            logger.error("[create_issue] Supabase insert returned no data. Response: %s", response)
            return jsonify({"error": "Insert failed", "response": str(response)}), 500

        new_issue = response.data[0]
        return jsonify(new_issue), 201

    except Exception:
        logger.exception("Error creating issue")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/issues', methods=['GET'])
def get_issues():
    """This endpoint gets all issues for the admin dashboard."""
    try:
        response = supabase.table('issues').select('*').order('created_at', desc=True).execute()
        issues = response.data
        return jsonify(issues), 200

    except Exception:
        logger.exception("Error getting issues")
        return jsonify({"error": "Internal server error"}), 500

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

    except Exception:
        logger.exception("Error updating issue id=%s", issue_id)
        return jsonify({"error": "Internal server error"}), 500

# --- This runs the app locally ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)