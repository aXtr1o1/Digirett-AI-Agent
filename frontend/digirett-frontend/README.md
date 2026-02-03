Lovdata RAG Chat - React Frontend
Clean, minimal chat interface for Norwegian legal AI assistant powered by FastAPI RAG backend.

🎯 Features
✅ Real-time streaming responses - Token-by-token display
✅ Source citations - Direct Lovdata links with context
✅ Markdown rendering - Formatted legal text
✅ Thinking process hidden - Clean UX without internal reasoning
✅ Responsive design - Mobile-friendly interface
✅ Error handling - Graceful fallbacks

📁 Project Structure
rag-chat-frontend/
├── public/
│   └── index.html
├── src/
│   ├── App.js              # Main chat component
│   ├── App.css             # Styling
│   ├── index.js            # React entry point
│   └── index.css           # Global styles
├── package.json            # Dependencies
├── .gitignore
└── README.md

🚀 Quick Start
1. Install Dependencies
bashnpm install
2. Configure API Endpoint
Update API_BASE_URL in src/App.js:
javascriptconst API_BASE_URL = 'https://your-backend-url.ngrok-free.dev';
3. Run Development Server
bashnpm start
Open http://localhost:3000

Run command 
----npm install
----npm start
   
🔧 Available Scripts
CommandDescriptionnpm startRuns dev server on port 3000npm run buildCreates production build in /buildnpm testLaunches test runner

📦 Dependencies
PackageVersionPurposereact^19.2.4UI frameworkreact-markdown^10.1.0Render formatted responsesreact-scripts5.0.1CRA build tools

🎨 UI Components
Chat Container

Auto-scrolling message list
User/assistant message bubbles
Empty state placeholder

Message Display

Markdown rendering (headings, lists, code)
Source citations with:

Numbered badges
Clickable Lovdata URLs
Context snippets



Input Area

Text input with Enter-to-send
Send button with loading spinner
Disabled state during requests


🔄 Streaming Logic
Event Types Handled:
javascript{type: 'token', data: 'word'}      // Append to response
{type: 'sources', data: [...]}     // Store citations
{type: 'complete', metadata: {}}   // Finalize message
{type: 'error', message: '...'}    // Show error
Thinking Process Filtering:

Hides content between <think> and </think> tags
Only displays final reasoning output


🎯 Key Features Explained
1. Real-time Streaming
Uses Server-Sent Events (SSE) to stream tokens as backend generates them.
2. Source Management
Displays top 3 sources with:

Document title
Lovdata URL
Relevant text snippet

3. Error Handling

Network errors → Red error bubble
Empty responses → Graceful fallback
Loading states → Spinner animation


🔐 Security Notes

No API keys in frontend
Backend handles authentication
CORS configured on FastAPI
ngrok headers added automatically


🐛 Troubleshooting
Issue: CORS errors
Fix: Ensure backend allows Access-Control-Allow-Origin: *
Issue: Streaming doesn't work
Fix: Check Accept: text/event-stream header
Issue: Sources not showing
Fix: Verify include_sources: true in request

