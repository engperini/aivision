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
import logging
from functools import wraps
import json

# Configurar o logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
load_dotenv(dotenv_path=".env.local")

# Configurações das APIs
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Inicializa Deepgram
deepgram = DeepgramClient(DEEPGRAM_API_KEY)

# Inicializa OpenAI
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)

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
            logger.error(f"Erro na API de TTS: {response.text}")
            return None

        # Lê o conteúdo do áudio
        audio_content = BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                audio_content.write(chunk)

        # Retorna o áudio em bytes
        return audio_content.getvalue()

    except Exception as e:
        logger.error(f"Erro ao chamar a API de TTS: {e}")
        return None

# Função para transcrever áudio usando DeepgramClient
def transcribe_audio(audio_bytes, mimetype='audio/wav', language='pt-BR'):
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
        response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options)

        # Log detalhado da resposta
        logger.info(f"Resposta da Deepgram: {response}")

        # Extrai o transcript
        transcript = response['results']['channels'][0]['alternatives'][0]['transcript']
        return transcript

    except Exception as e:
        logger.error(f"Erro na transcrição com Deepgram: {e}")
        return None

# Decorador para tratar erros
def handle_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Erro na rota {request.path}: {e}")
            return jsonify({"error": "Ocorreu um erro no servidor."}), 500
    return decorated_function

# Funções disponíveis para o ChatGPT
def websearch(query):
    # Implementação da função de busca na web
    # Exemplo simples usando Google Search API ou similar
    # Aqui, vamos apenas retornar uma resposta fictícia
    # Substitua com a lógica real de busca
    return f"Resultados da busca para '{query}'. (Implementar lógica de busca real)"

# Rota para servir a página principal
@app.route('/')
@handle_errors
def index():
    return render_template('index.html')

# Endpoint para processar áudio e vídeo
@app.route('/process', methods=['POST'])
@handle_errors
def process():
    if 'audio' not in request.files:
        logger.warning("Áudio não encontrado na requisição.")
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
            logger.info("Imagem capturada e salva.")
        cap.release()
        os.remove(video_path)

    # Transcreve o áudio usando Deepgram
    transcript = transcribe_audio(audio_bytes, mimetype='audio/wav', language='pt-BR')
    if not transcript:
        logger.error("Erro na transcrição de áudio.")
        return jsonify({"error": "Erro na transcrição de áudio"}), 500
    logger.info(f"Texto transcrito: {transcript}")

    # Verifica palavras-chave para utilizar a visão
    keywords = ["ver", "olhar", "foto", "câmera", "imagem", "cam", "ler", "visão", "cena", "picture"]
    use_image = any(keyword in transcript.lower() for keyword in keywords)

    chat_context.append({"role": "user", "content": transcript})

    # Chama a API do ChatGPT com funções
    try:
        # Define as funções que o ChatGPT pode chamar
        functions = [
            {
                "name": "websearch",
                "description": "Use útil para responder perguntas sobre eventos recentes. Não use para perguntas gerais.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Consulta para buscar na web, ex.: quem ganhou o US Open este ano?, notícias recentes sobre este assunto"
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

        response_chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat_context,
            functions=functions,
            function_call="auto"
        )
        response_message = response_chat.choices[0].message

        # Verifica se o GPT quer chamar uma função
        if response_message.function_call:
            function_name = response_message.function_call.name
            function_args = json.loads(response_message.function_call.arguments)

            # Mapeia o nome da função para a implementação real
            available_functions = {
                "websearch": websearch,
            }

            if function_name in available_functions:
                function_to_call = available_functions[function_name]
                # Chama a função com os argumentos necessários
                if function_name == "websearch":
                    function_response = function_to_call(query=function_args.get("query"))
                else:
                    function_response = None

                # Adiciona a chamada da função e sua resposta no contexto
                chat_context.append(response_message)
                chat_context.append({
                    "role": "function",
                    "name": function_name,
                    "content": function_response,
                })

                # Obtém a resposta final do ChatGPT após a função ser chamada
                second_response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=chat_context
                )
                reply = second_response.choices[0].message.content
                chat_context.append({"role": "assistant", "content": reply})
                logger.info(f"Resposta do ChatGPT após chamada de função: {reply}")
            else:
                reply = "Função não reconhecida."
                chat_context.append({"role": "assistant", "content": reply})
                logger.warning(f"Função chamada não está disponível: {function_name}")
        else:
            # Se não há chamada de função, simplesmente usa a resposta do ChatGPT
            reply = response_message.content
            chat_context.append({"role": "assistant", "content": reply})
            logger.info(f"Resposta do ChatGPT: {reply}")

    except Exception as e:
        logger.error(f"Erro ao chamar a API do ChatGPT: {e}")
        return jsonify({"error": "Erro ao gerar resposta com ChatGPT"}), 500

    # Sintetiza a resposta em áudio usando a API de TTS da OpenAI
    tts_audio = text_to_speech(reply)
    if not tts_audio:
        logger.error("Erro ao gerar áudio com a API de TTS.")
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
        logger.info("Imagem incluída na resposta.")

    # Converte o áudio para base64
    encoded_audio = base64.b64encode(tts_audio).decode('utf-8')
    response_data["audio"] = encoded_audio
    logger.info("Áudio sintetizado incluído na resposta.")

    return jsonify(response_data)

if __name__ == '__main__':
    # Certifique-se de que a pasta 'captured_images' existe
    if not os.path.exists('captured_images'):
        os.makedirs('captured_images')
    #app.run(host='0.0.0.0', port=5000, debug=True, ssl_context=('cert.pem', 'key.pem'))
    app.run(host='0.0.0.0', port=5000, debug=True)
