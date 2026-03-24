
Digirett Frontend

A modern, production-ready React frontend for the Digirett platform, featuring authentication, chat-based interactions, and conversation management. Built with scalability, maintainability, and performance in mind.

🚀 Tech Stack

React (Create React App)
Tailwind CSS – utility-first styling
Axios / Fetch – API communication
React Router – client-side routing
Jest & React Testing Library – testing

📁 Project Structure
digirett-frontend/
│
├── public/                  # Static assets
│   ├── index.html
│   └── favicon.ico
│
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── auth/            # Authentication components
│   │   ├── chat/            # Chat UI & logic
│   │   ├── common/          # Shared UI elements
│   │   ├── conversation/    # Conversation list & items
│   │   └── layout/          # Header, Sidebar, Layouts
│   │
│   ├── hooks/               # Custom React hooks
│   ├── pages/               # Page-level components
│   ├── providers/           # Context & providers
│   ├── services/            # API & business logic
│   ├── utils/               # Constants & helpers
│   ├── __test__/            # Unit tests
│   │
│   ├── App.js
│   ├── index.js
│   └── index.css
│
├── .env.example             # Environment variables template
├── package.json
├── tailwind.config.js
└── README.md

⚙️ Environment Variables

Create a .env file in the root directory using .env.example as reference:
envREACT_APP_API_BASE_URL=your_backend_api_url
⚠️ Never commit .env files to version control.

🛠️ Installation & Setup
Prerequisites

Node.js ≥ 16
npm or yarn

Steps
bash# Navigate to the project directory
cd frontend/digirett-frontend

# Install dependencies
npm install

# Start development server
npm start
App will run at:  👉 http://localhost:3000

🧪 Testing
Run unit tests with:
npm test
Tests are written using Jest and React Testing Library.

📦 Production Build
To generate an optimized production build:
npm run build
The build output will be available in the build/ directory.


🔗 API Integration
All backend communication is abstracted in:
src/services/
├── api.js
├── chatService.js
├── conversationService.js
└── sourceService.js
This separation ensures:

Clean architecture
Easy maintenance
Testability

🎨 UI & Styling

Tailwind CSS for fast and consistent styling
Reusable UI components under components/common
Responsive layout with Sidebar & Header

📈 Best Practices Followed

✅ Modular component structure
✅ Separation of concerns
✅ Environment-based configuration
✅ Reusable hooks and services
✅ Production-ready folder organization

📝 Available Scripts
In the project directory, you can run:
---npm start

Runs the app in development mode.

Open http://localhost:3000 to view it in your browser.
The page will reload when you make changes.

You may also see any lint errors in the console.
---npm test
Launches the test runner in interactive watch mode.

See the section about running tests for more information.
---npm run build