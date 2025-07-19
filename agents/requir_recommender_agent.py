import os
import pymongo
from dotenv import load_dotenv
from agents.logger import get_logger # type: ignore

# Load environment variables from .env file
load_dotenv()

logger = get_logger("recommender_agent", "logs/recommender_agent.log")
final_model_col = pymongo.MongoClient(os.getenv("MONGO_URI"))[os.getenv("USER_DB_NAME")]["final_models"]


class RecommenderAgent:
    def __init__(self, gpt_client):
        self.client = gpt_client
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_name = os.getenv("RECOMMENDER_DB_NAME")
        self.collection_name = os.getenv("RECOMMENDER_COLLECTION_NAME")

        if not all([self.mongo_uri, self.db_name, self.collection_name]):
            raise ValueError("❌ MongoDB environment variables not set correctly in .env file.")

    def _fetch_model_dataset(self):
        try:
            client = pymongo.MongoClient(self.mongo_uri)
            db = client[self.db_name]
            collection = db[self.collection_name]
            data = list(collection.find({}, {"_id": 0}))  # Exclude _id field
            logger.info(f"✅ Fetched {len(data)} models from MongoDB collection `{self.collection_name}`.")
            return data
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            print(f"❌ MongoDB connection failed: {e}")
            return []

    def recommend_models(self, analyzed_user_input: str, username: str, is_new_requirement: int = 1):

        dataset = self._fetch_model_dataset()
        if not dataset:
            logger.warning("⚠️ No dataset available for recommendation.")
            return []
        
        excluded_model = None
        if is_new_requirement == 0:
            final_entry = final_model_col.find_one({"email": username})
            if final_entry:
                excluded_model_raw = final_entry.get("final_model")
                if excluded_model_raw:
                    excluded_model = excluded_model_raw.strip().lower()

                    original_len = len(dataset)
                    dataset = [
                        m for m in dataset
                        if m.get("model_name", "").strip().lower() != excluded_model
                    ]
                    removed_count = original_len - len(dataset)
                    logger.info(f"🚫 Excluded model '{excluded_model_raw}'. {removed_count} model(s) removed.")
                    
                 

        # Convert models into formatted bullet list
        formatted_dataset = ""
        for model in dataset:
            formatted_dataset += (
                f"- {model.get('model_name', 'Unknown')} | "
                f"Accuracy: {model.get('accuracy', 'N/A')} | "
                f"Speed: {model.get('speed', 'N/A')} | "
                f"Cloud: {model.get('cloud', 'N/A')} | "
                f"Type: {model.get('type', 'N/A')}\n"
            )

        prompt = f"""
        You are an AI expert. From the following AI model shortlist, choose the top 4–5 models suitable for the user's requirement below.

        User's Requirement:
        {analyzed_user_input}

        Available AI Models:
        {formatted_dataset}

        Instructions:
        - Only use the above list for selection.
        - If the requirement involves multiple tasks, prefer multi-capability models.
        - For each selected model, reply with:
        - Model Name
        - A short reason (max 1 line)

        Reply only with a bullet list in this format:
        - <Model Name>: <short reason>
        """


        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant for AI model recommendation."},
                {"role": "user", "content": prompt}
            ]
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            result = response.choices[0].message.content
            print("🧠 GPT Response:\n", result)
            logger.info("✅ Recommended models:\n" + result)
            return result
        except Exception as e:
            logger.error(f"❌ GPT recommendation error: {e}")
            print(f"❌ GPT recommendation error: {e}")
            return "Model recommendation failed."
