document.addEventListener('DOMContentLoaded', () => {
    // Theme Handling
    const html = document.documentElement;
    const themeSwitcher = document.getElementById('themeSwitcher');
    const themeIcon = document.getElementById('themeIcon');

    // Set initial theme to light
    let theme = localStorage.getItem('theme') || "light";
    html.setAttribute('data-theme', theme);
    themeIcon.textContent = (theme === "light") ? "🌞" : "🌙";

    themeSwitcher.addEventListener('click', () => {
        theme = (theme === "light") ? "dark" : "light";
        html.setAttribute('data-theme', theme);
        themeIcon.textContent = (theme === "light") ? "🌞" : "🌙";
        localStorage.setItem('theme', theme);
    });

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.tab + 'Tab').classList.add('active');
        });
    });

    // Video Check
    const urlForm = document.getElementById('urlForm');
    const videoInfo = document.getElementById('videoInfo');
    const checkThumbBox = document.getElementById('checkThumbBox');
    const checkThumb = document.getElementById('checkThumb');
    let currentVideo = null;

    urlForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = document.getElementById('videoUrl').value;
        videoInfo.classList.add('hidden');
        document.getElementById('videoStreams').innerHTML = '';
        document.getElementById('audioStreams').innerHTML = '';

        // Show loading thumbnail if possible
        let thumbUrl = "";
        // Try to extract video ID from url (simple YouTube pattern)
        let vidMatch = url.match(/(?:v=|\/)([0-9A-Za-z_-]{11})/);
        if (vidMatch && vidMatch[1]) {
            thumbUrl = `https://img.youtube.com/vi/${vidMatch[1]}/hqdefault.jpg`;
            checkThumb.src = thumbUrl;
            checkThumbBox.classList.remove('hidden');
        } else {
            checkThumbBox.classList.add('hidden');
        }

        // Do check_video request
        const res = await fetch('/check_video', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({url})
        });

        checkThumbBox.classList.add('hidden');
        if (!res.ok) {
            alert('Failed to fetch video info!');
            return;
        }
        const info = await res.json();
        currentVideo = {url, ...info};
        if (info.error) {
            alert(info.error);
            return;
        }
        showVideoInfo(info);
    });

    function showVideoInfo(info) {
        videoInfo.classList.remove('hidden');
        document.getElementById('thumbnail').src = info.thumbnail_url;
        document.getElementById('title').textContent = info.title;
        document.getElementById('channel').innerHTML = `Channel: <a href="${info.channel_url}" target="_blank">${info.channel_id}</a>`;
        document.getElementById('views').textContent = info.views;
        document.getElementById('date').textContent = info.publish_date;
        fillStreams(info.streams);
    }

    function getFormat(mime) {
        if (!mime) return "-";
        let parts = mime.split('/');
        return parts.length > 1 ? parts[1] : parts[0];
    }

    function fillStreams(streams) {
        const videoBody = document.getElementById('videoStreams');
        const audioBody = document.getElementById('audioStreams');
        videoBody.innerHTML = '';
        audioBody.innerHTML = '';
        streams.forEach(stream => {
            if (stream.type === 'video') {
                let tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${stream.resolution || '-'}</td>
                    <td>${stream.filesize ? stream.filesize.toFixed(2) : '-'}</td>
                    <td>${getFormat(stream.mime_type)}</td>
                    <td><button class="download-btn" data-itag="${stream.itag}" data-type="video">Download</button></td>`;
                videoBody.appendChild(tr);
            } else if (stream.type === 'audio') {
                let tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${stream.abr || '-'}</td>
                    <td>${stream.filesize ? stream.filesize.toFixed(2) : '-'}</td>
                    <td>${getFormat(stream.mime_type)}</td>
                    <td><button class="download-btn" data-itag="${stream.itag}" data-type="audio">Download</button></td>`;
                audioBody.appendChild(tr);
            }
        });
        document.querySelectorAll('.download-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                startDownload(btn.dataset.itag, btn.dataset.type);
            });
        });
    }

    // Progress Dialog
    const progressDialog = document.getElementById('progressDialog');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const cancelBtn = document.getElementById('cancelBtn');
    const closeBtn = document.getElementById('closeBtn');

    let progressInterval = null;
    let activeDownloadId = null;

    function startDownload(itag, type) {
        progressBar.style.width = '0%';
        progressText.textContent = 'Initializing...';
        progressDialog.classList.remove('hidden');
        cancelBtn.disabled = false;
        closeBtn.disabled = true;
        fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                url: currentVideo.url,
                itag,
                type
            })
        }).then(res => res.json())
        .then(data => {
            if (!data.success) {
                progressText.textContent = 'Failed to start download!';
                cancelBtn.disabled = true;
                closeBtn.disabled = false;
                return;
            }
            activeDownloadId = data.download_id;
            watchProgress();
        });
    }

    function watchProgress() {
        progressInterval = setInterval(() => {
            fetch(`/progress/${activeDownloadId}`).then(r => r.json()).then(data => {
                if (data.status === 'error') {
                    progressBar.style.width = '0%';
                    progressText.textContent = 'Error: ' + data.error;
                    cancelBtn.disabled = true;
                    closeBtn.disabled = false;
                    clearInterval(progressInterval);
                    return;
                }
                if (data.status === 'cancelled') {
                    progressBar.style.width = '0%';
                    progressText.textContent = 'Download cancelled.';
                    cancelBtn.disabled = true;
                    closeBtn.disabled = false;
                    clearInterval(progressInterval);
                    return;
                }
                progressBar.style.width = `${data.percentage}%`;
                progressText.textContent = `Progress: ${data.percentage.toFixed(2)}% | Speed: ${formatBytes(data.speed)}/s | Time Left: ${formatTime(data.time_remaining)}`;
                if (data.status === 'complete') {
                    progressBar.style.width = `100%`;
                    progressText.innerHTML = `Done! <a href="/download_file/${data.filename}" download>Click to download</a>`;
                    cancelBtn.disabled = true;
                    closeBtn.disabled = false;
                    clearInterval(progressInterval);
                }
            });
        }, 800);
    }

    cancelBtn.addEventListener('click', () => {
        if (!activeDownloadId) return;
        fetch(`/cancel/${activeDownloadId}`, {method: 'POST'})
        .then(() => {
            cancelBtn.disabled = true;
            closeBtn.disabled = false;
        });
    });

    closeBtn.addEventListener('click', () => {
        progressDialog.classList.add('hidden');
        clearInterval(progressInterval);
        activeDownloadId = null;
    });

    function formatBytes(bytes) {
        if (!bytes || bytes < 1) return '0 B';
        let sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        let i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
    }

    function formatTime(seconds) {
        if (!seconds || seconds < 1) return '0s';
        let m = Math.floor(seconds / 60);
        let s = Math.floor(seconds % 60);
        return m ? `${m}m ${s}s` : `${s}s`;
    }
});


function triggerDownloadAndDelete(downloadUrl, fileName) {
    // 1. Trigger the download
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // 2. Wait a bit (let browser start the download), then delete file
    setTimeout(() => {
        fetch(`/delete_file/${encodeURIComponent(fileName)}`, { method: 'POST' })
          .then(r => r.json())
          .then(data => {
              if (!data.success) {
                  console.error('Failed to delete file:', data.error);
              }
          });
    }, 1500); // 1.5s delay to ensure download starts (adjust if needed)
}

// Example usage in your "download complete" logic
// progressText.innerHTML = `Done! <a href="..." id="finalDownloadLink">Click to download</a>`;
document.addEventListener('click', function(e) {
    if(e.target && e.target.id === 'finalDownloadLink') {
        e.preventDefault();
        const url = e.target.href;
        const fname = url.split('/').pop();
        triggerDownloadAndDelete(url, fname);
    }
});