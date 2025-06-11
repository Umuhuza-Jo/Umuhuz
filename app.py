from flask import Flask, render_template, request, jsonify, send_file
import pytubefix
from moviepy.editor import VideoFileClip, AudioFileClip
import os
import json
import threading
from werkzeug.utils import secure_filename
import time
import uuid

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['UPLOAD_FOLDER'] = 'downloads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

download_progress = {}
download_threads = {}

def create_progress_callback(download_id):
    def progress_callback(stream, chunk, bytes_remaining):
        total_size = stream.filesize
        bytes_downloaded = total_size - bytes_remaining
        percentage = (bytes_downloaded / total_size) * 100
        current_time = time.time()
        start_time = download_progress[download_id]['start_time']
        elapsed_time = current_time - start_time
        speed = bytes_downloaded / elapsed_time if elapsed_time > 0 else 0
        time_remaining = (total_size - bytes_downloaded) / speed if speed > 0 else 0
        download_progress[download_id].update({
            'percentage': percentage,
            'bytes_downloaded': bytes_downloaded,
            'total_size': total_size,
            'speed': speed,
            'time_remaining': time_remaining,
            'elapsed_time': elapsed_time
        })
    return progress_callback

def threaded_download(url, itag, download_type, download_id):
    try:
        video = pytubefix.YouTube(url)
        stream = video.streams.get_by_itag(itag)
        if not stream:
            download_progress[download_id]['status'] = 'error'
            download_progress[download_id]['error'] = 'Stream not found'
            return
        download_progress[download_id].update({'total_size': stream.filesize, 'status': 'downloading'})
        progress_callback = create_progress_callback(download_id)
        video.register_on_progress_callback(progress_callback)

        filename = secure_filename(f"{video.title}_{itag}.{'mp4' if download_type == 'video' else 'mp3'}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Download file
        stream.download(output_path=app.config['UPLOAD_FOLDER'], filename=filename)

        # Merge audio if needed
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
            video_clip.set_audio(audio_clip).write_videofile(final_path, codec='libx264', threads=4, preset='superfast', verbose=False, logger=None)
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
        download_progress[download_id]['status'] = 'error'
        download_progress[download_id]['error'] = str(e)

@app.route('/')
def index():
    return render_template('index.html')

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
    # Run download in thread
    t = threading.Thread(target=threaded_download, args=(url, itag, download_type, download_id))
    t.daemon = True
    download_threads[download_id] = t
    t.start()
    return jsonify({'download_id': download_id})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    if download_id in download_progress:
        progress = download_progress[download_id]
        return jsonify(progress)
    return jsonify({'error': 'No progress information available'}), 404

@app.route('/cancel/<download_id>', methods=['POST'])
def cancel_download(download_id):
    # In this sample, we can't really kill a running thread safely.
    # But you can use a flag in download_progress to signal the thread to abort, and check that during download.
    if download_id in download_progress:
        download_progress[download_id]['status'] = 'cancelled'
        return jsonify({'success': True, 'message': 'Cancelled'})
    return jsonify({'error': 'Download not found'}), 404

@app.route('/download_file/<filename>')
def download_file(filename):
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], filename),
        as_attachment=True
    )

if __name__ == '__main__':
    app.run(debug=True)
