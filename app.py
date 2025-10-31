import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from dotenv import load_dotenv

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
            # 1. Get JSON data from the request
            data = request.get_json()
            
            # 2. Prepare the data to insert into the database
            insert_data = {
                "description_text": data.get('description_text'),
                "lat": data.get('lat'),
                "lng": data.get('lng'),
                "media_url": data.get('media_url'),   # <-- NEW
                "media_type": data.get('media_type'), # <-- NEW
                "status": "Pending"
                # "submitted_by": user.id # We will add this later
            }
            
            # 3. Insert the data into the 'issues' table
            response = supabase.table('issues').insert(insert_data).execute()
            
            # 4. Return the new issue data back to the app
            new_issue = response.data[0]
            
            # --- AI PROCESSING WILL GO HERE IN THE NEXT STEP ---
            # (We will add code here to process the issue after it's created)
            # ---
            
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