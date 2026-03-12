import os
import io
import time
import logging
from PIL import Image
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- INLINED PROVIDER (Dependencies: google-genai, pillow) ---
class GeminiAPIKeyProvider:
    def __init__(self, api_key: str, model: str = "gemini-3-pro-image-preview"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self._model = model
        self._name = "Nano Banana Pro (API Key)"

    def generate(self, prompt: str, output_path: str = None) -> str:
        from google.genai import types
        full_prompt = f"Generate a high-quality image: {prompt}"
        
        try:
            response = self.client.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    temperature=1.0,
                ),
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise

        # Extract image
        if not response.candidates:
            raise RuntimeError("No candidates returned")
            
        candidate = response.candidates[0]
        img_data = None
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                img_data = part.inline_data.data
                break
        
        if img_data is None:
            raise RuntimeError("No image data in response")

        if output_path is None:
            output_path = "output.png"

        img = Image.open(io.BytesIO(img_data))
        img.save(output_path)
        logger.info(f"Image saved to {output_path}")
        return output_path

# --- MAIN EXECUTION ---
def get_api_key():
    load_dotenv(override=True)
    return os.environ.get("GEMINI_API_KEY")

def main():
    api_key = get_api_key()
    if not api_key:
        print("❌ GEMINI_API_KEY not found in .env or environment")
        return

    provider = GeminiAPIKeyProvider(api_key=api_key)
    
    if not os.path.exists("heroes"):
        os.makedirs("heroes")

    prompts = [
        (
            "concept_quill.png",
            "A close-up, hyper-detailed watercolor painting of a mechanical golden quill writing on ancient glowing parchment. The ink is liquid gold and transforms into vibrant, colorful whimsical creatures (dragons, fairies) as it touches the paper. Magical, alchemical, studio ghibli style, white background."
        ),
        (
            "concept_mind.png",
            "A split composition. Left side is a wireframe technical blueprint of a human brain. Right side is a blooming explosion of vibrant watercolor flowers and golden vines. The transition is seamless, representing logic turning into art. High ticket, luxury, alchemical aesthetic."
        ),
        (
            "concept_liquid.png",
            "A glass jar labeled 'Ideas' tipped over, spilling a galaxy of golden stars and watercolor clouds that form a storybook scene. Dark moss green background, cinematic lighting, 8k resolution, highly detailed."
        )
    ]

    print(f"🎨 Generating {len(prompts)} Hero Concepts using {provider._name}...")
    
    for filename, prompt in prompts:
        print(f"   👉 Generating {filename}...")
        try:
            provider.generate(prompt, output_path=f"heroes/{filename}")
            print(f"      ✅ Success!")
        except Exception as e:
            print(f"      ❌ Failed: {e}")
        time.sleep(2) # Brief pause

if __name__ == "__main__":
    main()
