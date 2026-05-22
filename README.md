# ManualMage
## 1. Project Overview
ManualMage is an intelligent web application designed to automatically generate structured Word documents (DOCX) from video files. By leveraging advanced Machine Learning models for speech recognition, frame deduplication, and generative AI content analysis, this tool extracts key insights and visuals from videos, formatting them into professional, easy-to-read manuals or summaries.
## 2. Project Features
- **Video Upload:** Seamlessly upload video files via a modern web interface.
- **Background Processing:** A robust asynchronous backend pipeline that processes videos without blocking the user experience.
- **Audio Transcription:** Converts video audio into accurate text using an advanced ASR model.
- **Frame Extraction & Deduplication:** Extracts frames using FFmpeg and intelligently removes visually redundant frames.
- **Generative AI Analysis:** Synthesizes the transcribed text and key visuals into a cohesive document structure.
- **Document Generation:** Automatically generates a formatted Word document (.docx) containing the synthesized content and images.
- **Job Tracking:** Track the progress of video processing jobs in real-time.
- **Secure Downloads:** Time-limited, token-secured links to download the finished documents.
## 3. Tech Stack
### Frontend
- **Angular 18:** A powerful framework for building the single-page application.
- **Tailwind CSS:** A utility-first CSS framework for rapidly styling the modern UI.
- **Firebase:** Real-time job state tracking using Firestore.
### Backend
- **FastAPI:** A high-performance Python web framework used for building the API and handling background tasks.
- **Uvicorn:** An ASGI web server implementation for Python.
- **Firebase Admin SDK:** Server-side integration with Firestore.
### AI Models Used
The pipeline utilizes three core AI models to process and understand the video content:
1. **Qwen3-ASR (0.6B):** An Automatic Speech Recognition (ASR) model. It processes the audio track of the uploaded video to generate highly accurate text transcriptions of the spoken content.
2. **CLIP (Contrastive Language-Image Pretraining):** A computer vision model used during the frame deduplication stage. By extracting visual embeddings from video frames, CLIP helps identify and discard redundant or nearly identical frames, ensuring only unique visual information is passed to the next stage.
3. **Gemini (Google Generative AI):** A powerful Large Language Model (LLM) that analyzes the transcribed text alongside the key extracted frames. It synthesizes this multi-modal information to generate the final structured content and layout for the resulting document.
## 4. Steps to Locally Run this Project
### Prerequisites
- Node.js (v18+)
- Python (v3.10+)
- FFmpeg installed and added to your system PATH
- Firebase Admin SDK JSON credentials (`manual-mage-firebase-adminsdk-...json`)
- Gemini API Key
### Quick Start (Windows)
If you are on Windows, you can use the provided batch script to start both the frontend and backend servers simultaneously:
1. Open a terminal in the root directory of the project.
2. Make sure you have set up a Python virtual environment in `backend\venv` and installed node modules in `frontend\node_modules`.
3. Run the start script:
   ```cmd
   dev-start.bat
   ```
### Manual Setup
**Backend Setup:**
1. Navigate to the backend directory: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Set your Gemini API key as an environment variable (e.g., `set GEMINI_API_KEY=your_key_here`).
6. Start the FastAPI server: `uvicorn main:app --reload --port 7860`

**Frontend Setup:**
1. Navigate to the frontend directory: `cd frontend`
2. Install dependencies: `npm install`
3. Start the development server: `npm start` (or `ng serve`)
4. Access the application in your browser at `http://localhost:4200`.
## 5. Contact & Connect
Let's connect! You can find me on LinkedIn here: [Haider Dawasaz](https://www.linkedin.com/in/haider-dawasaz/)
