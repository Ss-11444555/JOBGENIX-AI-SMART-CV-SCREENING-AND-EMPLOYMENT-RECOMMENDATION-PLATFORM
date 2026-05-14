import ollama
import os
import json 

# --- Configuration ---
MODEL_NAME = 'llama3:8b' # Using the specified model name

def generate_extraction_prompt(corpus):
    """
    Constructs a detailed system and user prompt for structured extraction.
    
    :param corpus: The extracted text from the resume.
    :return: A tuple containing (system_prompt, user_prompt).
    """
    
    # 1. System Prompt (Defining the role and required output format)
    system_prompt = (
        "You are an expert Resume Parsing AI. Your task is to accurately extract "
        "specific information from the provided resume text and return the result "
        "EXCLUSIVELY as a single, valid JSON object. Do not include any explanation, "
        "preamble, or text outside of the JSON block."
    )

    # 2. User Prompt (FIXED: Removed **bold** markdown from keys to prevent invalid JSON output)
    user_prompt = f"""
    Based on the text below, extract the following fields in the exact order:

    1.  name: The full name of the candidate.
    2.  email: The candidate's primary email address.
    3.  education: A list of objects, where each object contains:
        * degree: The degree obtained (e.g., Master of Science).
        * institution: The name of the university or school.
        * graduation_date: The year or date of graduation (e.g., 2019 or May 2019).
        * gpa (Optional): The GPA or relevant score, if present.
    4.  skills: A detailed list of technical and soft skills.
    5.  work_experience: A list of objects, where each object contains:
        * title: Job title (e.g., Senior Developer).
        * company: Company name.
        * duration: A string representing the employment period (e.g., Jan 2020 - Present).
    6.  language: A list of all languages the candidate speaks (e.g., English, Spanish).

    If a field cannot be found, use an empty string ("") or an empty list ([]) for its value.

    --- RESUME TEXT START ---
    {corpus}
    --- RESUME TEXT END ---
    """
    return system_prompt, user_prompt


def extract_data_with_ollama(corpus_text):
    """
    Main function to orchestrate the prompting and extraction, using the 
    corpus_text passed as an argument.
    
    :param corpus_text: The resume text obtained from the OCR process.
    :return: The extracted JSON string from the LLM, or None on error.
    """
    
    if not corpus_text:
        print("Error: Empty corpus provided for extraction.")
        return None

    system_prompt, user_prompt = generate_extraction_prompt(corpus_text)

    print(f"--- Sending Request to Ollama ({MODEL_NAME}) ---")
    
    try:
        client = ollama.Client()
        
        # Use the 'json' response format for reliable structured output
        response = client.generate(
            model=MODEL_NAME,
            prompt=user_prompt,
            system=system_prompt,
            format='json',
            # Increased prediction size to prevent truncation of large JSON outputs
            options={'num_predict': 4096}
        )

        # The model's response is the JSON string
        json_output = response['response']
        
        # NOTE: We return the output instead of printing it, 
        # allowing the main script to handle printing/logging and file saving.
        return json_output
        
    except ollama.RequestError as e:
        print(f"\nOllama Request Error: {e}")
        print("Hint: Is the Ollama server running? Is the model installed?")
        return None
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        return None