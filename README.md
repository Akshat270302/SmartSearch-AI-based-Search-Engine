# AI Search Engine

An AI-powered search application that combines web search, source-backed
AI answers, image search, conversational follow-up questions, and
Retrieval-Augmented Generation (RAG) for uploaded documents.

**Live application:** https://search.akshat04.live\
**API:** https://api.akshat04.live

## Overview

AI Search Engine brings traditional web search and AI-assisted answers
into one interface. It retrieves web results through SearXNG and uses
Google's Gemini models to generate answers. Users can switch between web
results, image results, and AI Mode. The application also supports
uploading documents and asking questions about their content through a
RAG workflow.

## Features

-   **Web search:** Retrieve web results through SearXNG.
-   **AI Mode:** Generate AI-assisted answers using Gemini and retrieved
    web evidence.
-   **Streaming responses:** Display AI answers progressively as the
    backend streams events.
-   **Source results:** Show web sources alongside search results and AI
    answers.
-   **Image search:** Browse image-search results in a dedicated view.
-   **Conversational follow-ups:** Ask follow-up questions with
    temporary conversation context.
-   **Document Q&A (RAG):** Upload supported documents and ask questions
    grounded in their content.
-   **Custom domains and HTTPS:** Frontend and API are served over
    HTTPS.

## Live Deployment

  -----------------------------------------------------------------------
  Component               Technology              Deployment
  ----------------------- ----------------------- -----------------------
  Frontend                React, Vite             Vercel

  API backend             Python, FastAPI         AWS EC2

  Web search              SearXNG                 Docker on EC2, bound to
                                                  loopback

  AI generation and       Google Gemini           Google AI Studio API
  embeddings                                      

  Reverse proxy and HTTPS Caddy                   EC2

  Document retrieval      ChromaDB (in-memory in  Backend process
                          the current setup)      
  -----------------------------------------------------------------------

-   Frontend: https://search.akshat04.live
-   Backend API: https://api.akshat04.live

> **Deployment note:** The current ChromaDB setup uses in-memory
> storage. Depending on how the application initializes its collection,
> uploaded-document indexes may be lost when the backend process
> restarts. Configure persistent storage before relying on long-lived
> document indexes.

## Architecture

1.  The user enters a query in the React frontend.
2.  The frontend calls the FastAPI backend over HTTPS.
3.  FastAPI retrieves web results from the privately hosted SearXNG
    service.
4.  For AI Mode, the backend prepares evidence and requests an answer
    from Gemini.
5.  The backend streams answer events to the frontend, which renders the
    response and available sources.
6.  For document Q&A, the document workflow extracts text,
    creates/retrieves embeddings, and uses relevant document content to
    support responses.

``` text
                         +-------------------------+
                         |       User Browser      |
                         +------------+------------+
                                      | HTTPS
                                      v
                         +-------------------------+
                         | React + Vite Frontend   |
                         |          Vercel         |
                         +------------+------------+
                                      | HTTPS API requests
                                      v
                         +-------------------------+
                         |       Caddy Proxy       |
                         |        AWS EC2          |
                         +------------+------------+
                                      |
                                      v
                         +-------------------------+
                         | FastAPI Backend         |
                         | 127.0.0.1:8000          |
                         +-------+---------+-------+
                                 |         |
                      Web search |         | AI generation /
                                 v         | embeddings
                       +----------------+  v
                       |    SearXNG     |  +----------------+
                       | 127.0.0.1:8080 |  | Google Gemini  |
                       +----------------+  +----------------+
```

## Technology Stack

### Frontend

-   React
-   Vite
-   JavaScript
-   Server-Sent Events (SSE) for streamed AI responses

### Backend and AI

-   Python
-   FastAPI
-   Uvicorn
-   Google Gen AI SDK / Gemini
-   Embeddings and ChromaDB for document retrieval
-   SearXNG for web search

### Deployment

-   AWS EC2 (Ubuntu)
-   Docker
-   Caddy reverse proxy with automatic HTTPS
-   Vercel
-   Custom domain and DNS configuration

## Local Development

The repository contains a frontend and a Python backend. Run them in
separate terminals during development.

### Prerequisites

-   Git
-   Node.js and npm
-   Python 3.12 or a compatible Python version supported by the project
-   A Google Gemini API key
-   Docker, if you want to run SearXNG locally

### 1. Clone the repository

``` bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd <YOUR_REPOSITORY_DIRECTORY>
```

Replace the placeholders with your repository URL and directory.

### 2. Configure the backend

Create and activate a virtual environment from the backend project
directory (the directory containing `main.py`):

``` bash
python -m venv .venv
```

Windows PowerShell:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

``` bash
source .venv/bin/activate
```

Install the backend dependencies using the dependency file provided by
the repository. For example, if the project has `requirements.txt`:

``` bash
pip install -r requirements.txt
```

Create a `.env` file in the backend application's expected working
directory. Use the variable names below and match the model names to the
models enabled for your API key:

``` dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_supported_gemini_model
GEMINI_EMBEDDING_MODEL=your_supported_embedding_model
SEARXNG_URL=http://127.0.0.1:8080
```

Do not commit `.env` or publish API keys. Keep a `.env.example`
containing placeholders only.

Start the API from the directory containing `main.py`:

``` bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API root should be available at `http://127.0.0.1:8000/`.
Interactive API documentation is typically available at
`http://127.0.0.1:8000/docs` while the backend is running.

### 3. Configure SearXNG

The backend expects a SearXNG instance at the URL configured in
`SEARXNG_URL`. Run SearXNG locally with Docker or configure the URL to
point to an instance you control.

For a local deployment, ensure that SearXNG is reachable at:

``` text
http://127.0.0.1:8080
```

Do not expose the SearXNG service publicly unless you have deliberately
configured and secured it for that purpose.

### 4. Configure and run the frontend

Open a second terminal and move to the frontend directory (the directory
containing `package.json`):

``` bash
cd frontend
npm install
```

Create the frontend environment file expected by the project, such as
`.env.local`, and configure the API base URL:

``` dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Start the Vite development server:

``` bash
npm run dev
```

Use the local URL printed by Vite in the terminal. If your frontend uses
a different environment-file name or port, follow the configuration in
the repository.

## Environment Variables

  --------------------------------------------------------------------------
  Variable                   Used by                 Purpose
  -------------------------- ----------------------- -----------------------
  `GEMINI_API_KEY`           Backend                 Authenticates requests
                                                     to Google's Gemini API.
                                                     Keep secret.

  `GEMINI_MODEL`             Backend                 Selects the Gemini
                                                     model used for answer
                                                     generation.

  `GEMINI_EMBEDDING_MODEL`   Backend                 Selects the embedding
                                                     model used for document
                                                     retrieval.

  `SEARXNG_URL`              Backend                 Base URL for the
                                                     SearXNG service.

  `VITE_API_BASE_URL`        Frontend                Base URL used by the
                                                     frontend to call the
                                                     backend API.
  --------------------------------------------------------------------------

Use model names supported by your Google AI Studio/API configuration. Do
not hard-code API keys in source code or expose them through frontend
variables.

## API Routes

The backend includes the following routes. Exact request and response
schemas should be checked in the current source code or at `/docs`.

  -----------------------------------------------------------------------
  Method                  Route                   Purpose
  ----------------------- ----------------------- -----------------------
  `GET`                   `/`                     Basic API health
                                                  response

  `GET`                   `/filters`              Returns available
                                                  search filter metadata

  `GET`                   `/search`               Retrieves web or image
                                                  search results

  `GET`                   `/ask`                  Generates an
                                                  AI-assisted answer

  `GET`                   `/ask/stream`           Streams an AI-assisted
                                                  answer

  `POST`                  `/ask/stream/context`   Streams an answer with
                                                  conversation context

  `POST`                  `/documents/extract`    Extracts text from an
                                                  uploaded document

  `POST`                  `/documents/retrieve`   Retrieves relevant
                                                  document content

  `POST`                  `/documents/ask`        Answers a question
                                                  using document content
  -----------------------------------------------------------------------

Confirm exact document routes in the current backend code or OpenAPI
documentation, as router prefixes can vary.

## Production Deployment

The live deployment uses the following arrangement:

-   **Vercel:** hosts the React/Vite frontend.
-   **AWS EC2:** runs the FastAPI backend and SearXNG.
-   **Caddy:** reverse-proxies HTTPS API requests to FastAPI.
-   **SearXNG:** bound to loopback so it is not directly exposed to the
    public internet.

Production configuration reminders:

1.  Set `VITE_API_BASE_URL` in Vercel to `https://api.akshat04.live`,
    then redeploy the frontend after changing the value.
2.  Configure backend CORS to allow the exact production frontend
    origin: `https://search.akshat04.live`.
3.  Keep the Gemini API key on the backend only.
4.  Keep FastAPI and SearXNG internal ports private; expose only the
    necessary web ports through the reverse proxy.
5.  Restrict SSH access to trusted IP addresses.
6.  Remember that an automatically assigned EC2 public IPv4 address can
    change after a stop/start. If it changes, update the API DNS record.
7.  Add authentication and appropriate access controls before exposing
    document upload and retrieval features to untrusted users.
8.  Configure persistent storage for document indexes if uploaded
    documents must remain available after a backend restart.
9.  Configure sensible request-size limits, timeouts, rate limits, and
    error handling before broader public use.

## Security

-   Never commit `.env`, API keys, private keys, or other credentials.
-   Use `.gitignore` to exclude environment files, virtual environments,
    caches, build output, and local databases as appropriate.
-   Store production secrets in the server's environment or deployment
    secret settings.
-   Review CORS and access controls before making endpoints publicly
    available.
-   Treat uploaded documents and their extracted contents as potentially
    sensitive.
-   Do not assume in-memory document indexes provide durable storage.

## Troubleshooting

### AI answers fail but web search works

-   Check that `GEMINI_API_KEY` is valid and loaded by the running
    backend.
-   Verify that the configured Gemini model is available to the API key.
-   Inspect backend logs for the underlying Gemini/API error.
-   Restart the backend after changing its environment file.

### Search returns no results

-   Check that `SEARXNG_URL` points to a reachable SearXNG instance.
-   Verify SearXNG is healthy and supports the requested response
    format.
-   Check backend logs for connection errors or upstream failures.

### Frontend cannot reach the API

-   Verify `VITE_API_BASE_URL` is correct for the current environment.
-   Confirm the backend and HTTPS reverse proxy are running.
-   Check CORS configuration for the frontend origin.
-   Redeploy the frontend after changing Vercel environment variables.

### Uploaded documents are unavailable after a restart

-   The current setup uses in-memory ChromaDB storage. Configure
    persistent storage and appropriate lifecycle handling if indexes
    need to survive restarts.

## Future Improvements

-   Persistent vector storage for uploaded documents
-   Authentication and access control for document workflows
-   Stronger request validation, rate limiting, and upload-size limits
-   Improved observability, structured logs, and health checks
-   Automated tests for search, streaming, and document Q&A

## License

No license is specified here. Add a `LICENSE` file and update this
section if you intend to publish the project under a particular
open-source license.
