import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
print(f"Loaded API Key: {api_key[:10]}..." if api_key else "No API Key loaded")

if api_key:
    genai.configure(api_key=api_key)
    try:
        print("Available Models:")
        models = genai.list_models()
        model_names = []
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                model_names.append(m.name)
        print("\n".join(model_names) if model_names else "No models support generateContent")
    except Exception as e:
        print(f"Error fetching models: {e}")
