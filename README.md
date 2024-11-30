# Autonomous Surveillance Agents

This project implements an autonomous surveillance system using Python for the backend server and Unity for the simulation environment.

## Prerequisites

- Python 3.x
- Unity Editor
- OpenAI API Key

## Setup Instructions

### 1. Python Environment Setup

Create and activate a Python virtual environment:

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
.\venv\Scripts\activate
```

### 2. Environment Variables

Create a `.env` file in the root directory and add your OpenAI API key:

```
OPENAI_API_KEY=your_api_key_here
```

### 3. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 4. Start the Server

Run the server from the root directory of the project:

```bash
python server/v2.py
```

### 5. Unity Simulation

1. Open Unity Hub
2. Add and open the `simulation` folder as a Unity project
3. Once the server is running, start the Unity project by clicking the Play button in the Unity Editor

## Project Structure

- `server/`: Contains the Python backend server code
- `simulation/`: Contains the Unity project for the surveillance simulation
- `.env`: Configuration file for environment variables

## Notes

- Make sure the server is running before starting the Unity simulation
- Keep your OpenAI API key secure and never commit it to version control
- The server needs to be running continuously for the simulation to work properly
