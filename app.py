from flask import Flask, request, jsonify, send_from_directory, render_template
import requests
import os
import base64
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)  

# Load credentials and configuration from environment variables
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
GITHUB_TOKEN = os.getenv('MY_GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'pavansweb/pookiefy-song-storage')
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/"
RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')

# Define the directory to save downloads
DOWNLOAD_FOLDER = os.path.join(app.root_path, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def upload_to_github(filename, file_path):
    """Uploads a file to GitHub using the GitHub API."""
    with open(file_path, 'rb') as f:
        file_content = f.read()
    encoded_content = base64.b64encode(file_content).decode()

    file_url = f"downloads/{filename}"
    payload = {
        "message": f"Add {filename}",
        "content": encoded_content,
        "branch": "main"
    }

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    response = requests.put(f'{GITHUB_API_URL}{file_url}', headers=headers, data=json.dumps(payload))

    if response.status_code == 201:
        file_info = response.json()
        download_url = file_info['content']['download_url']
        return download_url
    else:
        print("Error uploading file to GitHub:", response.json())
        return None

@app.route('/')
def index():
    print(GITHUB_TOKEN)
    return render_template('index.html')

@app.route('/search-spotify-song', methods=['POST'])
def search_spotify_song():
    try:
        search_term = request.json.get('searchTerm', '').strip()

        if not search_term:
            return jsonify({'success': False, 'error': 'No search term provided'}), 400

        token_response = requests.post('https://accounts.spotify.com/api/token', data={
            'grant_type': 'client_credentials'
        }, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(f'{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}'.encode()).decode()
        })
        token_data = token_response.json()
        token = token_data.get('access_token')

        if not token:
            return jsonify({'success': False, 'error': 'Unable to fetch Spotify token'}), 500

        search_response = requests.get(f'https://api.spotify.com/v1/search?q={search_term}&type=track&limit=10', headers={
            'Authorization': f'Bearer {token}'
        })
        search_data = search_response.json()

        unique_songs = []
        song_set = set()

        for song in search_data.get('tracks', {}).get('items', []):
            song_identifier = f"{song['name']}-{song['artists'][0]['name']}"
            if song_identifier not in song_set:
                song_set.add(song_identifier)
                unique_songs.append(song)

        return jsonify({
            'success': True,
            'songs': unique_songs
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/song-info-to-audio', methods=['POST'])
def song_info_to_audio():
    try:
        data = request.json
        song_name = data.get('songName')
        spotify_song_url = data.get('spotifyUrl')
        
        if not song_name or not spotify_song_url:
            return jsonify({'success': False, 'error': 'Both song name and Spotify URL are required'}), 400
        
        print("Received song name:", song_name)
        print("Received Spotify song URL:", spotify_song_url)

        sanitized_song_name = sanitize_filename(song_name)
        filename = f"{sanitized_song_name}.mp3"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)

        file_url = f"downloads/{filename}"
        github_headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        response = requests.get(f'{GITHUB_API_URL}{file_url}', headers=github_headers)

        if response.status_code == 200:
            file_info = response.json()
            download_url = file_info['download_url']
            print("The song file already exists in github. Providing the direct link:", download_url)          
            return jsonify({
                'success': True,
                'audio_url': download_url,
                'song_name': song_name,
            })
        elif response.status_code == 404:
            print(f"File does not exist on GitHub, proceeding to download: {filename}")

            if os.path.exists(filepath):
                print(f"File already exists locally: {filename}")
                download_url = upload_to_github(filename, filepath)
                if download_url:
                    os.remove(filepath)
                    print(f"Local file {filename} removed after upload.")                   
                    return jsonify({
                        'success': True,
                        'audio_url': download_url,
                        'song_name': song_name,
                    })
                else:
                    return jsonify({'success': False, 'error': 'Error uploading file to GitHub'}), 500

            api_url = "https://spotify-downloader9.p.rapidapi.com/downloadSong"
            querystring = {"songId": spotify_song_url}
            headers = {
                "x-rapidapi-key": RAPIDAPI_KEY,
                "x-rapidapi-host": "spotify-downloader9.p.rapidapi.com"
            }

            response = requests.get(api_url, headers=headers, params=querystring)
            response_data = response.json()

            if response.status_code == 200 and response_data.get('success'):
                data = response_data.get('data', {})
                download_link = data.get('downloadLink')

                if download_link:
                    print(f"Downloading audio from: {download_link}")
                    audio_response = requests.get(download_link, stream=True)
                    with open(filepath, 'wb') as f:
                        f.write(audio_response.content)

                    print(f"Download complete: {filepath}")
                    download_url = upload_to_github(filename, filepath)
                    if download_url:
                        os.remove(filepath)
                        print(f"Local file {filename} removed after upload.")                        
                        return jsonify({
                            'success': True,
                            'audio_url': download_url,
                            'song_name': song_name,
                        })
                    else:
                        return jsonify({'success': False, 'error': 'Error uploading file to GitHub'}), 500
                else:
                    return jsonify({'success': False, 'error': 'No download link found in response'}), 500
            else:
                error_message = response_data.get('message', 'Unknown error from Spotify API')
                print("Error from Spotify downloader API:", error_message)
                return jsonify({'success': False, 'error': error_message}), 500
        else:
            print("Error checking file on GitHub:", response.json())
            return jsonify({'success': False, 'error': 'Error checking file on GitHub'}), 500

    except Exception as e:
        print("Error in song_info_to_audio route:", e)
        return jsonify({'success': False, 'error': str(e)}), 500

def sanitize_filename(name):
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name.strip().rstrip('.')

@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)
 