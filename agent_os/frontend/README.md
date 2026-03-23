# AgentOS Frontend

This is a React-based observability dashboard for TradingAgents.

## Tech Stack
- **Framework:** React (Vite)
- **UI Library:** Chakra UI
- **State Management:** React Context / Hooks
- **Communication:** Axios (REST) & WebSockets

## Getting Started

1.  **Initialize the project:**
    ```bash
    npm create vite@latest . -- --template react-ts
    npm install @chakra-ui/react @emotion/react @emotion/styled flutter-framer-motion axios lucide-react
    ```

2.  **Run the development server:**
    ```bash
    npm run dev
    ```

## Core Components Structure

- `src/components/CommandCenter/`: The main terminal and agent map.
- `src/components/Portfolio/`: Portfolio holdings and metrics.
- `src/hooks/useAgentStream.ts`: Custom hook for WebSocket streaming.
- `src/context/AuthContext.tsx`: Mock auth and multi-tenant support.
