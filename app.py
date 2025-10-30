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
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# This is a "test route" to see if your server is running
@app.route('/')
def home():
    return "Python API for Smart City App is running!"

# --- PHASE 1 ENDPOINTS ---

# This endpoint creates a new text-only issue
@app.route('/api/issue', methods=['POST'])
def create_issue():
    try:
        # 1. Get JSON data from the request (from the app)
        data = request.get_json()
        description = data.get('description_text')
        lat = data.get('lat')
        lng = data.get('lng')

        # We will skip user authentication for now to keep it simple

        # 2. Prepare the data to insert into the database
        insert_data = {
            "description_text": description,
            "lat": lat,
            "lng": lng,
            "status": "Pending"
            # "submitted_by": user.id # We will add this in a later phase
        }

        # 3. Insert the data into the 'issues' table
        response = supabase.table('issues').insert(insert_data).execute()

        # 4. Return the new issue data back to the app
        new_issue = response.data[0]
        return jsonify(new_issue), 201 # 201 means "Created"

    except Exception as e:
        # If anything goes wrong, return an error
        return jsonify({"error": str(e)}), 500

# You will add more endpoints here later (GET /api/issues, PUT /api/issue/:id)

# This runs the app
if __name__ == '__main__':
    app.run(debug=True, port=5000)

# ... (your get_issues function is above this) ...

    # This endpoint updates a single issue (e.g., changes its status)
    @app.route('/api/issue/<int:issue_id>', methods=['PUT'])
    def update_issue(issue_id):
        try:
            # 1. Get the new data from the request
            data = request.get_json()
            new_status = data.get('status')
            # You could also get 'assigned_to', etc. here in the future
            
            # 2. Prepare the data to update
            update_data = {
                "status": new_status
            }
            
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