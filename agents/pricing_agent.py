import time
import openai
from openai import AzureOpenAI
from agents.logger import get_logger # type: ignore

logger = get_logger("pricing_agent", "logs/pricing_agent.log")

class PricingAgent:
    def __init__(self, assistant_id, azure_api_key, azure_endpoint, api_version="2024-05-01-preview"):
        self.assistant_id = assistant_id
        self.client = AzureOpenAI(
            api_key=azure_api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version
        )

    def analyze_pricing(self, model_list):
        logger.info("===== Step 3: Pricing Analysis Started =====")
        logger.info("Received model list for pricing:")
        for model in model_list:
            logger.info(f"   - {model}")

        question = (
            "Here is a list of shortlisted AI models:\n\n"
            + "\n".join(f"- {model}" for model in model_list) +
            "\n\nFor each model, check the uploaded file for pricing. "
            "If the file has pricing info, use it. If not, estimate the price based on your knowledge.\n"
            "Return the response as a table in this format:\n\n"
            "| Model | Estimated Price | Price Unit | Provider | Region |\n"
            "|-------|------------------|------------|----------|--------|"
        )

        logger.info("Asking assistant: %s", question)

        # Create thread
        thread = self.client.beta.threads.create()

        # Post message
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question
        )

        # Run assistant
        run = self.client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=self.assistant_id
        )

        # Wait for assistant response
        logger.info("Waiting for assistant response...")
        while run.status not in ["completed", "failed"]:
            time.sleep(2)
            run = self.client.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

        # Get assistant response
        messages = self.client.beta.threads.messages.list(thread_id=thread.id)
        response = ""
        for msg in messages.data:
            if msg.role == "assistant":
                response += msg.content[0].text.value

        logger.info("\nAssistant Pricing Response:\n" + response)
        return response
