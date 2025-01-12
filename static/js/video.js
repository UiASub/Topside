async function updateVideoStream() {
    try {
        const response = await fetch('/api/video_stream');
        const data = await response.json();
        const videoElement = document.getElementById('video-stream');
        if (data.url) {
            videoElement.src = data.url;
        }
    } catch (error) {
        console.error('Error updating video stream:', error);
    }
}

// Update the video stream every second
setInterval(updateVideoStream, 1000);
