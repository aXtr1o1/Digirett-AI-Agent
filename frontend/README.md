# Frontend - Digirett AI Agent

Next.js frontend application for the Digirett AI Agent legal assistant.

## 📋 Overview

This frontend is built with **Next.js** and will be hosted on **Vercel**.

## 🎨 Development Workflow

1. **Design Phase**: Create Figma design first
2. **Client Validation**: Validate design with the client
3. **Implementation**: 
   - Add authentication
   - Implement the design interface

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ 
- npm or yarn or pnpm

### Installation

```bash
# Install dependencies
npm install

# Run development server
npm run dev
```

Visit: http://localhost:3000

## 📁 Project Structure

```
frontend/
├── app/                 # Next.js app directory
├── components/          # React components
├── lib/                 # Utilities and helpers
├── public/              # Static assets
├── styles/              # Global styles
└── package.json
```

## 🔧 Environment Variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=Digirett AI Agent
```

## 🛠️ Available Scripts

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run start        # Start production server
npm run lint         # Run ESLint
```

## 🚢 Deployment

This frontend will be hosted on **Vercel**.

 - connect your repository to Vercel for automatic deployments.

## 📚 Tech Stack

- **Framework**: Next.js 14
- **Styling**: Tailwind CSS
- **Authentication**: NextAuth.js
- **Deployment**: Vercel

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Submit a pull request

---

**Last Updated**: January 2026
