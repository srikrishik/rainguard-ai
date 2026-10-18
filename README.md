# RainGuard AI - Go Outside Before the Rain Does



An open-source, AI-powered preventive maintenance assistant for housing societies.



RainGuard AI helps maintenance teams prepare for rainfall by turning weather risks, asset information, and historical incidents into actionable inspection missions.



## The Problem



Housing societies may experience waterlogging, blocked stormwater drains, and other rain-related maintenance issues. Maintenance teams need a practical way to identify risks before rainfall causes problems.



## The Solution



RainGuard AI supports preventive maintenance through the following workflow:



1. Identify rainfall-related risks.

2. Prioritize vulnerable society assets.

3. Generate inspection checklists.

4. Record findings during field inspections.

5. Attach photo evidence.

6. Use AI-assisted analysis to interpret findings.

7. Track maintenance tasks and completion.

8. Support reinspection and durable workflow execution.



## Example Scenario



A stormwater drain near Gate 2 has a history of waterlogging. RainGuard AI helps maintenance teams prioritize the drain for inspection, document its condition, and track preventive actions.



## Technology Stack



- Python and FastAPI — Backend API

- JavaScript and Vite — Frontend

- MongoDB Atlas — Database

- Gemma — AI-assisted analysis through a hosted model service

- Temporal — Durable workflow orchestration

- GitHub Copilot — AI-assisted development



## Project Structure



- `backend/` — Backend API, application logic, and tests

- `frontend/` — Web application

- `docs/` — Project documentation



## Getting Started



### Prerequisites



- Python

- Node.js and npm

- MongoDB Atlas access if required

- Credentials for the configured hosted AI service

- Temporal service access if you want to run Temporal workflows



### 1. Clone the repository



```bash

git clone https://github.com/srikrishik/rainguard-ai.git

cd rainguard-ai

