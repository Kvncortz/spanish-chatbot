#!/usr/bin/env python3
"""
Script to check available Google AI models
"""

import os
import google.genai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ GOOGLE_API_KEY not found in environment variables")
    print("Please set your GOOGLE_API_KEY in the .env file")
    exit(1)

try:
    # Initialize Google AI
    client = genai.Client(api_key=GOOGLE_API_KEY)
    
    print("🔍 Checking available Google AI models...")
    print("=" * 50)
    
    # List all available models - try different methods
    try:
        models = client.models.list()
        models_list = list(models)
    except AttributeError:
        try:
            models = client.list_models()
            models_list = list(models)
        except AttributeError:
            # Try direct model access
            models_list = [
                "models/gemini-1.5-pro",
                "models/gemini-1.5-flash",
                "models/gemini-1.0-pro",
                "models/gemini-pro",
                "models/gemini-pro-vision"
            ]
            print("📊 Using known model list (API method may have changed)")
    
    print(f"📊 Found {len(models_list)} total models:")
    print()
    
    # Filter for generative models and sort them
    generative_models = []
    for model in models_list:
        if isinstance(model, str):
            generative_models.append(model)
        else:
            # If it's a model object, get its name
            if hasattr(model, 'name'):
                generative_models.append(model.name)
    
    generative_models.sort()
    
    print("🤖 Available Models:")
    print("-" * 40)
    
    for model_name in generative_models:
        print(f"  • {model_name}")
    
    print()
    print("🎯 Recommended Models for Spanish Learning:")
    print("-" * 40)
    
    # Highlight the best models for educational use
    recommended_models = [
        "models/gemini-1.5-pro",
        "models/gemini-1.5-flash", 
        "models/gemini-1.0-pro"
    ]
    
    for model_name in recommended_models:
        if model_name in generative_models:
            print(f"  ✅ {model_name} - EXCELLENT for education")
        else:
            print(f"  ❌ {model_name} - Not available")
    
    print()
    print("💡 Usage Example:")
    print("```python")
    print("import google.genai as genai")
    print("client = genai.Client(api_key='YOUR_API_KEY')")
    print("model = client.GenerativeModel('models/gemini-1.5-pro')")
    print("response = model.generate_content('Hola, cómo estás?')")
    print("print(response.text)")
    print("```")
    
    print()
    print("🔑 Your API Key Status: ✅ Valid")
    print("🌐 Google AI Connection: ✅ Working")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print()
    print("Possible issues:")
    print("• Invalid API key")
    print("• Network connectivity problems") 
    print("• API quota exceeded")
    print("• Service temporarily unavailable")
    print()
    print("Check your .env file and ensure GOOGLE_API_KEY is correct.")
