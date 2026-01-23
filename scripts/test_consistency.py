import os
import sys

# Add root to sys.path
sys.path.append(os.getcwd())

from integrations.gen_client import gen_client
from config import settings

def test_consistency(reference_image_path: str):
    print(f"Starting consistency test with reference: {reference_image_path}")

    # Define 5 different actions/prompts
    actions = [
        "drinking tea in a garden",
        "fighting with a sword",
        "reading a book in a library",
        "running in the rain",
        "sleeping on a couch"
    ]

    output_dir = os.path.join(settings.OUTPUT_DIR, "consistency_test")
    os.makedirs(output_dir, exist_ok=True)

    for i, action in enumerate(actions):
        prompt = f"A character {action}, consistent with reference image."
        print(f"Generating image {i+1}/5: {prompt}")

        image_data = gen_client.generate_image(prompt, reference_image_path)

        if image_data:
            file_path = os.path.join(output_dir, f"consistency_{i+1}.png")
            with open(file_path, "wb") as f:
                f.write(image_data)
            print(f"Saved to {file_path}")
        else:
            print(f"Failed to generate image {i+1}")

if __name__ == "__main__":
    # Create a dummy reference image if it doesn't exist for testing logic
    ref_path = "assets/characters/test_ref.png"
    if not os.path.exists(ref_path):
        with open(ref_path, "wb") as f:
            f.write(b'\x00') # Dummy content

    test_consistency(ref_path)
