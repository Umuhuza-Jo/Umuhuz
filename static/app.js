let lastDownloadId = null;
let pollInterval = null;

function checkVideo() {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) return alert('Please enter a video URL!');
    fetch('/check_video', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) return alert(data.error);
        renderVideoInfo(data);
    });
}

function renderVideoInfo(info) {
    let html = `
        <img src="${info.thumbnail_url}" style="max-width:200px;"><br>
        <b>${info.title}</b><br>
        <div class="tabs">
            <div class="tab active" id="videoTab" onclick="showTab('video', this)">Video</div>
            <div class="tab" id="audioTab" onclick="showTab('audio', this)">Audio</div>
        </div>
        <div id="videoTable"></div>
        <div id="audioTable" style="display:none"></div>
    `;
    document.getElementById('videoInfo').innerHTML = html;
    // Fill tables
    let vrows = info.streams.filter(s=>s.type==='video').map(s=>`
        <tr>
            <td>${s.resolution||'-'}</td>
            <td>${s.mime_type}</td>
            <td>${s.filesize? s.filesize.toFixed(2)+' MB':'-'}</td>
            <td><button onclick="startDownload('${info.video_id}','${s.itag}','video')">Download</button></td>
        </tr>`).join('');
    let arows = info.streams.filter(s=>s.type==='audio').map(s=>`
        <tr>
            <td>${s.abr||'-'}</td>
            <td>${s.mime_type}</td>
            <td>${s.filesize? s.filesize.toFixed(2)+' MB':'-'}</td>
            <td><button onclick="startDownload('${info.video_id}','${s.itag}','audio')">Download</button></td>
        </tr>`).join('');
    document.getElementById('videoTable').innerHTML = `<table>
        <tr><th>Resolution</th><th>Type</th><th>Size</th><th>Action</th></tr>${vrows}</table>`;
    document.getElementById('audioTable').innerHTML = `<table>
        <tr><th>Bitrate</th><th>Type</th><th>Size</th><th>Action</th></tr>${arows}</table>`;
}

function showTab(tab, el) {
    document.getElementById('videoTab').classList.remove('active');
    document.getElementById('audioTab').classList.remove('active');
    el.classList.add('active');
    document.getElementById('videoTable').style.display = (tab==='video')?'block':'none';
    document.getElementById('audioTable').style.display = (tab==='audio')?'block':'none';
}

function startDownload(video_id, itag, type) {
    // you'll need to get the original url from the input box
    const url = document.getElementById('urlInput').value.trim();
    fetch('/download', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url,itag,type})
    })
    .then(res=>res.json())
    .then(data=>{
        if (data.error) return alert(data.error);
        lastDownloadId = data.download_id;
        openModal();
        pollProgress();
    });
}

function pollProgress() {
    if (!lastDownloadId) return;
    pollInterval = setInterval(()=>{
        fetch(`/progress/${lastDownloadId}`)
        .then(res=>res.json())
        .then(data=>{
            if (data.status==='complete') {
                updateProgressBar(100, "Download complete! <a href='/download_file/"+data.filename+"'>Click to download file</a>");
                clearInterval(pollInterval);
            } else if (data.status==='downloading' || data.status==='processing_audio' || data.status==='merging') {
                let status = `Status: ${data.status}<br>
                    Downloaded: ${formatBytes(data.bytes_downloaded)} / ${formatBytes(data.total_size)}<br>
                    Speed: ${formatBytes(data.speed)}/s<br>
                    Time left: ${data.time_remaining.toFixed(1)}s`;
                updateProgressBar(data.percentage, status);
            } else if (data.status==='cancelled') {
                updateProgressBar(0, "Download cancelled.");
                clearInterval(pollInterval);
            } else if (data.status==='error') {
                updateProgressBar(0, "Error: "+data.error);
                clearInterval(pollInterval);
            }
        });
    }, 1000);
}

function updateProgressBar(percentage, status) {
    document.getElementById('progressBar').style.width = percentage + "%";
    document.getElementById('progressStatus').innerHTML = status;
}

function cancelDownload() {
    if (!lastDownloadId) return;
    fetch(`/cancel/${lastDownloadId}`, {method:'POST'})
        .then(res=>res.json())
        .then(data=>{
            updateProgressBar(0, "Download cancelled.");
            clearInterval(pollInterval);
        });
}

function openModal() {
    document.getElementById('progressModal').style.display = 'block';
    updateProgressBar(0, '');
}
function closeModal() {
    document.getElementById('progressModal').style.display = 'none';
    if (pollInterval) clearInterval(pollInterval);
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B','KB','MB','GB','TB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length-1) {
        bytes /= 1024; i++;
    }
    return bytes.toFixed(2)+' '+units[i];
}