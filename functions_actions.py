#openai functions call - actions
import openai
import json, os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env.local")
openai.api_key = os.getenv("OPENAI_API_KEY")
wheather_api_key = os.getenv("OPENWEATHER_API_KEY")
search_api = os.getenv("apikey_search")

import requests


#define function weather
def get_weather_forecast(location, cnt=1, api_key = wheather_api_key):
    """Get the weather forecast or current weather in a given location"""

    if cnt>=1:

        url = "http://api.openweathermap.org/data/2.5/forecast" # 5 days 3 to 3 hours

        params = {
            "q": location,
            "cnt": cnt, #number of timestamp
            "appid": api_key,
            "units": "metric",}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for non-2xx responses
            data = response.json()
            #print(data)

            cnt = cnt-1
            
            # Extract relevant forecast information
            temperature = data["list"][cnt]["main"]["temp"]
            weather_description = data["list"][cnt]["weather"][0]["description"]
            humidity = data["list"][cnt]["main"]["humidity"]
            timestamp = data["list"][cnt]["dt_txt"]
        
            forecast_info = {
            "location": location,
            "temperature": temperature,
            "humidity": humidity,
            "forecast_description": weather_description,
            "timestamp": timestamp,
            "type" : "forecast data, all units in metric",
            }

            return json.dumps(forecast_info)
        
        except requests.exceptions.RequestException as e:
            print("Error occurred during API request:", e)
            return None
        
    else: #current weather
        
        url = "http://api.openweathermap.org/data/2.5/weather" 
        
        params = {
            "q": location,
            "appid": api_key,
            "units": "metric",}

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise an exception for non-2xx responses
            data = response.json()
                   
            # Extract relevant current weather information
            temperature = data["main"]["temp"]
            weather_description = data["weather"][0]["description"]
            humidity = data["main"]["humidity"]
            wind = data["wind"]["speed"]
        
            forecast_info = {
            "location": location,
            "temperature": temperature,
            "humidity": humidity,
            "weather_description": weather_description,
            "wind_speed": wind,
            "type" : "current weather data, all units in metric",
            }

            return json.dumps(forecast_info)
        
        except requests.exceptions.RequestException as e:
            print("Error occurred during API request:", e)
            return None


    
#def function to serpapi search engine
from serpapi import GoogleSearch
def search_serpapi(query):
    local_results = []
    answer_box = []
    params = {
        "engine": "google", #"duckduckgo"
        "q": query,
        "gl": "br",
        "api_key": search_api 
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    organic_results = results["organic_results"]

    if "local_results" in results:
        local_results = results["local_results"]

    if "answer_box" in results:
        answer_box = results["answer_box"]

    resultado_local = json.dumps(local_results, indent=4)
    resultado_box = json.dumps(answer_box, indent=4)
    
    
    snipts = [resultado['snippet'] for resultado in organic_results[:3]]
    snipts_result = ', '.join(snipts)
    final_result = resultado_box + "\n" + resultado_local + "\n" + snipts_result
    return final_result


#google custom API Search
import requests
import json

CS_API_KEY = os.getenv("CS_API_KEY")
CS_CX = os.getenv("CS_CX")

from googleapiclient.discovery import build

# Define your API key and API version
api_key = CS_API_KEY
api_version = "v1"
# Create a custom search engine service
service = build("customsearch", api_version, developerKey=api_key)
# Function to execute the search
def execute_search(query):
    try:
        results = service.cse().list(
            cx=CS_CX,
            start = 1,
            num = 3,
            #dateRestrict = 'm1'
            q=query,
            hl = 'br',
            gl = 'br',
        ).execute()
        
        # Handle the search results here (result variable) to return jason
        final_result = []
        
        if results['items']:
            for item in results['items']:
                title = item['title']
                link = item['link']
                snippet = item['snippet']
                res = [title, link, snippet]
                final_result.append(json.dumps(res, indent=4))
                #print (json.dumps(res, indent=4))

        return final_result

    except Exception as e:
        print("Error executing search:", e)

def websearch(query):
    r = search_serpapi(query)
    if r is not None:
        return r
    else:
        print("Using custom search engine")
        return execute_search(query)


