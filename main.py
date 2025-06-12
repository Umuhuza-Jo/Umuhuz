import flet as ft
import pytubefix
from moviepy.editor import VideoFileClip, AudioFileClip
import os
import threading
import time
import uuid

DOWNLOADS_DIR = "downloads"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

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

def threaded_download(url, itag, download_type, download_id, page):
    try:
        video = pytubefix.YouTube(url, client='WEB')
        stream = video.streams.get_by_itag(itag)
        if not stream:
            download_progress[download_id]['status'] = 'error'
            download_progress[download_id]['error'] = 'Stream not found'
            return
        download_progress[download_id].update({'total_size': stream.filesize, 'status': 'downloading'})
        progress_callback = create_progress_callback(download_id)
        video.register_on_progress_callback(progress_callback)

        filename = f"{video.title}_{itag}.{'mp4' if download_type == 'video' else 'mp3'}"
        filename = filename.replace("/", "_").replace("\\", "_")
        filepath = os.path.join(DOWNLOADS_DIR, filename)

        # Download file
        stream.download(output_path=DOWNLOADS_DIR, filename=filename)

        # Merge audio if needed
        if download_type == 'video_with_audio':
            download_progress[download_id]['status'] = 'processing_audio'
            audio_stream = video.streams.filter(only_audio=True).order_by('abr').desc().first()
            audio_filename = f"{video.title}_audio.mp3".replace("/", "_").replace("\\", "_")
            audio_path = os.path.join(DOWNLOADS_DIR, audio_filename)
            audio_stream.download(output_path=DOWNLOADS_DIR, filename=audio_filename)

            download_progress[download_id]['status'] = 'merging'
            video_clip = VideoFileClip(filepath)
            audio_clip = AudioFileClip(audio_path)
            final_filename = f"{video.title}_final.mp4".replace("/", "_").replace("\\", "_")
            final_path = os.path.join(DOWNLOADS_DIR, final_filename)
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
        page.update()
    except Exception as e:
        download_progress[download_id]['status'] = 'error'
        download_progress[download_id]['error'] = str(e)
        page.update()

def main(page: ft.Page):
    page.title = "YouTube Downloader"
    page.scroll = ft.ScrollMode.AUTO

    url_input = ft.TextField(label="YouTube URL", width=500)
    check_button = ft.ElevatedButton("Check Video", disabled=False)
    info_text = ft.Text("")
    streams_dropdown = ft.Dropdown(label="Select stream")
    download_type_dropdown = ft.Dropdown(
        label="Download type",
        options=[
            ft.dropdown.Option("video"),
            ft.dropdown.Option("audio"),
            ft.dropdown.Option("video_with_audio")
        ],
        value="video"
    )
    download_button = ft.ElevatedButton("Download", disabled=True)
    progress_bar = ft.ProgressBar(width=500, value=0)
    progress_info = ft.Text("")
    download_link = ft.Text("")
    cancel_button = ft.ElevatedButton("Cancel Download", disabled=True)

    download_id = None
    selected_stream = None

    def check_video_click(e):
        nonlocal selected_stream
        url = url_input.value.strip()
        if not url:
            info_text.value = "Please enter a YouTube URL"
            page.update()
            return
        try:
            video = pytubefix.YouTube(url, client='WEB')
            streams = video.streams
            info_text.value = f"Title: {video.title}\nDuration: {video.length}s\nViews: {video.views}\nPublished: {video.publish_date}"
            # Populate dropdown
            streams_dropdown.options.clear()
            for stream in streams:
                stream_type = 'video' if 'video' in stream.mime_type else 'audio'
                resolution = getattr(stream, 'resolution', '')
                abr = getattr(stream, 'abr', '')
                filesize = getattr(stream, 'filesize_mb', 0)
                label = f"{stream_type.upper()} | itag: {stream.itag} | {resolution or abr} | {filesize:.2f} MB | {stream.mime_type}"
                streams_dropdown.options.append(ft.dropdown.Option(key=stream.itag, text=label))
            if streams_dropdown.options:
                streams_dropdown.value = streams_dropdown.options[0].key
            download_button.disabled = False
            page.update()
        except Exception as ex:
            info_text.value = f"Error: {ex}"
            streams_dropdown.options.clear()
            download_button.disabled = True
            page.update()

    def download_click(e):
        nonlocal download_id, selected_stream
        url = url_input.value.strip()
        itag = streams_dropdown.value
        d_type = download_type_dropdown.value
        if not all([url, itag, d_type]):
            info_text.value = "Please select a stream and type"
            page.update()
            return
        download_button.disabled = True
        cancel_button.disabled = False
        page.update()
        download_id_local = str(uuid.uuid4())
        download_id = download_id_local
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

        def update_progress():
            while download_progress[download_id]['status'] not in ['complete', 'error', 'cancelled']:
                p = download_progress[download_id]
                progress_bar.value = p['percentage'] / 100
                progress_info.value = f"{p['percentage']:.2f}% | {p['bytes_downloaded']/1e6:.2f} MB / {p['total_size']/1e6:.2f} MB | Speed: {p['speed']/1e6:.2f} MB/s | ETA: {p['time_remaining']:.1f}s | Status: {p['status']}"
                page.update()
                time.sleep(0.5)
            p = download_progress[download_id]
            progress_bar.value = p['percentage'] / 100
            progress_info.value = f"{p['percentage']:.2f}% | {p['bytes_downloaded']/1e6:.2f} MB / {p['total_size']/1e6:.2f} MB | Speed: {p['speed']/1e6:.2f} MB/s | ETA: {p['time_remaining']:.1f}s | Status: {p['status']}"
            if p['status'] == 'complete':
                download_link.value = f"Download: {os.path.join(DOWNLOADS_DIR, p['filename'])}"
            elif p['status'] == 'error':
                download_link.value = f"Error: {p.get('error', 'Unknown error')}"
            else:
                download_link.value = ""
            download_button.disabled = False
            cancel_button.disabled = True
            page.update()

        # Start download thread
        t = threading.Thread(target=threaded_download, args=(url, itag, d_type, download_id, page))
        t.daemon = True
        download_threads[download_id] = t
        t.start()
        # Start a progress polling thread
        threading.Thread(target=update_progress, daemon=True).start()

    def cancel_click(e):
        nonlocal download_id
        if download_id and download_id in download_progress:
            download_progress[download_id]['status'] = 'cancelled'
            progress_info.value = "Download cancelled."
            cancel_button.disabled = True
            download_button.disabled = False
            page.update()

    check_button.on_click = check_video_click
    download_button.on_click = download_click
    cancel_button.on_click = cancel_click

    page.add(
        ft.Column([
            url_input,
            check_button,
            info_text,
            streams_dropdown,
            download_type_dropdown,
            download_button,
            cancel_button,
            progress_bar,
            progress_info,
            download_link
        ])
    )

ft.app(target=main)
