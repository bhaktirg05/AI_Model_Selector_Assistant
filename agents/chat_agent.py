# Enhanced chat agent with clean, user-friendly output

import os
import json
import docx
import csv
import re
import pandas as pd
import pytesseract
import speech_recognition as sr
from PIL import Image
from agents.logger import get_logger  # type: ignore
from pymongo import MongoClient
from dotenv import load_dotenv
import random

logger = get_logger("chat_agent", "logs/chat_agent.log")

# Load environment variables to connect to MongoDB
load_dotenv()
mongo_client = MongoClient(os.getenv("MONGO_URI"))
user_db = mongo_client[os.getenv("USER_DB_NAME")]
model_col = user_db["models"]
final_model_col = user_db["final_models"]
chats_col = user_db["chats"]

class ChatAgent:
    def __init__(self, gpt_client):
        self.client = gpt_client

    def _read_text_file(self, file_path):
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading text file: {e}")
            return ""

    def _read_docx_file(self, file_path):
        try:
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            logger.error(f"Error reading DOCX: {e}")
            return ""

    def _read_csv_file(self, file_path):
        try:
            with open(file_path, 'r', encoding="utf-8") as f:
                reader = csv.reader(f)
                return "\n".join([", ".join(row) for row in reader])
        except Exception as e:
            logger.error(f"Error reading CSV: {e}")
            return ""

    def _read_xlsx_file(self, file_path):
        try:
            df = pd.read_excel(file_path)
            return df.to_string(index=False)
        except Exception as e:
            logger.error(f"Error reading XLSX: {e}")
            return ""

    def _read_json_file(self, file_path):
        try:
            with open(file_path, 'r') as f:
                return json.dumps(json.load(f), indent=2)
        except Exception as e:
            logger.error(f"Error reading JSON: {e}")
            return ""

    def _read_image_file(self, file_path):
        try:
            img = Image.open(file_path)
            return pytesseract.image_to_string(img)
        except Exception as e:
            logger.error(f"Error reading image: {e}")
            return ""

    def _read_audio_file(self, file_path):
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(file_path) as source:
                audio_data = recognizer.record(source)
                return recognizer.recognize_google(audio_data)
        except Exception as e:
            logger.error(f"Error reading audio: {e}")
            return ""

    def _handle_file_input(self, file_path):
        ext = os.path.splitext(file_path)[-1].lower()
        if ext == '.txt':
            return self._read_text_file(file_path)
        elif ext == '.docx':
            return self._read_docx_file(file_path)
        elif ext == '.csv':
            return self._read_csv_file(file_path)
        elif ext == '.xlsx':
            return self._read_xlsx_file(file_path)
        elif ext == '.json':
            return self._read_json_file(file_path)
        elif ext in ['.png', '.jpg', '.jpeg']:
            return self._read_image_file(file_path)
        elif ext in ['.mp3', '.wav']:
            return self._read_audio_file(file_path)
        else:
            logger.warning(f"Unsupported file format: {ext}")
            return ""

    def _collect_user_input(self):
        print("\nEnter your requirement (You can enter text or file path. Type 'exit' to quit):")
        lines = []
        while True:
            try:
                line = input("> ").strip()
            except Exception as e:
                logger.error(f"Input error: {e}")
                return ""

            if line.lower() in ["exit", "quit"]:
                return "EXIT_COMMAND"

            if line:
                lines.append(line)
            elif lines:
                break

        return "\n".join(lines).strip()

    def _get_chat_history(self, username, limit=10):
        """Fetch recent chat history for context"""
        try:
            chats = list(chats_col.find({"email": username}).sort("_id", -1).limit(limit))
            history = []
            for chat in reversed(chats):  # Reverse to get chronological order
                history.append(f"User: {chat['message']}")
                if 'response' in chat:
                    history.append(f"Agent: {chat['response']}")
            return "\n".join(history)
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return ""

    def _classify_with_context(self, user_input, username, current_model=None):
        """Classify user input using chat history for better context"""
        try:
            # Get recent chat history
            chat_history = self._get_chat_history(username)
            
            # Enhanced classification prompt with context
            classification_prompt = f"""
You are classifying user messages in an AI model recommendation chatbot. 

CHAT HISTORY:
{chat_history}

CURRENT MODEL: {current_model if current_model else "None"}

USER'S LATEST MESSAGE: {user_input}

Classify the user's message into one of these categories:

1. **Greeting** - Simple greetings like "hi", "hello", "good morning"
2. **NewRequirement** - User wants recommendation for a NEW AI task/use-case
3. **FollowUp** - User is asking about the CURRENT recommended model (includes yes/no responses to agent questions)
4. **ModelRejection** - User explicitly rejects the current model and wants alternatives
5. **Goodbye** - Messages like "bye", "good night", "see you", "talk later"
6. **OffTopic** - Questions completely unrelated to AI models (math, weather, personal advice, etc.)

IMPORTANT RULES:
- If user says "yes", "ok", "sure", "no", "not really" after agent asked about current model → **FollowUp**
- If user asks details about current model → **FollowUp**  
- If user describes a completely new AI task → **NewRequirement**
- If user says "I don't like this model" or "suggest another" → **ModelRejection**
- Only classify as **OffTopic** if completely unrelated to AI models AND not a continuation of current conversation

Reply with ONLY one word: Greeting, NewRequirement, FollowUp, ModelRejection, Goodbye, or OffTopic
"""

            classify_response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": classification_prompt},
                    {"role": "user", "content": user_input.strip()}
                ]
            )

            classification = classify_response.choices[0].message.content.strip()
            logger.info(f"Classified '{user_input}' as: {classification}")
            return classification

        except Exception as e:
            logger.error(f"Classification error: {e}")
            return "OffTopic"  # Default fallback

    def _format_response(self, raw_response, response_type="general", model_name=None):
        """
        Clean and format response for better UI display with proper spacing and formatting
        """
        try:
            # Remove unwanted symbols and tags
            clean_response = raw_response.replace("##PROCEED##", "").replace("##HOLD##", "")
            clean_response = clean_response.replace("**", "").replace("##", "")
            
            # Remove extra whitespace and normalize spacing
            clean_response = re.sub(r'[ \t]+', ' ', clean_response).strip()
            
            # FIRST: Remove any existing emoji highlighting around model names
            if model_name:
                # Remove the ugly emoji format if it exists
                clean_response = clean_response.replace(f"🎯 {model_name} 🎯", model_name)
                # Replace model name with special markers that your React frontend can detect and style
                #clean_response = clean_response.replace(model_name, f"**MODEL_NAME_START**{model_name}**MODEL_NAME_END**")
            
            # Fix bullet point formatting to create proper hierarchy
            # Pattern: "• MainPoint: • SubPoint • SubPoint • NextMainPoint:"
            
            # Step 1: Identify and format main points (those followed by colon)
            clean_response = re.sub(r'•\s*([A-Z][^:•]+?):\s*•', r'\n\n• \1:\n  ◦ ', clean_response)
            
            # Step 2: Convert remaining bullets after sub-points to proper sub-bullets
            clean_response = re.sub(r'•\s*([A-Z][^•\n]+?)(?=\s*•|\s*$)', r'\n  ◦ \1', clean_response)
            
            # Step 3: Handle numbered lists properly
            clean_response = re.sub(r'(\d+\.)\s*([A-Z][^:]+?):\s*', r'\n\n\1 \2:\n', clean_response)
            
            # Step 4: Clean up any double bullet issues
            clean_response = re.sub(r'•\s*•', '•', clean_response)
            
            # Add appropriate emojis based on response type (but not for model names)
            if response_type == "greeting":
                emojis = ["👋", "😊", "🤖", "✨"]
                clean_response = f"{random.choice(emojis)} {clean_response}"
            elif response_type == "recommendation":
                clean_response = f"💡 {clean_response}"
            elif response_type == "follow_up":
                clean_response = f"📝 {clean_response}"
            elif response_type == "goodbye":
                emojis = ["👋", "😊", "🎯", "✨"]
                clean_response = f"{clean_response} {random.choice(emojis)}"
            
            # Clean up excessive newlines and trailing symbols
            clean_response = re.sub(r'\n\n\n+', '\n\n', clean_response)
            clean_response = re.sub(r'\s*--\s*$', '', clean_response)
            clean_response = re.sub(r'\s+$', '', clean_response)  # Remove trailing spaces
            
            return clean_response
            
        except Exception as e:
            logger.error(f"Error formatting response: {e}")
            return raw_response

    def _generate_smart_response(self, user_input, context_type, current_model=None, chat_history=""):
        """
        Generate contextually appropriate responses with proper formatting
        """
        try:
            if context_type == "greeting":
                system_prompt = """
                You are a friendly AI model advisor. Generate a warm, welcoming greeting that:
                - Is brief and conversational (1-2 sentences max)
                - Asks about their AI needs
                - Uses simple, friendly language
                - Sounds natural and engaging
                
                Do NOT use any markdown formatting, ** symbols, or ## symbols.
                Keep it clean and simple.
                """
                
            elif context_type == "follow_up":
                system_prompt = f"""
                You are helping a user with the AI model: {current_model}
                
                RECENT CHAT HISTORY:
                {chat_history}
                
                Generate a helpful response that:
                - Answers their question about {current_model}
                - Uses clear, simple language
                - Provides practical information
                - Adapts response style based on question complexity
                
                RESPONSE FORMATTING RULES:
                1. For SHORT/SIMPLE questions: Give a brief paragraph answer (2-3 sentences)
                2. For COMPLEX questions: Structure with intro paragraph + key points
                3. For DETAILED explanations: Use mix of paragraphs and organized points
                
                FORMATTING GUIDELINES:
                - Use clear hierarchy: Main points with sub-explanations
                - For main features/points: use bullet points (•)
                - For sub-explanations: use different style or indentation
                - For steps/processes: use numbers (1. 2. 3.)
                - For simple lists: use dashes (-)
                - Always mention the model name: {current_model}
                - Do NOT use ** or ## symbols
                - Use moderate spacing between points
                - Make key points stand out from explanations
                
                EXAMPLES:
                Simple question: "Does it work with images?"
                Answer: "Yes, {current_model} can process and analyze images effectively. It handles various formats including PNG, JPEG, and supports both image recognition and text extraction from images."
                
                Complex question: "What are its key features?"
                Answer: "{current_model} offers several powerful features:
                
                • Advanced Processing: Handles large documents and complex data efficiently
                • Multi-Format Support: Works with text, images, PDFs, and more
                • High Accuracy: Delivers reliable results with 95%+ accuracy rates
                • Easy Integration: Simple APIs and SDKs for quick implementation
                
                These features make {current_model} ideal for enterprise applications!"
                
                Make it conversational, helpful, and visually appealing.
                """
                
            elif context_type == "off_topic":
                system_prompt = """
                The user asked something unrelated to AI models. 
                Generate a polite redirect that:
                - Is friendly but firm
                - Redirects to AI model topics
                - Is brief (1 sentence)
                - Sounds natural
                
                Do NOT use any markdown formatting or special symbols.
                """
                
            elif context_type == "goodbye":
                system_prompt = """
                Generate a friendly goodbye message that:
                - Is warm and positive
                - Invites them to return
                - Is brief (1-2 sentences)
                - Sounds natural
                
                Do NOT use any markdown formatting or special symbols.
                """
                
            else:  # general
                system_prompt = """
                You are a helpful AI model advisor. Generate a response that:
                - Matches the complexity of the user's question
                - Uses clear, simple language
                - Is well-structured for complex topics
                - Is brief for simple questions
                - Uses varied formatting (paragraphs, bullets, numbers)
                
                FORMATTING RULES:
                - Do NOT use ** for bold text
                - Do NOT use ## symbols  
                - Use different bullet styles: • for features, 1. for steps, - for simple lists
                - Vary your formatting approach
                - Use proper spacing between elements
                
                Make it helpful, conversational, and visually appealing.
                """

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input.strip()}
                ],
                temperature=0.7,
                max_tokens=500
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating smart response: {e}")
            return "I'm having trouble processing that right now. Please try again."

    def run_chat_loop(self):
        """
        Console-based chat loop - uses main processing function
        """
        collected_input = ""

        while not collected_input:
            raw_input = self._collect_user_input()

            if raw_input == "EXIT_COMMAND":
                return "EXIT_COMMAND"

            for segment in raw_input.splitlines():
                segment = segment.strip()
                if os.path.exists(segment):
                    collected_input += "\n" + self._handle_file_input(segment)
                else:
                    collected_input += "\n" + segment

            if not collected_input.strip():
                print("No valid input detected. Please try again.")

        # Use the main web processing function
        result = self.process_web_input(collected_input)
        
        if result["proceed"]:
            return result["message"]
        else:
            print(result["message"])
            return None

    def process_web_input(self, user_input, session_data=None, username=None):
        """
        Main processing function - handles all input types and generates responses
        """
        try:
            if not user_input or not user_input.strip():
                return {
                    "proceed": False,
                    "message": "Please provide your requirement to get started! 🤖"
                }

            if session_data is None:
                logger.info("Session data was None – initializing new session.")
                session_data = {
                    "shortlisted_models": [],
                    "current_model": None,
                    "rejected_models": [],
                    "original_requirement": "",
                    "is_new_requirement": 1
                }

            # Get current model from database
            current_model = None
            if username:
                final_entry = final_model_col.find_one({"email": username})
                if final_entry:
                    current_model = final_entry.get("final_model")
                    session_data["current_model"] = current_model
                    session_data["original_requirement"] = final_entry.get("analyzed_input", "")
                    logger.info(f"Loaded final model from DB: {current_model}")

            # Use enhanced classification with context
            input_type = self._classify_with_context(user_input, username, current_model)
            chat_history = self._get_chat_history(username, limit=5)

            if input_type == "Greeting":
                greeting_message = self._generate_smart_response(user_input, "greeting")
                formatted_message = self._format_response(greeting_message, "greeting")
                return {
                    "proceed": False,
                    "message": formatted_message
                }

            if input_type == "Goodbye":
                goodbye_message = self._generate_smart_response(user_input, "goodbye")
                formatted_message = self._format_response(goodbye_message, "goodbye")
                return {
                    "proceed": False,
                    "message": formatted_message
                }

            if input_type == "OffTopic":
                off_topic_message = self._generate_smart_response(user_input, "off_topic")
                formatted_message = self._format_response(off_topic_message, "general")
                return {
                    "proceed": False,
                    "message": formatted_message
                }

            if input_type == "NewRequirement":
                session_data["original_requirement"] = user_input
                session_data["is_new_requirement"] = 1
                return {
                    "proceed": True,
                    "action": "NewRequirement",
                    "is_new_requirement": 1,
                    "message": "💡 Perfect! Let me analyze your requirement and find the best AI models for you."
                }

            if input_type == "FollowUp":
                if current_model:
                    # Generate smart follow-up response
                    follow_up_message = self._generate_smart_response(
                        user_input, "follow_up", current_model, chat_history
                    )
                    
                    # Clean and format the response with model name highlighting
                    formatted_message = self._format_response(follow_up_message, "follow_up", current_model)

                    return {
                        "proceed": False,
                        "message": formatted_message
                    }
                else:
                    return {
                        "proceed": False,
                        "message": "🤖 I haven't recommended any model yet. Please tell me what AI task you need help with!"
                    }

            if input_type == "ModelRejection":
                if current_model:
                    rejected = session_data.get("rejected_models", [])
                    rejected.append(current_model)
                    session_data["rejected_models"] = rejected

                shortlisted = session_data.get("shortlisted_models", [])
                rejected = session_data.get("rejected_models", [])
                remaining = [m for m in shortlisted if m not in rejected]

                if not remaining:
                    return {
                        "proceed": True,
                        "action": "ModelRejection",
                        "rejected_models": rejected,
                        "requirement": session_data.get("original_requirement", ""),
                        "is_new_requirement": 0,
                        "message": "🔄 No problem! Let me search for more suitable alternatives that better match your needs."
                    }

                next_model = remaining[0]
                doc = model_col.find_one({"key": next_model})
                full_name = doc["name"] if doc else next_model
                session_data["current_model"] = full_name
                session_data["is_new_requirement"] = 0

                return {
                    "proceed": True,
                    "action": "ModelRejection",
                    "rejected_models": rejected,
                    "requirement": session_data.get("original_requirement", ""),
                    "is_new_requirement": 0,
                    "message": f"🎯 I understand! Let me recommend {full_name} as a better alternative for your needs."
                }
            
            return {
                "proceed": False,
                "message": "🤔 I'm not sure how to help with that. Could you please tell me more about your AI model needs?"
            }

        except Exception as e:
            logger.error(f"Web GPT error: {repr(e)}")
            return {
                "proceed": False,
                "message": "⚠️ Something went wrong while processing your request. Please try again in a moment."
            }