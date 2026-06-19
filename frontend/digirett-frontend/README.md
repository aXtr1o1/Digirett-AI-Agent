# Digirett AI Agent Frontend

Welcome to the **Digirett AI Agent Frontend** — a premium, enterprise-grade React-based user interface designed for human-in-the-loop (HITL) legal consultancy, Retrieval-Augmented Generation (RAG) assistant chat, and role-based workspace management. 

Featuring stunning dark-mode aesthetics, custom micro-animations, glowing background orbs, and seamless transitions, this application provides an exceptionally premium and responsive experience for clients, lawyers, and administrators.

---

## Core Architecture 

*   **Real-time RAG Legal Assistant**: Context-aware, multi-turn Norwegian law assistant using WebSocket streaming, typing animations, and source citation links.
*   **Role-Based Access Control (RBAC)**: Secure routing mapped dynamically through Clerk user metadata roles (`user`, `lawyer`, `admin`) to automatically redirect clients to their chat dashboard, lawyers to their active queues, and administrators to the management portal.
*   **Lawyer Case Workspace**: Complete ticket management dashboard allowing lawyers to self-claim cases, review full chat logs/document contexts, schedule calendar consultations via Cal.com, and log legal resolutions.
*   **Admin Management Portal**: Control room for creating invitation tokens, managing user statuses (active, suspended, demoted), and auditing incoming queries.

---

## Production Folder Structure

The frontend is structured modularly to decouple API services, custom hooks, reusable components, and global layout providers:

```text
digirett-frontend/
├── public/                      # Static assets & index.html
├── src/
│   ├── __test__/                # Unit and integration test suites
│   ├── components/              # Reusable UI Components
│   │   ├── auth/                # Sign-In/Up forms, SSOCallbacks, and Guards
│   │   │   ├── ForgotPassword.jsx
│   │   │   ├── ProtectedRoute.jsx
│   │   │   ├── RoleGuard.jsx
│   │   │   ├── SSOCallback.jsx
│   │   │   ├── SignInForm.jsx
│   │   │   ├── SignUpForm.jsx
│   │   │   ├── SocialLogin.jsx
│   │   │   └── UserProfile.jsx
│   │   ├── chat/                # Messaging blocks, stream citation containers
│   │   │   ├── BookingSystem.jsx
│   │   │   ├── ChatContainer.jsx
│   │   │   ├── EscalationStatusCard.jsx
│   │   │   ├── FileUploadMessage.jsx
│   │   │   ├── Message.jsx
│   │   │   ├── MessageComposer.jsx
│   │   │   ├── MessageList.jsx
│   │   │   ├── ResolutionNotification.jsx
│   │   │   ├── SourceLinks.jsx
│   │   │   └── TypingIndicator.jsx
│   │   ├── common/              # Global buttons, glowing layers, alert modals
│   │   │   ├── BackgroundLayer.jsx
│   │   │   ├── Button.jsx
│   │   │   ├── ErrorMessage.jsx  # Sleek dark-mode modal alert
│   │   │   ├── GlowingOrb.jsx
│   │   │   ├── Input.jsx
│   │   │   ├── LoadingSpinner.jsx
│   │   │   └── UpgradeCard.jsx
│   │   └── layout/              # Sidebars, Header, and Main workspace layout
│   │       ├── Header.jsx
│   │       ├── LegalPanel.jsx
│   │       ├── MainLayout.jsx
│   │       └── Sidebar.jsx
│   │
│   ├── hooks/                   # Custom React State & Lifecycle Hooks
│   │   ├── useChat.js           # WS message streaming connection
│   │   ├── useConversations.js  # Conversational history & deletion
│   │   ├── useCopyToClipboard.js
│   │   └── useDocumentUpload.js # PDF/Doc upload validations & sizes
│   │
│   ├── pages/                   # Main Page Views
│   │   ├── AdminDashboard.jsx   # Admin management panel
│   │   ├── ChatPage.jsx         # Client chat assistant page
│   │   ├── ForgotPasswordPage.jsx
│   │   ├── InvitePage.jsx       # Validates organizational signup invites
│   │   ├── LawyerDashboard.jsx  # Case queue & claim dashboard
│   │   ├── ProvisioningPage.jsx # Syncing loader screen
│   │   ├── SignInPage.jsx       # Custom themed login portal
│   │   ├── SignUpPage.jsx       # Clerk signup page wrapper
│   │   ├── SuspendedPage.jsx    # Restricted user landing route
│   │   └── TicketDetailsPage.jsx# Details & outcomes for escalated cases
│   │
│   ├── providers/               # Global Context Providers
│   │   ├── ClerkWithRouter.jsx  # Handles auth navigation hooks
│   │   └── ThemeProvider.jsx    # Client light/dark mode configurations
│   │
│   ├── services/                # Decoupled Network/API Service Layer
│   │   ├── adminService.js      # User states, invites, audits
│   │   ├── api.js               # Base axios client (Clerk token injector)
│   │   ├── calService.js        # Cal.com API bridge
│   │   ├── chatService.js       # WebSocket query stream endpoints
│   │   ├── conversationService.js
│   │   ├── documentService.js   # Attachment uploads
│   │   ├── hitlService.js       # Escalations & lawyer assignment queue
│   │   ├── inviteService.js     # Invite token verifications
│   │   └── sourceService.js     # Cite URL resolution
│   │
│   ├── styles/                  # Global style extensions
│   │   └── clerkTheme.js        # Elegant dark styles for Clerk sub-elements
│   │
│   ├── utils/                   # Shared configurations & endpoint maps
│   │   └── constants.js
│   │
│   ├── App.js                   # Application Router and Guard mappings
│   ├── index.js                 # App mounting entry point
│   ├── App.css
│   └── index.css                # Global styles, scrollbars, Tailwind rules
│
├── package.json                 # Project dependencies & scripts
├── tailwind.config.js           # Premium CSS token system
└── postcss.config.js            # PostCSS configuration
```

---

## Local Development & Quick Start


### 1. Installation
Clone this repository and run the package manager inside the root of this frontend folder:
```bash
npm install
```

### 2. Environment Configuration
Create a `.env` file in the root of the `digirett-frontend` folder:
```env
# Clerk Authentication Keys
REACT_APP_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
REACT_APP_CLERK_SIGN_IN_URL=/sign-in
REACT_APP_CLERK_SIGN_UP_URL=/sign-up
REACT_APP_CLERK_AFTER_SIGN_IN_URL=/
REACT_APP_CLERK_AFTER_SIGN_UP_URL=/

# Backend API Configuration
REACT_APP_API_BASE_URL=http://localhost:8000

# Supabase Configurations (Web clients)
REACT_APP_SUPABASE_URL=https://your_supabase_ref.supabase.co
REACT_APP_SUPABASE_ANON_KEY=your_supabase_anon_key
```

### 3. Running Locally
Launch the hot-reloading webpack dev server:
```bash
npm start
```
The application will open automatically at [http://localhost:3000](http://localhost:3000).

---

## Production Build & Deployment

To bundle the application into highly-optimized, minified static assets for production hosting (e.g., Netlify, Vercel, S3):

```bash
npm run build
```

This compiles your React application into the `./build` folder. The production assets feature:
*   Code-splitting and chunk size optimization.
*   Standardized production-level compression.
*   Production-optimized API connections (leveraging dynamic .env configurations).

---

## Performance Optimizations Implemented
*   **Ref-Latched Auth Handshakes**: Prevents duplicate multi-redirect cycles on Google login inside the SSO callback.
*   **Asynchronous Webhook offloading support**: Coupled with the backend background task queuing model, eliminating block-times during user syncing.
*   **Decoupled Service Layers**: Fully optimized Axios API bridges with cached token injections, avoiding unnecessary token fetch handshakes.

## Login Details

--Admin

Username: admin 
Pass : DigirettAdmin@123 

--Admin with lawyer access

Username : adminlawyer
Pass : DigirettAdminLawyer@123

--Lawyer

Username: lawyer1
Pass: DigirettLawyer@123

--Users

Username: tamiluser
Pass: tamiluser@123

Username: pragauser
Pass: pragauser@123

Username: vineeshuser
Pass: vineeshuser@123
