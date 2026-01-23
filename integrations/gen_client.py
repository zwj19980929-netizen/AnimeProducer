import requests
import json
from config import settings

class NanoBananaClient:
    def __init__(self):
        self.api_key = settings.NANO_BANANA_API_KEY
        self.api_url = settings.NANO_BANANA_API_URL

    def generate_image(self, prompt: str, reference_image_path: str = None) -> bytes:
        """
        Generates an image using Nano Banana API.
        If reference_image_path is provided, it's sent for consistency.
        """
        # Mocking the implementation if no API key is set for local testing without cost
        if not self.api_key or self.api_key == "your_nano_banana_api_key_here":
            print(f"[MOCK] Generating image for prompt: '{prompt}' with ref: '{reference_image_path}'")
            # Return a dummy 1x1 pixel black image
            return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # This payload structure is hypothetical based on common SD APIs
        payload = {
            "prompt": prompt,
            "negative_prompt": "low quality, bad anatomy",
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 30
        }

        # Handle reference image (e.g., via ControlNet or IP-Adapter)
        # In a real scenario, you might upload the image first or send base64
        if reference_image_path:
             # Assume API accepts a URL or base64. For now, just logging.
             print(f"Using reference image: {reference_image_path}")
             # payload["controlnet_image"] = encode_image(reference_image_path)

        try:
            response = requests.post(f"{self.api_url}/txt2img", headers=headers, json=payload)
            response.raise_for_status()
            # Assuming API returns JSON with a URL or base64
            # return decode_response(response.json())
            return response.content # Placeholder
        except Exception as e:
            print(f"Error generating image: {e}")
            return None

gen_client = NanoBananaClient()
