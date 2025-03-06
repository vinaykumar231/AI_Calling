# AI Calling Project

## Overview
This AI-powered calling system automates voice calls without human intervention. It enables bulk calling, customized voice messages, and interactive AI-based responses.

## Features
- **Bulk Calling**: Automatically dial multiple numbers from a list.
- **AI-Driven Voice Calls**: Generate and customize voice messages.
- **No Human Intervention**: Calls are fully automated.
- **Call Scheduling**: Set up calls at specific times.
- **Twilio Integration**: Uses Twilio API for seamless call handling.
- **Real-Time Analytics**: Track call logs and response rates.
- **Custom Voice Messages**: Personalize messages using AI-generated speech.
- **OpenAI API Support**: Enhance interactions with AI-based voice responses.

## Technology Stack
- **Backend**: FastAPI (Python)
- **Database**: MySQL
- **Voice Handling**: Twilio API
- **AI Integration**: OpenAI API
- **Frontend**: React (if applicable)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/vinaykumar231/AI_calling.git
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables (`.env` file):
   ```
   SQLALCHEMY_DATABASE_URL=your_url
   OPENAI_API_KEY=your_api_key
   ```

4. Run the server:
   ```bash
   uvicorn main:app --reload
   ```

## Usage
- Upload a list of phone numbers.
- Set up custom voice messages.
- Schedule or trigger automated calls.
- Monitor call logs and response rates.

## Contributing
Feel free to submit issues or pull requests to improve this project.

## License
This project is licensed under the MIT License.

## Commit & Push to GitHub
Run these commands:
```bash
git add README.md
git commit -m "Added detailed README file"
git push origin main
```

