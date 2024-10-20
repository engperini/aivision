const talkButton = document.getElementById('talkButton');
const localVideo = document.getElementById('localVideo');
const status = document.getElementById('status');
const responseAudio = document.getElementById('responseAudio');
const responseImage = document.getElementById('responseImage');

let mediaStream = null;
let audioChunks = [];
let recorder = null;
let isRecording = false;

talkButton.onclick = async () => {
    if (!isRecording) {
        // Iniciar Gravação
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
            localVideo.srcObject = mediaStream;

            recorder = new MediaRecorder(mediaStream);
            recorder.ondataavailable = event => {
                audioChunks.push(event.data);
            };
            recorder.onstop = () => {
                console.log('Gravação de áudio finalizada.');
                sendData();
            };
            recorder.start();

            isRecording = true;
            talkButton.textContent = 'Parar';
            status.textContent = 'Gravando...';
        } catch (err) {
            console.error('Erro ao acessar dispositivos de mídia:', err);
            status.textContent = 'Erro ao acessar dispositivos de mídia.';
        }
    } else {
        // Parar Gravação
        recorder.stop();
        isRecording = false;
        talkButton.textContent = 'Falar';
        status.textContent = 'Processando sua fala...';
    }
};

const sendData = async () => {
    // Cria um blob do áudio gravado
    const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
    audioChunks = []; // Reseta os chunks

    // Captura um frame do vídeo
    let videoBlob = null;
    if (mediaStream.getVideoTracks().length > 0) {
        const videoTrack = mediaStream.getVideoTracks()[0];
        const imageCapture = new ImageCapture(videoTrack);
        try {
            const bitmap = await imageCapture.grabFrame();
            // Converte o frame para blob
            const canvas = document.createElement('canvas');
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(bitmap, 0, 0);
            videoBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
        } catch (err) {
            console.error('Erro ao capturar frame de vídeo:', err);
        }
    }

    // Prepara os dados para envio
    const formData = new FormData();
    formData.append('audio', audioBlob, 'audio.wav');
    if (videoBlob) {
        formData.append('video', videoBlob, 'video.jpg');
    }

    try {
        const response = await fetch('/process', {  // Rota relativa
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Erro na requisição: ${response.statusText}`);
        }

        const data = await response.json();
        status.textContent = 'Resposta recebida do servidor.';
        
        // Display bot's response in chat
        displayBotMessage(data.response); 

        // Reproduz o áudio de resposta
        if (data.audio) {
            const audioBytes = atob(data.audio);
            const audioBuffer = new Uint8Array(audioBytes.length);
            for (let i = 0; i < audioBytes.length; i++) {
                audioBuffer[i] = audioBytes.charCodeAt(i);
            }
            const blob = new Blob([audioBuffer], { type: 'audio/mp3' });
            const url = URL.createObjectURL(blob);
            responseAudio.src = url;
            responseAudio.play();
        }

        // Exibe a imagem de resposta, se houver
        if (data.image) {
            responseImage.src = `data:image/jpeg;base64,${data.image}`;
            responseImage.style.display = 'block';
        } else {
            responseImage.style.display = 'none';
        }

    } catch (err) {
        console.error('Erro ao enviar dados:', err);
        status.textContent = 'Erro ao enviar dados para o servidor.';
    }
};

function displayUserMessage(message) {
    const template = document.getElementById('user-message-template');
    const messageElement = template.content.cloneNode(true);
    messageElement.querySelector('.message-text').textContent = message;
    document.getElementById('chat-container').appendChild(messageElement);
}

function displayBotMessage(message) {
    const template = document.getElementById('bot-message-template');
    const messageElement = template.content.cloneNode(true);
    messageElement.querySelector('.message-text').textContent = message;
    document.getElementById('chat-container').appendChild(messageElement);
}
