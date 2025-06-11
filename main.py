from flask import Flask, render_template, request, jsonify, send_file
import pytubefix
from moviepy.editor import VideoFileClip, AudioFileClip
import os
import json
import threading
from werkzeug.utils import secure_filename
import time
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 * 1024  # 16GB max file size

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
SETTINGS_FILE = 'settings.json'
download_progress = {}
download_threads = {}  # Track download threads for cancel

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {"default_path": app.config['UPLOAD_FOLDER'], "theme": "dark"}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

def create_progress_callback(download_id, cancel_flag):
    def progress_callback(stream, chunk, bytes_remaining):
        if cancel_flag['cancel']:
            raise Exception('Download cancelled by user.')
        total_size = stream.filesize
        bytes_downloaded = total_size - bytes_remaining
        percentage = (bytes_downloaded / total_size) * 100
        current_time = time.time()
        start_time = download_progress[download_id]['start_time']
        elapsed_time = current_time - start_time
        speed = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
        time_remaining = ((total_size - bytes_downloaded) / speed) if speed > 0 else 0
        download_progress[download_id].update({
            'percentage': percentage,
            'bytes_downloaded': bytes_downloaded,
            'total_size': total_size,
            'speed': speed,
            'time_remaining': time_remaining,
            'elapsed_time': elapsed_time
        })
    return progress_callback

def download_worker(url, itag, download_type, download_id, cancel_flag):
    try:
        video = pytubefix.YouTube(url)
        stream = video.streams.get_by_itag(itag)
        if not stream:
            download_progress[download_id]['status'] = 'error'
            download_progress[download_id]['error'] = 'Stream not found'
            return

        download_progress[download_id].update({
            'total_size': stream.filesize,
            'status': 'downloading'
        })

        progress_callback = create_progress_callback(download_id, cancel_flag)
        video.register_on_progress_callback(progress_callback)

        filename = secure_filename(f"{video.title}_{itag}.{'mp4' if download_type == 'video' else 'mp3'}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        try:
            stream.download(output_path=app.config['UPLOAD_FOLDER'], filename=filename)
            if download_type == 'video_with_audio':
                download_progress[download_id]['status'] = 'processing_audio'
                audio_stream = video.streams.filter(only_audio=True).order_by('abr').desc().first()
                audio_filename = secure_filename(f"{video.title}_audio.mp3")
                audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
                audio_stream.download(output_path=app.config['UPLOAD_FOLDER'], filename=audio_filename)
                download_progress[download_id]['status'] = 'merging'
                video_clip = VideoFileClip(filepath)
                audio_clip = AudioFileClip(audio_path)
                final_filename = secure_filename(f"{video.title}_final.mp4")
                final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
                video_clip.set_audio(audio_clip).write_videofile(final_path, codec='libx264', threads=12, preset='superfast', verbose=False, logger=None)
                os.remove(filepath)
                os.remove(audio_path)
                filepath = final_path
                filename = final_filename

            download_progress[download_id].update({
                'status': 'complete',
                'percentage': 100,
                'filename': filename
            })
        except Exception as e:
            download_progress[download_id].update({
                'status': 'error',
                'error': str(e)
            })
    except Exception as e:
        download_progress[download_id].update({
            'status': 'error',
            'error': str(e)
        })

@app.route('/')
def index():
    return render_template('index.html', settings=load_settings())

@app.route('/check_video', methods=['POST'])
def check_video():
    url = request.json.get('url')
    if not url:
        return jsonify({'error': 'Please provide a URL'}), 400
    try:
        video = pytubefix.YouTube(url)
        streams = video.streams
        video_info = {
            'title': video.title,
            'thumbnail_url': video.thumbnail_url,
            'channel_url': video.channel_url,
            'channel_id': video.channel_id,
            'length': video.length,
            'views': video.views,
            'publish_date': str(video.publish_date),
            'video_id': video.video_id,
            'streams': []
        }
        for stream in streams:
            stream_info = {
                'itag': stream.itag,
                'mime_type': stream.mime_type,
                'resolution': getattr(stream, 'resolution', None),
                'abr': getattr(stream, 'abr', None),
                'filesize': getattr(stream, 'filesize_mb', 0),
                'type': 'video' if 'video' in stream.mime_type else 'audio'
            }
            video_info['streams'].append(stream_info)
        return jsonify(video_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    url = data.get('url')
    itag = data.get('itag')
    download_type = data.get('type')
    if not all([url, itag, download_type]):
        return jsonify({'error': 'Missing required parameters'}), 400
    download_id = str(uuid.uuid4())
    download_progress[download_id] = {
        'percentage': 0,
        'bytes_downloaded': 0,
        'total_size': 0,
        'speed': 0,
        'time_remaining': 0,
        'start_time': time.time(),
        'elapsed_time': 0,
        'status': 'initializing'
    }
    cancel_flag = {'cancel': False}
    download_threads[download_id] = cancel_flag
    thread = threading.Thread(target=download_worker, args=(url, itag, download_type, download_id, cancel_flag))
    thread.start()
    return jsonify({'success': True, 'download_id': download_id})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    if download_id in download_progress:
        progress = download_progress[download_id]
        if progress.get('status') == 'error':
            return jsonify({
                'error': progress.get('error', 'Unknown error'),
                'status': 'error'
            }), 400
        current_time = time.time()
        elapsed_time = current_time - progress['start_time']
        progress['elapsed_time'] = elapsed_time
        if elapsed_time > 0 and progress['bytes_downloaded'] > 0:
            progress['speed'] = progress['bytes_downloaded'] / elapsed_time
            if progress['speed'] > 0:
                remaining_bytes = progress['total_size'] - progress['bytes_downloaded']
                progress['time_remaining'] = remaining_bytes / progress['speed']
        return jsonify({
            'percentage': progress['percentage'],
            'time_remaining': progress['time_remaining'],
            'bytes_downloaded': progress['bytes_downloaded'],
            'total_size': progress['total_size'],
            'speed': progress['speed'],
            'elapsed_time': progress['elapsed_time'],
            'status': progress['status'],
            'filename': progress.get('filename')
        })
    return jsonify({'error': 'No progress information available'}), 404

@app.route('/cancel/<download_id>', methods=['POST'])
def cancel_download(download_id):
    if download_id in download_threads:
        download_threads[download_id]['cancel'] = True
        download_progress[download_id]['status'] = 'cancelled'
        return jsonify({'success': True})
    return jsonify({'error': 'Download not found'}), 404

@app.route('/download_file/<filename>')
def download_file(filename):
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], filename),
        as_attachment=True
    )

@app.route('/delete_file/<filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'File not found'}), 404

@app.route('/settings', methods=['GET', 'POST'])
def handle_settings():
    if request.method == 'POST':
        settings = request.json
        save_settings(settings)
        return jsonify({'success': True})
    return jsonify(load_settings())

if __name__ == '__main__':
    app.run(debug=True)
