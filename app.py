import os
import eventlet
eventlet.monkey_patch()
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
from deepgram import DeepgramClient, PrerecordedOptions, FileSource
import base64
from io import BytesIO

import requests
import logging
from functools import wraps
import json
from functions_actions import websearch
from openai import OpenAI

from flask_socketio import SocketIO, emit

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
client = OpenAI(api_key=OPENAI_API_KEY)

# Inicializa Flask
app = Flask(__name__)
CORS(app)  # Permite requisições de outros domínios (para desenvolvimento)

# Inicializa SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Contexto do Chat
chat_context = [
    {
        "role": "system",
        "content": (
            "Seu nome é Alloy. Você é um bot engraçado e espirituoso, que consegue ver imagens, consegue identificar objetos em imagens, ver câmera, ler textos em imagens e trabalhar com todo tipo de imagem. Sua interface com os usuários inclui capacidades de voz e visão. "
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
            logger.error(f"Erro no evento: {e}")
            emit("error", {"error": "Ocorreu um erro no servidor."})
    return decorated_function

# Rota para servir a página principal
@app.route('/')
@handle_errors
def index():
    return render_template('index.html')

# Evento para conexão de clientes
@socketio.on('connect')
def handle_connect():
    logger.info(f"Cliente conectado: {request.sid}")

# Evento para desconexão de clientes
@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"Cliente desconectado: {request.sid}")

# Evento para processar dados enviados pelo cliente
@socketio.on('process_data')
@handle_errors
def handle_process_data(data):
    global chat_context
    use_image = False

    if 'video' in data:
        video_data = data['video']
        try:
            # Decodifica a imagem base64
            header, encoded = video_data.split(',', 1)
            video_bytes = base64.b64decode(encoded)
            with open('captured_images/captured_image.jpg', 'wb') as f:
                f.write(video_bytes)
            logger.info("Imagem salva direto do navegador.")
            use_image = True
        except Exception as e:
            logger.error(f"Erro ao salvar a imagem: {e}")
            emit("error", {"error": "Erro ao processar a imagem."})
            return

    if 'audio' in data:
        audio_data = data['audio']
        try:
            # Decodifica o áudio base64
            header, encoded = audio_data.split(',', 1)
            audio_bytes = base64.b64decode(encoded)
            # Transcreve o áudio usando Deepgram
            transcript = transcribe_audio(audio_bytes, mimetype='audio/wav', language='pt-BR')
            if not transcript:
                logger.error("Erro na transcrição de áudio.")
                emit("error", {"error": "Erro na transcrição de áudio"})
                return
            logger.info(f"Texto transcrito: {transcript}")

            chat_context.append({"role": "user", "content": transcript})

            # Verifica palavras-chave para utilizar a visão
            keywords = ["ver", "olhar", "foto", "câmera", "imagem", "cam", "ler", "visão", "cena", "picture"]
            use_image = any(keyword in transcript.lower() for keyword in keywords)

        except Exception as e:
            logger.error(f"Erro ao processar áudio: {e}")
            emit("error", {"error": "Erro ao processar áudio."})
            return

    elif 'text' in data:
        text = data['text']
        logger.info(f"Texto recebido: {text}")
        chat_context.append({"role": "user", "content": text})

        # Verifica palavras-chave para utilizar a visão
        keywords = ["ver", "olhar", "foto", "câmera", "imagem", "cam", "ler", "visão", "cena", "picture"]
        use_image = any(keyword in text.lower() for keyword in keywords)

    else:
        logger.warning("Requisição inválida: nem áudio, nem texto.")
        emit("error", {"error": "Requisição inválida."})
        return

    # Define as funções que o ChatGPT pode chamar
    tools = [
        {
            "type": "function",
            "function": {
                "name": "websearch",
                "description": "Use esta função para responder perguntas que requerem informações atualizadas da internet, como eventos recentes, agendas de eventos e informações sobre o dia atual ou datas futuras.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Consulta para buscar na web, ex.: quem ganhou o US Open este ano?, noticias hoje?, me atualize de determinado assunto, quais os próximos shows do artista X?"
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "use_camera",
                "description": "Use esta função quando o usuário solicitar alguma coisa visual.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Ação solicitada pelo usuário relacionada ao uso da câmera."
                        },
                    },
                    "required": ["action"],
                    "additionalProperties": False,
                },
            }
        }
    ]

    # Chama a API do ChatGPT com funções
    try:
        response_chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=chat_context,
            tools=tools,
            tool_choice="auto"
        )
        response_message = response_chat.choices[0].message

        # Verifica se o GPT quer chamar uma função
        if response_message.tool_calls:
            reply = None
            tool_call = response_message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            if function_name == "use_camera" and use_image:
                reply = None
                # Converte a imagem para base64
                with open('captured_images/captured_image.jpg', 'rb') as img_file:
                    encoded_image = base64.b64encode(img_file.read()).decode('utf-8')
                chat_context.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded_image}"
                            },
                        },
                    ],
                })
                logger.info("Imagem incluída no chat.")

            elif function_name == "websearch":
                reply = None
                function_response = websearch(query=function_args.get("query"))
                chat_context.append(response_message)
                chat_context.append({
                    "role": "function",
                    "name": function_name,
                    "content": function_response,
                })
                logger.info("Internet Search used")

            else:
                reply = "Não foi possível processar a solicitação."
                chat_context.append({"role": "assistant", "content": reply})
                logger.warning(f"Função chamada não está disponível: {function_name}")

            # Obtém a resposta final do ChatGPT após a função ser chamada
            second_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=chat_context
            )
            reply = second_response.choices[0].message.content if hasattr(second_response.choices[0].message, 'content') else 'Erro ao obter resposta do assistente.'
            chat_context.append({"role": "assistant", "content": reply})
            logger.info(f"Resposta do ChatGPT após chamada de função: {reply}")

        else:
            reply = response_message.content if hasattr(response_message, 'content') else 'Erro ao obter resposta do assistente.'
            chat_context.append({"role": "assistant", "content": reply})
            logger.info(f"Resposta do ChatGPT: {reply}")

    except Exception as e:
        logger.error(f"Erro ao chamar a API do ChatGPT: {e}")
        emit("error", {"error": "Erro ao gerar resposta com ChatGPT"})
        return

    # Sintetiza a resposta em áudio usando a API de TTS da OpenAI
    tts_audio = text_to_speech(reply) if reply else None
    if not tts_audio:
        logger.error("Erro ao gerar áudio com a API de TTS.")
        emit("error", {"error": "Erro ao gerar áudio"})
        return
    elif not reply:
        emit("error", {"error": "Nenhuma resposta gerada"})
        return

    # Prepara a resposta
    response_data = {
        "text": reply
    }

    # Converte o áudio para base64
    encoded_audio = base64.b64encode(tts_audio).decode('utf-8')
    response_data["audio"] = encoded_audio
    logger.info("Áudio sintetizado incluído na resposta.")

    # Envia a resposta de volta ao cliente via WebSocket
    emit("response", response_data)

if __name__ == '__main__':
    if not os.path.exists('captured_images'):
        os.makedirs('captured_images')
    socketio.run(app, host='192.168.0.21', port=5000, debug=True, certfile='cert.pem', keyfile='key.pem')
    