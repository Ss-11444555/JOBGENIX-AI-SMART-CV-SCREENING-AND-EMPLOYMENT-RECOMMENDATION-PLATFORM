from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def home():
    return jsonify({'message': 'Flask Server Running!', 'status': 'online'})

@app.route('/api')
def api():
    return jsonify({
        'message': 'API Online',
        'endpoints': {
            'job_seeker_register': '/api/auth/job-seeker/register',
            'test': '/api/test'
        }
    })

@app.route('/api/test')
def test():
    return jsonify({'test': 'success', 'data': 'API is working!'})

@app.route('/api/auth/job-seeker/register', methods=['POST', 'OPTIONS'])
def register():
    from flask import request
    if request.method == 'OPTIONS':
        return jsonify({'status': 'preflight'})
    
    data = request.get_json() or {}
    return jsonify({
        'success': True,
        'message': 'Registration endpoint is working',
        'received_data': data,
        'token': 'dummy_token_for_testing'
    })

if __name__ == '__main__':
    print("🚀 Starting Flask Server on port 5001")
    print("📡 Open: http://localhost:5001")
    print("📡 API: http://localhost:5001/api")
    print("🔧 Press Ctrl+C to stop")
    print("-" * 50)
    app.run(debug=True, port=5001, host='0.0.0.0')