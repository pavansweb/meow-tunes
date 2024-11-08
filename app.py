from flask import Flask, request, jsonify, send_from_directory, render_template
import requests
import os
import urllib.parse
import subprocess
import base64

app = Flask(__name__)

YOUTUBE_API_KEY = 'AIzaSyAZMHc8-c0ywvjiRs3CCxgLCnUBBRTTuXg'
# Spotify API credentials
CLIENT_ID = '94b35bcd2ade48df8bcde2a7af57ac8c'
CLIENT_SECRET = 'c201f35569f84ec8ac3407d02ee9d1d5'

# Define the directory to save downloads
DOWNLOAD_FOLDER = os.path.join(app.root_path, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    """Render the index template."""
    return render_template('index.html')

@app.route('/search-spotify-song', methods=['POST'])
def search_spotify_song():
    try:
        # Get the search term from the request
        search_term = request.json.get('searchTerm', '').strip()

        if not search_term:
            return jsonify({'success': False, 'error': 'No search term provided'}), 400

        # Get Spotify access token
        token_response = requests.post('https://accounts.spotify.com/api/token', data={
            'grant_type': 'client_credentials'
        }, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()
        })
        token_data = token_response.json()
        token = token_data.get('access_token')

        if not token:
            return jsonify({'success': False, 'error': 'Unable to fetch Spotify token'}), 500

        # Search Spotify for the track
        search_response = requests.get(f'https://api.spotify.com/v1/search?q={search_term}&type=track&limit=10', headers={
            'Authorization': f'Bearer {token}'
        })
        search_data = search_response.json()

        # Filter out duplicates based on song name and artist
        unique_songs = []
        song_set = set() 

        for song in search_data.get('tracks', {}).get('items', []):
            song_identifier = f"{song['name']}-{song['artists'][0]['name']}"
            if song_identifier not in song_set:
                song_set.add(song_identifier)
                unique_songs.append(song)

        # Return the filtered song results
        return jsonify({
            'success': True,
            'songs': unique_songs
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/song-info-to-audio', methods=['POST'])
def song_info_to_audio():
    try:
        # Get the song name and Spotify URL from the request
        data = request.json
        song_name = data.get('songName')
        spotify_song_url = data.get('spotifyUrl')
        
        if not song_name or not spotify_song_url:
            return jsonify({'success': False, 'error': 'Both song name and Spotify URL are required'}), 400
        
        print("Received song name:", song_name)
        print("Received Spotify song URL:", spotify_song_url)

        # Sanitize and create the filename
        sanitized_song_name = sanitize_filename(song_name)
        filename = f"{sanitized_song_name}.mp3"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)

        # Check if the file already exists locally
        if os.path.exists(filepath):
            print(f"File already exists: {filename}")
            return jsonify({
                'success': True,
                'audio_url': f'/downloads/{filename}',
                'song_name': song_name,
            })

        # If the file does not exist, make the RapidAPI call
        api_url = "https://spotify-downloader9.p.rapidapi.com/downloadSong"
        querystring = {"songId": spotify_song_url}
        headers = {
            "x-rapidapi-key": "403a0838eamshd14c1848197da01p118343jsn5f0026273ed4",
            "x-rapidapi-host": "spotify-downloader9.p.rapidapi.com"
        }

        # Make the API request
        response = requests.get(api_url, headers=headers, params=querystring)
        response_data = response.json()
        
        print("Spotify downloader API response:", response_data)

        if response.status_code == 200 and response_data.get('success'):
            data = response_data.get('data', {})
            download_link = data.get('downloadLink')
            
            # If download URL is provided, download the file
            if download_link:
                print(f"Downloading audio from: {download_link}")
                audio_response = requests.get(download_link, stream=True)
                with open(filepath, 'wb') as f:
                    f.write(audio_response.content)

                print(f"Download complete: {filepath}")
                return jsonify({
                    'success': True,
                    'audio_url': f'/downloads/{filename}',
                    'song_name': song_name,
                })
            else:
                return jsonify({'success': False, 'error': 'No download link found in response'}), 500
        else:
            error_message = response_data.get('message', 'Unknown error from Spotify API')
            print("Error from Spotify downloader API:", error_message)
            return jsonify({'success': False, 'error': error_message}), 500

    except Exception as e:
        print("Error in song_info_to_audio route:", e)
        return jsonify({'success': False, 'error': str(e)}), 500



def sanitize_filename(name):
    """Sanitize the song name to be a valid filename"""
    # Remove invalid characters for filenames
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in invalid_chars:
        name = name.replace(char, '_')

    # Ensure the filename doesn't end with a space or dot
    name = name.strip().rstrip('.')
    
    return name

@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)
