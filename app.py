from flask import Flask, request, jsonify, send_from_directory, render_template
import requests
import os
import base64
import json
from datetime import datetime

app = Flask(__name__)

YOUTUBE_API_KEY = 'AIzaSyAZMHc8-c0ywvjiRs3CCxgLCnUBBRTTuXg'
# Spotify API credentials
CLIENT_ID = '94b35bcd2ade48df8bcde2a7af57ac8c'
CLIENT_SECRET = 'c201f35569f84ec8ac3407d02ee9d1d5'

# GitHub credentials (use environment variables for security)
GITHUB_TOKEN = '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'
GITHUB_REPO = 'pavansweb/pookiefy-song-storage'
GITHUB_API_URL = 'https://api.github.com/repos/pavansweb/pookiefy-song-storage/contents/'

# Define the directory to save downloads
DOWNLOAD_FOLDER = os.path.join(app.root_path, 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def upload_to_github(filename, file_path):
    """Uploads a file to GitHub using the GitHub API."""
    # Read the audio file in binary mode and encode to base64
    with open(file_path, 'rb') as f:
        file_content = f.read()
    encoded_content = base64.b64encode(file_content).decode()

    # Construct the GitHub API request payload
    file_url = f"downloads/{filename}"
    payload = {
        "message": f"Add {filename}",
        "content": encoded_content,
        "branch": "main"  # Specify the branch where the file should be uploaded
    }

    # GitHub API headers with authentication
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    # Send the POST request to GitHub API
    response = requests.put(f'{GITHUB_API_URL}{file_url}', headers=headers, data=json.dumps(payload))

    if response.status_code == 201:
        # Return the URL to the uploaded file in the repository
        file_info = response.json()
        download_url = file_info['content']['download_url']
        return download_url
    else:
        print("Error uploading file to GitHub:", response.json())
        return None

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

        # Check if the file already exists in the GitHub repository
        file_url = f"downloads/{filename}"
        github_headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        # Send a GET request to check if the file exists in the GitHub repository
        response = requests.get(f'{GITHUB_API_URL}{file_url}', headers=github_headers)

        if response.status_code == 200:
            # If the file exists, return the existing download URL
            file_info = response.json()
            download_url = file_info['download_url']
            print("The song file already exists in github. Providing the direct link:", download_url)          
            return jsonify({
                'success': True,
                'audio_url': download_url,  # This is the direct URL you need
                'song_name': song_name,
            })
        elif response.status_code == 404:
            # If the file does not exist, proceed with the download process
            print(f"File does not exist on GitHub, proceeding to download: {filename}")

            # Check if the file already exists locally
            if os.path.exists(filepath):
                print(f"File already exists locally: {filename}")
                # Upload the file to GitHub
                download_url = upload_to_github(filename, filepath)
                if download_url:
                    # After successful upload, remove the local file
                    os.remove(filepath)
                    print(f"Local file {filename} removed after upload.")                   
                    return jsonify({
                        'success': True,
                        'audio_url': download_url,
                        'song_name': song_name,
                    })
                else:
                    return jsonify({'success': False, 'error': 'Error uploading file to GitHub'}), 500

            # If the file does not exist locally, make the RapidAPI call
            api_url = "https://spotify-downloader9.p.rapidapi.com/downloadSong"
            querystring = {"songId": spotify_song_url}
            headers = {
                "x-rapidapi-key": "827a267b18mshccf0ef3588021b6p1eed8djsn6d526d9496ee",
                "x-rapidapi-host": "spotify-downloader9.p.rapidapi.com"
            }

            # Make the API request
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
                    # Upload the downloaded file to GitHub
                    download_url = upload_to_github(filename, filepath)
                    if download_url:
                        # After successful upload, remove the local file
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
            # If GitHub API returns an error other than 404
            print("Error checking file on GitHub:", response.json())
            return jsonify({'success': False, 'error': 'Error checking file on GitHub'}), 500

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
