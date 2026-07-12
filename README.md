# GitChat

This repository contains a full-stack Retrieval-Augmented Generation (RAG) application designed to interact with codebases. It allows users to query and analyze code repositories using an AI agent powered by vector search.

## Architecture

The system is built using a modern microservices architecture to separate concerns and ensure scalability:

1.  **Frontend (React)**: Built with React, Vite, and Tailwind CSS. It communicates with the API Gateway to send user queries and display the AI agent's responses.
2.  **API Gateway (Node.js)**: Built with Express and MongoDB. It acts as the bridge between the frontend and the AI service, managing client requests, handling chat history, and storing application state.
3.  **AI Service (Python)**: Built with FastAPI and LangGraph. This component contains the core AI logic. It receives queries from the API Gateway, performs vector searches against the codebase using MongoDB Atlas, and generates intelligent responses.

## Usage

Once the application is successfully deployed, open your web browser and navigate to the deployed frontend URL. 

From the interface, you can initiate a chat session to query your indexed codebase. The AI agent will search through the vectorized code in MongoDB Atlas and return context-aware explanations and answers.
