import os
import tempfile
import pandas as pd
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from langchain_community.vectorstores import FAISS

# Load environment variables
load_dotenv()

# Initialize OpenAI API key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OpenAI API key not found. Please set it in the .env file.")

# Initialize Flask app
app = Flask(__name__)

# Initialize OpenAI Embeddings
embeddings = OpenAIEmbeddings(api_key=api_key)

# In-memory storage for documents and patient data
documents_db = None
patient_data = None

# Route for rendering the main page
@app.route("/")
def home():
    print("✅ Flask is rendering index.html")  # Debugging message
    return render_template("index.html")

# Helper function to process PDF documents
def process_pdf_documents(uploaded_files):
    global documents_db
    rec_chunks = []
    try:
        for uploaded_file in uploaded_files:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(uploaded_file.read())
                temp_file_path = temp_file.name

            loader = PyMuPDFLoader(temp_file_path)
            documents = loader.load()

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=500)
            chunks = text_splitter.split_documents(documents)
            rec_chunks.extend(chunks)

            os.remove(temp_file_path)

        documents_db = FAISS.from_documents(rec_chunks, embeddings)
        return "PDF documents processed successfully!"
    except Exception as e:
        return f"Error processing PDF documents: {e}"

# Route for handling file uploads
@app.route("/upload", methods=["POST"])
def upload_files():
    global patient_data
    pdf_files = request.files.getlist("pdf_files")
    csv_file = request.files.get("csv_file")

    response = {}

    if pdf_files:
        response["pdf_status"] = process_pdf_documents(pdf_files)

    if csv_file:
        try:
            patient_data = pd.read_csv(csv_file)
            response["csv_status"] = "Patient data CSV processed successfully!"
        except Exception as e:
            response["csv_status"] = f"Error processing CSV file: {e}"

    return jsonify(response)

# Route for handling questions
@app.route("/ask", methods=["POST"])
def ask_question():
    global documents_db, patient_data
    data = request.json
    question = data.get("question", "")

    if not question:
        return jsonify({"response": "Please provide a valid question."})

    response_data = {"question": question, "response": ""}

    if documents_db:
        try:
            model = ChatOpenAI(api_key=api_key, model_name="gpt-3.5-turbo", temperature=0)
            prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant. Answer the user's questions based on the document."),
                ("user", question)
            ])
            chain = LLMChain(llm=model, prompt=prompt)
            response_data["response"] = chain.run(question)
        except Exception as e:
            response_data["response"] = f"Error processing question: {e}"

    if patient_data is not None and ("patients" in question.lower() or "eligible" in question.lower()):
        try:
            if "cancer" in question.lower():
                eligible_patients = patient_data[patient_data['Condition'].str.contains("cancer", case=False, na=False)]
            elif "diabetes" in question.lower():
                eligible_patients = patient_data[patient_data['Condition'].str.contains("diabetes", case=False, na=False)]
            else:
                eligible_patients = pd.DataFrame()

            if not eligible_patients.empty:
                response_data["response"] += "\nEligible patients:\n"
                response_data["response"] += eligible_patients.to_string(index=False)
            else:
                response_data["response"] += "\nNo eligible patients found."
        except Exception as e:
            response_data["response"] += f"\nError processing patient data: {e}"

    return jsonify(response_data)

# Ensure Flask runs correctly
if __name__ == "__main__":
    app.run(debug=True)
