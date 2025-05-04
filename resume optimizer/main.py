from flask import Flask, request, jsonify, render_template
import fitz  # PyMuPDF
import requests

app = Flask(__name__)

# --- CHANGE 1: Update API_URL to point to Ollama's default endpoint ---
# Ollama typically runs its API on http://localhost:11434
# The /v1/chat/completions path is compatible with Ollama's chat endpoint
API_URL = "http://localhost:11434/v1/chat/completions"

# Home Route (UI)
@app.route("/", methods=["GET", "POST"])
def home():
    return render_template("index.html") # Make sure you have an index.html template

# Function to extract text from uploaded PDF
def extract_text_with_structure(pdf_file):
    try:
        # Use BytesIO to read the uploaded file multiple times if needed
        from io import BytesIO
        pdf_data = BytesIO(pdf_file.read())
        doc = fitz.open(stream=pdf_data, filetype="pdf")
        pages = [page.get_text("dict")["blocks"] for page in doc if page.get_text("dict")]
        return doc, pages
    except Exception as e:
        print("Error extracting text:", e)
        return None, None

# --- CHANGE 2: Rename function and update model name for Ollama/Llama ---
# Renaming the function for clarity, as it now calls a local LLM via API
def call_local_llm(prompt):
    payload = {
        # --- CHANGE 2a: Change model name to your Llama3 model tag ---
        # Use 'llama3' for the default 8B version
        # Use 'llama3:70b' for the larger version (requires more resources)
        # Use specific tags like 'llama3:8b-instruct-q4_k_m' for quantized versions
        "model": "llama3.1:latest", # <--- You can change this tag if using a different size/quantization
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000, # Adjust if needed
        "temperature": 0.50 # Adjust if needed
    }
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        # Ollama's response structure is compatible with OpenAI's chat completions
        return response.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except requests.RequestException as e:
        print(f"Error in local LLM API call: {e}")
        # Provide more detail if possible, like response text for debugging
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response status code: {e.response.status_code}")
             print(f"Response text: {e.response.text}")
        return f"Error calling local LLM API: {e}"

# Resume Optimization Route
@app.route("/optimize_resume", methods=["POST"])
def optimize_resume():
    if "resume" not in request.files or "job_posting" not in request.form:
        # Return a proper response for missing data
        return render_template("index.html", optimized_resume="Error: Resume and job posting required"), 400

    uploaded_pdf = request.files["resume"]
    job_posting = request.form["job_posting"]

    # Pass a copy of the file stream if it needs to be read multiple times
    # extract_text_with_structure handles reading the stream inside the function
    original_doc, structured_pages = extract_text_with_structure(uploaded_pdf)
    if not original_doc or not structured_pages:
        return render_template("index.html", optimized_resume="Error: Failed to process PDF"), 500 # Use a 500 status for server error

    # Extract flat text from structured blocks (assuming the structure is helpful or needed elsewhere)
    # If structure isn't needed, you could simplify text extraction with get_text("text")
    flat_text = "\n\n".join(
        "\n".join(span["text"] for line in block.get("lines", []) for span in line.get("spans", []))
        for page in structured_pages for block in page
    ).strip()

    # Fallback if structured extraction failed or was empty, use plain text
    if not flat_text:
         try:
             # Need to seek back to the beginning of the file stream if read already
             uploaded_pdf.seek(0)
             temp_doc = fitz.open(stream=uploaded_pdf.read(), filetype="pdf")
             flat_text = temp_doc.get_text().strip()
             temp_doc.close()
         except Exception as e:
             print(f"Fallback plain text extraction failed: {e}")
             flat_text = "Could not extract text from PDF."


    if not job_posting or not flat_text or flat_text == "Could not extract text from PDF.":
         return render_template("index.html", optimized_resume="Error: Could not extract usable text from resume or job posting was empty."), 400


    prompt = f"""
    Improve the following resume so it aligns better with the job post. Use relevant keywords and phrasing but do not invent experience or details that are not present in the original resume. Maintain the overall structure and format of the original resume as much as possible, focusing on rephrasing and adding relevant keywords naturally.

    --- JOB POSTING ---
    {job_posting}

    --- ORIGINAL RESUME ---
    {flat_text}

    --- OPTIMIZED RESUME ---
    """

    # --- CHANGE 2b: Call the renamed function ---
    optimized_text = call_local_llm(prompt)

    # Add basic error handling for the LLM response
    if optimized_text.startswith("Error:"):
         return render_template("index.html", optimized_resume=f"LLM Error: {optimized_text}"), 500


    return render_template("index.html", optimized_resume=optimized_text)

if __name__ == "__main__":
    # Ensure debug is True only during development
    app.run(debug=True, use_reloader=False)