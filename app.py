import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import openai
import cv2
import base64
from io import BytesIO
import requests

# Carrega variáveis de ambiente
load_dotenv(dotenv_path=".env.local")

# Configurações das APIs
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Inicializa Deepgram
deepgram = DeepgramClient(DEEPGRAM_API_KEY)

# Inicializa Flask
app = Flask(__name__)
CORS(app)  # Permite requisições de outros domínios (para desenvolvimento)

# Contexto do Chat
chat_context = [
    {
        "role": "system",
        "content": (
            "Seu nome é Alloy. Você é um bot engraçado e espirituoso. Sua interface com os usuários inclui capacidades de voz e visão. "
            "Sempre que um usuário pedir para 'ver', 'usar a câmera', 'olhar para', 'analisar', 'ler' algo visualmente, ou qualquer coisa que exija percepção visual, você deve utilizar suas capacidades de visão. Sim, você pode usar a câmera quando necessário. "
            "Responda com respostas curtas e concisas. Evite usar pontuação inpronunciável ou emojis."
        )
    }
]

# Função para sintetizar texto em áudio usando a API de TTS da OpenAI
def text_to_speech(text):
    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "tts-1",
        "voice": "alloy",
        "input": text
    }

    try:
        response = requests.post(url, headers=headers, json=data, stream=True)

        if response.status_code != 200:
            print(f"Erro na API de TTS: {response.text}")
            return None

        # Lê o conteúdo do áudio
        audio_content = BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                audio_content.write(chunk)

        # Retorna o áudio em bytes
        return audio_content.getvalue()

    except Exception as e:
        print(f"Erro ao chamar a API de TTS: {e}")
        return None

# Função para transcrever áudio usando DeepgramClient
def transcribe_audio(audio_bytes, mimetype='audio/mp3', language='pt-BR'):
    try:
        # Configurações para a transcrição
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
            language=language
        )

        # Cria o payload
        payload: FileSource = {
            "buffer": audio_bytes,
            "mimetype": mimetype
        }

        # Chama o método de transcrição
        response = deepgram.listen.rest.v("1").transcribe_file(payload, options)

        # Extrai o transcript
        transcript = response['results']['channels'][0]['alternatives'][0]['transcript']
        return transcript

    except Exception as e:
        print(f"Erro na transcrição com Deepgram: {e}")
        return None

# Rota para servir a página principal
@app.route('/')
def index():
    return render_template('index.html')

# Endpoint para processar áudio e vídeo
@app.route('/process', methods=['POST'])
def process():
    if 'audio' not in request.files:
        return jsonify({"error": "Áudio não encontrado"}), 400
    audio_file = request.files['audio']
    audio_bytes = audio_file.read()

    video_frame = None
    if 'video' in request.files:
        video_file = request.files['video']
        # Salva o vídeo temporariamente
        video_path = 'temp_video.mp4'
        video_file.save(video_path)
        # Captura o primeiro frame
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        if ret:
            video_frame = frame
            # Salva a imagem capturada em uma pasta específica
            captured_images_path = 'captured_images/captured_image.jpg'
            cv2.imwrite(captured_images_path, frame)
            print("Imagem capturada e salva.")
        cap.release()
        os.remove(video_path)

    # Transcreve o áudio usando Deepgram
    transcript = transcribe_audio(audio_bytes, mimetype='audio/mp3', language='pt-BR')
    if not transcript:
        return jsonify({"error": "Erro na transcrição de áudio"}), 500
    print(f"Texto transcrito: {transcript}")

    # Verifica palavras-chave para utilizar a visão
    keywords = ["ver", "olhar", "foto", "câmera", "imagem", "cam", "ler", "visão", "cena", "picture"]
    use_image = any(keyword in transcript.lower() for keyword in keywords)

    chat_context.append({"role": "user", "content": transcript})

    # Chama a API do ChatGPT
    try:
        response_chat = openai.completions.create(
            model="gpt-4",
            messages=chat_context
        )
        reply = response_chat.choices[0].message.content
        chat_context.append({"role": "assistant", "content": reply})
        print(f"Resposta do ChatGPT: {reply}")
    except Exception as e:
        print(f"Erro ao chamar a API do ChatGPT: {e}")
        return jsonify({"error": "Erro ao gerar resposta com ChatGPT"}), 500

    # Sintetiza a resposta em áudio usando a API de TTS da OpenAI
    tts_audio = text_to_speech(reply)
    if not tts_audio:
        return jsonify({"error": "Erro ao gerar áudio"}), 500

    # Prepara a resposta
    response_data = {
        "text": reply
    }

    if use_image and video_frame is not None:
        # Converte a imagem para base64
        with open('captured_images/captured_image.jpg', 'rb') as img_file:
            encoded_image = base64.b64encode(img_file.read()).decode('utf-8')
        response_data["image"] = encoded_image
        # Remove a imagem após o envio
        os.remove('captured_images/captured_image.jpg')
        print("Imagem incluída na resposta.")

    # Converte o áudio para base64
    encoded_audio = base64.b64encode(tts_audio).decode('utf-8')
    response_data["audio"] = encoded_audio
    print("Áudio sintetizado incluído na resposta.")

    return jsonify(response_data)

if __name__ == '__main__':
    # Certifique-se de que a pasta 'captured_images' existe
    if not os.path.exists('captured_images'):
        os.makedirs('captured_images')
    app.run(host='0.0.0.0', port=5000)
