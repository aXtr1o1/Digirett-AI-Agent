# Digirett Frontend Documentation

This document provides a detailed technical overview of the Digirett AI Agent frontend application.

## 🏗 Architecture & Stack
The frontend is a modern Single Page Application (SPA) built with the following core technologies:
- **Framework**: React.js (v18.3)
- **Styling**: Tailwind CSS for utility-first design and consistent UI.
- **Authentication**: Clerk (managed authentication and user management).
- **Icons**: Lucide React and React Icons.
- **API Communication**: Axios for RESTful requests to the backend.
- **Markdown Rendering**: `react-markdown` with `remark-gfm` for rich chat messages.

---

## 🔐 Authentication & Role-Based Access Control (RBAC)
Authentication is handled by **Clerk**. The application uses a custom integration to manage sessions and gate access based on user roles.

### User Roles
1. **User**: Can access the chat interface and manage personal conversations.
2. **Lawyer**: Can access the Lawyer Dashboard to handle escalated tickets and view chat histories.
3. **Admin**: Full access to all administrative features, user management, and dashboards.

### Security Implementation
- **`ClerkWithRouter`**: Custom provider that wraps the app to sync Clerk auth state with React Router.
- **`ProtectedRoute`**: A wrapper component that ensures only authenticated users can access specific routes (e.g., `/chat`).
- **`RoleGuard`**: A specialized component that gates routes based on the user's role (e.g., `/admin` or `/lawyer`).

---

## 📂 Core Pages & Features

### 1. Chat Interface (`/chat`)
The primary interface for interacting with the AI Agent.
- **Real-time Interaction**: Streaming-like experience for AI responses.
- **Source Citations**: Displays clickable links/references for AI-generated answers.
- **File Uploads**: Support for uploading documents for contextual analysis.
- **Conversation History**: Sidebar navigation to access and manage past chats.

### 2. Lawyer Dashboard (`/lawyer`)
The Human-in-the-Loop (HITL) command center.
- **Ticket Queue**: Lists all escalations requested by users.
- **Ticket Details**: Provides a full view of the conversation history that led to the escalation.
- **Status Management**: Lawyers can update the status of tickets (Pending, Resolved, etc.).

### 3. Admin Dashboard (`/admin`)
For system-level management.
- **User Management**: View and manage users and their roles.
- **System Logs**: (If applicable) monitoring system health and usage.

### 4. Onboarding & Provisioning
- **Invite Page (`/invite`)**: Handles incoming user invitations via unique tokens.
- **Provisioning (`/provisioning`)**: A guided flow for setting up new user accounts after invitation.

---

## 🧩 Component Breakdown

### Layout Components
- **`Sidebar`**: Manages navigation, conversation history, and user profile shortcuts.
- **`Header`**: Displays current location context and global actions.
- **`MainLayout`**: The top-level wrapper ensuring consistent spacing and responsive behavior.

### Chat Components
- **`MessageComposer`**: The input area with support for multi-line text and file attachments.
- **`MessageList`**: Renders the conversation stream using the `Message` component.
- **`SourceLinks`**: A dedicated component for rendering bibliographic references from the RAG pipeline.
- **`TypingIndicator`**: Visual feedback while the AI is generating a response.

---

## ⚙️ Environment Configuration
The frontend requires the following environment variables (defined in `.env`):
- `REACT_APP_CLERK_PUBLISHABLE_KEY`: Clerk integration key.
- `REACT_APP_API_URL`: Base URL for the backend API.
- `REACT_APP_SUPABASE_URL`: (Optional/Legacy) Supabase endpoint.
- `REACT_APP_SUPABASE_ANON_KEY`: (Optional/Legacy) Supabase public key.

---

## 🛠 Development Commands
- `npm start`: Runs the app in development mode at [http://localhost:3000](http://localhost:3000).
- `npm run build`: Builds the app for production to the `build` folder.
- `npm test`: Launches the test runner.
- `npm run lint`: Runs ESLint to check for code quality issues.
