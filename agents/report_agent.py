import json
from openai import AzureOpenAI  # or from openai import OpenAI if not using Azure
from agents.logger import get_logger  # type: ignore
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import re

logger = get_logger("report_agent", "logs/report_agent.log")

# Load MongoDB credentials
load_dotenv()
mongo_client = MongoClient(os.getenv("MONGO_URI"))
user_db = mongo_client[os.getenv("USER_DB_NAME")]
model_col = user_db["models"]
final_model_col = user_db["final_models"]


class ReportAgent:
    def __init__(self, gpt_client):
        self.client = gpt_client
        logger.info("Report Agent initialized using GPT directly (no assistant)")

    def generate_report(self, username, analyzed_input, recommended_models, pricing_table):
        logger.info("Sending all inputs to GPT for final analysis...")

        prompt = (
            "You are an expert AI model selector.\n\n"
            f"1. Analyzed user requirement:\n{analyzed_input}\n\n"
            f"2. Recommended models:\n{recommended_models}\n\n"
            f"3. Pricing details of shortlisted models:\n{pricing_table}\n\n"
            "Step 2: Your task is to select the best model using logic.\n\n"
            "Output Format (strictly follow this format):\n\n"
            "Final Best Model Recommended:\n"
            "1. Model Name      : <model_name>\n"
            "2. Price           : <price with unit>\n"
            "3. Speed           : <speed - always write something, even if approximate or inferred>\n"
            "4. Accuracy        : <convert to percentage if decimal (e.g., 0.987 → 98.7 %)>\n"
            "5. Cloud           : <cloud provider>\n"
            "6. Region          : <region or deployment area>\n"
            "7. Reason for Selection : <Short one-liner reason showing why this model fits best>\n\n"
            "Rules:\n"
            "- NEVER write \"Not specified\" for Speed or Accuracy.\n"
            "- If Speed or Accuracy is missing, use best assumption or guess based on other fields.\n"
            "- Format should be beautiful and consistent, no markdown, no bullets, no emojis.\n"
            "- Maintain equal spacing after colons for clean readability.\n"
            "- The reason must be short and clearly reflect accuracy/speed/user goal.\n"
            "- Do not recommend the same model again and again across different inputs.\n"
            "- Consider diverse strengths of other models if multiple meet requirements."
        )

        try:
            completion = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a smart assistant helping select the best AI model "
                            "with a professional, plain-text report. Ensure speed is filled, "
                            "accuracy is shown as %, and output is beautifully aligned."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.4,
                max_tokens=800
            )

            result = completion.choices[0].message.content.strip()
            logger.info("GPT response generated successfully.")
            print(result)

            # Extract model name
            import re
            match = re.search(r"Model Name\s*:\s*(.+)", result)
            final_model = match.group(1).strip() if match else "UNKNOWN"

            # Store to MongoDB
            try:
                final_model_col.update_one(
                    {"email": username},
                    {
                        "$set": {
                            "email": username,
                            "analyzed_input": analyzed_input,
                            "final_model": final_model
                        }
                    },
                    upsert=True
                )
                print("📨 Inside report agent - saving for:", username)

                logger.info(f"Stored final recommendation for user {username}: {final_model}")
            except Exception as db_err:
                logger.error(f"Error saving final model to DB: {db_err}")

            return result

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"Error generating report: {e}"


    def get_model_info(self, model_name: str):
        try:
            doc = model_col.find_one({"model_name": model_name})
            if not doc:
                logger.warning(f"No document found in MongoDB for model: {model_name}")
                return f"No information found for model: {model_name}"

            info = (
                f"Speed    : {doc.get('speed', 'Unknown')}\n"
                f"Accuracy : {doc.get('accuracy', 'Unknown')}%\n"
                f"Pricing  : {doc.get('pricing', 'Unknown')}\n"
                f"Cloud    : {doc.get('cloud', 'Unknown')}\n"
                f"Region   : {doc.get('region', 'Unknown')}"
            )
            return info

        except Exception as e:
            logger.error(f"Error fetching model info for {model_name}: {e}")
            return f"Failed to retrieve model details due to an internal error."
