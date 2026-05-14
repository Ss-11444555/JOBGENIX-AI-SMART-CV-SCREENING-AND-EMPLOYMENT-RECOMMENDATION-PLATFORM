# Job Matching System

A web-based job matching platform with role-based dashboards for job seekers, companies, and administrators. The system includes job posting, job applications, CV upload, OCR-based resume text extraction, and AI-assisted job matching features.

## Features

- Job seeker registration and login
- Company registration and login
- Admin dashboard
- Job posting and job management
- Job application management
- CV upload and profile management
- OCR support for extracting text from resumes
- AI/ML-based resume and job matching features
- Mock interview and analytics pages

## Technologies Used

- Python
- Flask
- MySQL
- HTML
- CSS
- JavaScript
- Tesseract OCR
- OpenAI API
- scikit-learn
- PyTorch / Ultralytics

## Project Structure

```text
.
├── app.py
├── start_flask.py
├── requirements.txt
├── frontend/
├── css/
├── js/
├── pages/
├── components/
├── OCR_code/
├── NewAIPredict/
├── VirtualMeeting/
└── assets/
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

## Important Notes

- Do not upload `.env` to GitHub because it contains private credentials.
- Do not upload virtual environment folders such as `venv` or `venv311`.
- Uploaded CVs and generated temporary files should stay outside GitHub.
