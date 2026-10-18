# RainGuard AI — Go Outside Before the Rain Does

An open-source, AI-powered preventive maintenance assistant for housing societies.

RainGuard AI helps maintenance teams prepare for rainfall by turning weather risks, asset information, and historical incidents into actionable inspection missions.

## The Problem

Housing societies may experience waterlogging, blocked stormwater drains, and other rain-related maintenance issues. Maintenance teams need a practical way to identify risks before rainfall causes problems.

Traditional maintenance processes can be reactive, with inspections and repairs taking place only after problems occur. RainGuard AI aims to help teams identify potential risks earlier and organize preventive maintenance.

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

A stormwater drain near Gate 2 has a history of waterlogging.

RainGuard AI helps maintenance teams prioritize the drain for inspection, document its condition, analyze inspection findings, and track preventive actions.

## Key Features

- **Preventive inspection planning:** Organize inspections around rainfall-related risks.
- **Asset and incident context:** Use available society asset information and historical incidents to inform inspections.
- **Field inspection support:** Record findings during physical inspections.
- **Photo evidence:** Attach images to inspection findings where supported by the application.
- **AI-assisted analysis:** Use a hosted Gemma model service to analyze inspection findings.
- **Maintenance tracking:** Track maintenance tasks and their completion.
- **Reinspection workflows:** Support follow-up inspections and durable workflow execution.

Feature availability depends on the application's configured services and environment.

## Technology Stack

- **Python and FastAPI:** Backend API and application logic.
- **JavaScript and Vite:** Frontend web application.
- **MongoDB Atlas:** Database.
- **Gemma:** AI-assisted analysis through a hosted model service.
- **Temporal:** Durable workflow orchestration.
- **GitHub Copilot:** AI-assisted software development.

## Best Use of GitHub Copilot

GitHub Copilot was used as an AI-assisted development tool during the development of RainGuard AI.

### How Copilot Was Used

- **Copilot Chat:** Explored implementation approaches, discussed technical decisions, and troubleshot development issues.
- **Copilot Agent Mode:** Assisted with implementing features and making coordinated changes across project files.
- **Iterative development:** Helped with implementation and refinement across the backend, frontend, and application workflows.

### Human Oversight

Copilot served as a development assistant. Development decisions and testing were part of the iterative process.

The goal was to use AI-assisted development to build a practical open-source application for preventive maintenance in housing societies.

This section describes the development workflow, not the AI functionality inside the application. Gemma is used for application-level AI-assisted analysis.

## Project Structure

```text
rainguard-ai/
├── backend/     # Backend API, application logic, and tests
├── frontend/    # Web application
├── docs/        # Project documentation
├── README.md    # Project overview and setup instructions
└── .gitignore   # Git ignore rules
```

## Getting Started

Follow these instructions to set up a local development environment.

### Prerequisites

- Python
- Node.js and npm
- Git
- MongoDB Atlas access, if required by your configuration
- Credentials for the configured hosted AI service
- Access to a Temporal service if you want to run Temporal workflows

### 1. Clone the Repository

```bash
git clone https://github.com/srikrishik/rainguard-ai.git
cd rainguard-ai
```

### 2. Configure Environment Variables

Check the backend directory for the provided environment template.

Create a local `.env` file based on `backend/.env.example`, if that template exists:

```powershell
Copy-Item .\backend\.env.example .\backend\.env
```

If the template is located elsewhere, adjust the path accordingly.

Open `backend/.env` and configure the environment variables required by your application.

Use your own credentials for the configured services.

**Never commit `.env` files, database passwords, API keys, or other secrets to GitHub.**

The `.env.example` file should contain placeholder values rather than real credentials.

### 3. Set Up the Backend

Open a terminal at the repository root:

```powershell
cd .\backend
```

Create a virtual environment:

```powershell
py -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the backend dependencies:

```powershell
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation, use the appropriate Python executable directly or resolve the local execution-policy issue according to your environment.

### 4. Run the Backend

From the `backend` directory, start the FastAPI development server using the application's configured entry point.

For example, if the application entry point is `app.main:app`:

```powershell
python -m uvicorn app.main:app --reload
```

If your application uses a different entry point or configuration, follow the corresponding project setup.

### 5. Set Up the Frontend

Open a separate terminal at the repository root:

```powershell
cd "$HOME\Downloads\RainGuard AI\frontend"
```

Install the frontend dependencies:

```powershell
npm install
```

Start the Vite development server:

```powershell
npm run dev
```

Open the local URL printed by Vite in your browser.

### 6. Temporal Workflows

Temporal is used for durable workflow orchestration.

To run Temporal workflows, configure the required service connection and environment variables, and start the appropriate Temporal worker according to the backend implementation.

A running Temporal service is required for workflows that depend on it.

## Configuration and Security

RainGuard AI may depend on external services for database access, hosted AI analysis, and workflow orchestration.

- Keep actual credentials in local environment files.
- Do not commit `.env` files.
- Use placeholder values in `.env.example`.
- Configure external services before testing features that depend on them.
- Do not expose credentials in screenshots, logs, issues, or public documentation.

## Testing

Backend tests are available in the `backend/tests/` directory.

From the backend directory, activate the virtual environment and run:

```powershell
python -m pytest
```

Test results depend on the current code, environment configuration, and available services.

## Project Goals

RainGuard AI aims to make preventive maintenance more organized and actionable for housing societies by connecting rainfall-related risks with field inspections, evidence collection, AI-assisted analysis, and maintenance follow-up.

## Open Source

RainGuard AI is an open-source project.

Repository: https://github.com/srikrishik/rainguard-ai

Contributions, feedback, and suggestions are welcome.

## Acknowledgements

- **GitHub Copilot:** AI-assisted development.
- **Gemma:** AI-assisted analysis through a hosted model service.
- **FastAPI, Vite, MongoDB Atlas, and Temporal:** Technologies used in the project.