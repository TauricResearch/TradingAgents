# Implementation Plan: TradingAgents k8s Deployment

This document outlines the strategy for building and deploying the TradingAgents framework to a Raspberry Pi Kubernetes cluster (ARM64), including the addition of a web-based UI.

## Phase 1: Infrastructure & ARM64 Preparation
- **Multi-Arch Builds:** Configure Docker Buildx to target `linux/arm64`.
- **Registry:** Push images to a private registry or GitHub Container Registry (GHCR).
- **K8s Persistent Storage:** Define a `PersistentVolumeClaim` (PVC) with `ReadWriteMany` access to share trade logs and memory between the Agent CronJobs and the UI Dashboard.

## Phase 2: UI & API Development
- **Backend (FastAPI):**
    - Create a service to parse JSON logs in the shared volume.
    - Provide endpoints for trade history, active run status, and agent "reflections."
- **Frontend (React + Vanilla CSS):**
    - Implement `reactflow` for agentic graph visualization.
    - Design a "Senior Analyst" aesthetic (dark mode, high-contrast data tables, interactive node sidebars).
- **Integration:** Update the `TradingAgentsGraph` to support optional webhook callbacks for real-time state updates.

## Phase 3: Workload Definition
- **Agents (CronJob):** Schedule trade analysis runs (e.g., daily after market close).
- **Dashboard (Deployment):** A persistent pod hosting the FastAPI server and React frontend.
- **Secrets:** Kubernetes `Secret` to manage API keys for LLM providers (OpenAI, Anthropic, etc.) and data vendors (Alpha Vantage).

## Phase 4: Raspberry Pi Optimization
- **Remote LLMs:** Default to API-based LLMs to save Pi CPU/RAM resources.
- **Resource Constraints:** Apply K8s resource limits (e.g., 512MB RAM, 0.5 CPU) to ensure cluster stability.
- **Local Ingress:** Configure Traefik/Nginx to expose the dashboard at `trading.local`.
