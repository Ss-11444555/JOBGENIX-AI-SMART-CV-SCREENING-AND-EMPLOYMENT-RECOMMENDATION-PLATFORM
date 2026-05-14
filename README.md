# JOBGENIX AI: Smart CV Screening and Employment Recommendation Platform

JOBGENIX AI is a web-based recruitment platform that helps job seekers, companies, and administrators manage the hiring process. The system combines CV upload, OCR-based resume extraction, machine learning prediction, job recommendation, and virtual interview support.

## Features

- Job seeker, company, and admin authentication
- Job posting and job application management
- CV upload and profile management
- Resume text extraction from PDF and image files
- Machine learning prediction for suitable job roles
- Salary prediction based on resume information
- Match score calculation for candidate-job suitability
- AI-powered virtual interview questions and evaluation
- Dashboards for job seekers, companies, and administrators

## Machine Learning Model

The machine learning module is located in `NewAIPredict/`.

It uses two trained scikit-learn models:

- `job_role_classifier.pkl`: predicts the most suitable job role for a candidate.
- `salary_prediction_model.pkl`: predicts an estimated salary based on the candidate profile.

The prediction logic is handled by:

```text
NewAIPredict/predictor.py
```

The model receives resume-related features such as:

- Extracted resume text
- Detected technical skills
- Education information
- Estimated years of experience

The system prepares these features and sends them into the trained models. The output includes:

- Predicted job role
- Predicted salary
- Estimated experience years
- Top recommended job roles with confidence values
- Detected education information

## How The AI Prediction Works

1. The job seeker uploads a CV.
2. The system extracts text from the CV.
3. The extracted text is analyzed to detect skills, education, and experience.
4. The cleaned resume data is passed to the trained machine learning models.
5. The job role classifier predicts the best job category.
6. The salary model predicts an expected salary range/value.
7. The system calculates a match score using role prediction, salary, experience, and detected skills.
8. The result is saved and shown in the job seeker/company dashboard.

## CV Text Extraction and OCR

The CV extraction module uses OCR to read resume files. It supports PDF and image-based resumes.

Main OCR technologies:

- Tesseract OCR
- Poppler for converting PDF pages into images
- Pillow and OpenCV for image handling

The extraction process works like this:

1. A CV file is uploaded by the user.
2. The file is stored in the upload directory.
3. If the file is a PDF, Poppler converts the first page into an image.
4. Tesseract OCR reads text from the image or uploaded image file.
5. The extracted text is cleaned and passed to the AI/ML prediction pipeline.
6. Skills and education details are detected from the extracted resume text.

## Virtual Meeting and Interview Module

The virtual meeting/interview feature is located in:

```text
VirtualMeeting/
```

Parts of this module are also integrated into `app.py`.

The virtual interview system can:

- Generate technical interview questions based on the predicted or selected job role
- Conduct a structured interview flow
- Transcribe candidate audio answers
- Generate AI voice responses
- Evaluate interview answers
- Produce an interview review with score, strengths, weaknesses, and recommendation

The integrated interview workflow uses OpenAI services for:

- Speech-to-text transcription
- Interview question generation
- Answer evaluation
- Text-to-speech audio generation

The interview flow is designed around a five-question technical interview. Questions progress from basic to more advanced topics and are customized for the job role.

## Technologies Used

- Python
- Flask
- MySQL
- HTML
- CSS
- JavaScript
- Tesseract OCR
- Poppler
- OpenAI API
- scikit-learn
- pandas
- NumPy
- PyTorch / Ultralytics

## Project Structure

```text
.
|-- app.py
|-- start_flask.py
|-- requirements.txt
|-- README.md
|-- .env.example
|-- frontend/
|-- css/
|-- js/
|-- pages/
|-- components/
|-- OCR_code/
|-- NewAIPredict/
|   |-- predictor.py
|   |-- job_role_classifier.pkl
|   |-- salary_prediction_model.pkl
|-- VirtualMeeting/
|   |-- app.py
|   |-- interview_ai.py
|-- assets/
|-- uploads/
```

## Installation

1. Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
cd YOUR_REPOSITORY_NAME
```

2. Create a virtual environment:

```bash
python -m venv venv
```

3. Activate the virtual environment:

```bash
venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Create a `.env` file using `.env.example` as a template.

6. Run the application:

```bash
python app.py
```

7. Open the application:

```text
http://localhost:5000
```

## Environment Variables

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_database_password
DB_NAME=job_matching_system

OPENAI_API_KEY=your_openai_api_key

SMTP_HOST=your_smtp_host
SMTP_PORT=465
SMTP_USER=your_email@example.com
SMTP_PASS=your_email_password
SMTP_USE_SSL=1

TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
POPPLER_BIN=path_to_poppler_bin
```

## Requirements

- Python 3.11 recommended
- MySQL server
- Tesseract OCR installed
- Poppler installed if PDF OCR is used
- OpenAI API key for virtual interview, transcription, and text-to-speech features

